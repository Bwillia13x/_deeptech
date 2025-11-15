# Staging Deployment Runbook

**Audience**: Operators preparing or maintaining the Signal Harvester staging environment.
**Last Updated**: November 12, 2025

---

## 1. Purpose

Provide a deterministic checklist for bringing up (or recycling) the Docker-based staging stack defined in `docker-compose.staging.yml`. The runbook covers prerequisites, environment preparation, deployment, verification, and common recovery procedures.

---

## 2. Required Inputs

- **Host Requirements**: Docker 24+ and Docker Compose 2+, 4 vCPUs / 16 GB RAM minimum, outbound HTTPS access for Let's Encrypt (unless running in `TLS_CERT_MODE=internal`).
- **DNS + Networking**:
  - `API_HOST`, `GRAFANA_HOST`, `PROMETHEUS_HOST`, `ALERTMANAGER_HOST` all point to the staging host's public IP.
  - TCP 80/443 exposed to the Internet; 22 open for SSH.
- **Secrets**:
  - PostgreSQL + Redis credentials (either managed services or the compose defaults in `docker-compose.staging.yml`).
  - API/LLM tokens, Slack webhook, and any other `.env.staging` content.
  - Basic Auth credentials for Grafana/Prometheus/Alertmanager (bcrypt hashes generated via `htpasswd -nbB user pass | cut -d: -f2`; escape dollar signs as `$$` before inserting into the env file).
- **TLS**:
  - `TLS_EMAIL` for Let's Encrypt issuance.
  - `TLS_CERT_MODE` values:
    - `tls {$TLS_CERT_MODE}` in `deploy/staging/Caddyfile` accepts either `internal` (self-signed) or an email address for ACME. Use `internal` for local drills, `:443` with valid DNS and Let's Encrypt otherwise.
  - `ACME_CA` overrides the certificate authority (default Let's Encrypt production URL). Set to `internal` when rehearsing without public DNS.

---

## 3. Environment Preparation

1. **Sync repository** on the target host:

   ```bash
   git clone git@github.com:your-org/signal-harvester.git /opt/signal-harvester
   cd /opt/signal-harvester
   ```

2. **Copy env template** and populate secrets:

   ```bash
   cp .env.staging.example .env.staging
   ```

   Key fields to edit:
   - `DATABASE_URL`: point at the managed PostgreSQL instance (`postgresql://USER:PASSWORD@HOST:PORT/DB`).
   - `POSTGRES_*`: only used when you run the bundled Postgres container. Leave blank (or remove) if you're delegating to an external DB.
   - `REDIS_HOST`, `REDIS_PASSWORD` etc. live in `.env.staging` even though the compose file defaults to the bundled Redis container.
   - `TLS_CERT_MODE`: set to `internal` for self-signed rehearsals, otherwise keep empty so Caddy requests a cert using `TLS_EMAIL` + Let's Encrypt.
   - `ACME_CA`: default `https://acme-v02.api.letsencrypt.org/directory`; switch to `https://acme-staging-v02.api.letsencrypt.org/directory` if you want to dry-run issuance without hitting rate limits.
   - `*_BASIC_AUTH_HASH`: paste bcrypt outputs with `$` escaped as `$$` because env files treat `$` as interpolation.
3. **Verify secrets**:

   ```bash
   ./scripts/check_env.py --file .env.staging  # optional helper, ensures required keys exist
   ```

4. **Seed databases** (only if using managed services):
   - PostgreSQL: the `schema-init` one-shot service now runs `scripts/init_postgres_schema.py` automatically during `make staging-stack-up`. Run it manually (`python scripts/init_postgres_schema.py --database-url "$DATABASE_URL"`) only if you need to re-bootstrap or troubleshoot outside of Compose, then confirm with `harvest verify-postgres --database-url "$DATABASE_URL"` (or `python scripts/validate_postgresql.py` when Typer isn't available).
   - Redis: no seeding required; ensure the DB indexes referenced in `docker-compose.staging.yml` exist (DB 1 for cache, DB 2 for rate limiting).

---

## 4. Deployment Steps

1. **Sanity check compose file**:

   ```bash
   docker compose --env-file .env.staging -f docker-compose.staging.yml config > /tmp/staging-config.yaml
   ```

   Inspect the generated config for unexpected interpolations or missing env vars.

2. **Launch the stack** using the Makefile helper (enforces `.env.staging` presence):

   ```bash
   make staging-stack-up
   ```

3. **Monitor startup**:

   ```bash
   docker compose --env-file .env.staging -f docker-compose.staging.yml ps
   docker compose --env-file .env.staging -f docker-compose.staging.yml logs -f edge signal-harvester scheduler
   ```

4. **Schema verification**: the `signal-harvester-staging-schema-init` container will exit with status `0` once migrations complete. Check its logs for the final schema version, or rerun manually if needed:

    ```bash
    docker compose --env-file .env.staging -f docker-compose.staging.yml logs -f schema-init
   make staging-schema-init                    # rerun migrations with the current .env.staging values
   DRY_RUN=1 make staging-schema-init          # connectivity check without schema mutations
    ```

   Behind the scenes the make target invokes `scripts/init_postgres_schema.py` inside the API image, so it honors the same `DATABASE_URL` you configured in `.env.staging`.

5. **Scheduler health**: confirm the `signal-harvester-staging-scheduler` container entered `running (healthy)`; logs should show `harvest daemon --interval 300` heartbeats every 5 minutes.
6. **Enable external reachability**: verify firewall rules map ports 80/443 to the host. Caddy terminates TLS and proxies the internal services.

### Recycling / Tear-down

```bash
make staging-stack-down         # Controlled shutdown
make staging-stack-up           # Redeploy after env changes
```

---

## 5. Verification Checklist

Run the following commands from an operator workstation (replace hostnames with your staging FQDNs):

```bash
# API readiness
curl -sk https://api.staging.example.com/health/ready | jq '.'

# API startup (ensures migrations applied)
curl -sk https://api.staging.example.com/health/startup | jq '.'

# Grafana (Basic Auth)
curl -sk -u admin:*** https://grafana.staging.example.com/api/health

# Prometheus health
curl -sk -u metrics:*** https://prometheus.staging.example.com/-/healthy

# Alertmanager health
curl -sk -u alerts:*** https://alerts.staging.example.com/-/healthy
```

Expected results:

- API endpoints return HTTP 200 with `status: "healthy"`. If status is `degraded`, inspect database/Redis connectivity.
- Grafana responds with `{ "database": "ok", "version": "..." }`.
- Prometheus/Alertmanager return `OK` text responses.

Additionally, confirm rate-limit headers on any API endpoint (curl `-I` against `/health/live`) to ensure the distributed limiter is enabled.

### Remote PostgreSQL Rehearsal (Week 7 Gate)

1. **Flip the DSN**: Update `.env.staging` so `DATABASE_URL` and `POSTGRES_*` point at the managed PostgreSQL instance (or VPN-accessible staging cluster). Re-run `make staging-stack-up` so the `schema-init` job seeds the remote DB.
2. **Capture schema evidence**:
   - `docker compose --env-file .env.staging -f docker-compose.staging.yml logs schema-init --tail 50`
   - `psql "$DATABASE_URL" -c "\\dt"`
   - `psql "$DATABASE_URL" -c "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1;"`
3. **Connectivity double-check (optional)**:
   - `DRY_RUN=1 make staging-schema-init`
   - `harvest verify-postgres --database-url "$DATABASE_URL"` (run from the repo root, falls back to `scripts/validate_postgresql.py` if needed)
4. **API + monitoring evidence**:
   - `curl -sk https://$API_HOST/health/ready | jq '.status'`
   - `curl -sk -u metrics:*** https://$PROMETHEUS_HOST/api/v1/targets | jq '.data.activeTargets[] | select(.labels.job=="signal-harvester")'`
   - `curl -sk -D - https://$API_HOST/health/live -o /dev/null | grep -i x-ratelimit`
5. **Archive artifacts**: Paste command outputs + timestamps into `docs/STAGING_VALIDATION_SUMMARY.md` (Week 7 section) and attach screenshots/log excerpts to the weekly status report so reviewers can validate the evidence bundle.

---

## 6. Operational Tasks

- **Log Inspection**:

   ```bash
   docker compose --env-file .env.staging -f docker-compose.staging.yml logs -f signal-harvester | grep ERROR
   docker compose --env-file .env.staging -f docker-compose.staging.yml logs -f prometheus grafana alertmanager edge
   ```

- **Backups**: leverage `./backups` volume mounted on Postgres. Run `pg_dump` via `docker compose exec db pg_dump ... > /backups/$(date +%F).sql` and copy off-host.
- **Certificate Renewal**: Caddy auto-renews. Ensure ports 80/443 remain available and `TLS_EMAIL` is a valid monitored inbox.
- **Basic Auth Rotation**: regenerate bcrypt hashes using `htpasswd -nbB <user> <pass> | cut -d: -f2`, update `.env.staging`, rerun `make staging-stack-up`.

---

## 7. Troubleshooting

| Symptom | Likely Cause | Resolution |
|---------|--------------|-----------|
| `curl https://api.../health/ready` returns `degraded` citing DB/Redis | `DATABASE_URL` or Redis env values misconfigured | Verify secrets in `.env.staging`, rerun `make staging-stack-up`. Check `docker compose logs signal-harvester` for SQLAlchemy errors. |
| Caddy logs `failed to obtain certificate` | DNS not pointing to host or firewall blocks port 80 | Confirm DNS A records, ensure port 80 open for ACME HTTP-01, optionally flip `TLS_CERT_MODE=internal` + `ACME_CA=internal` for temporary operation. |
| Grafana/Prometheus prompt for auth repeatedly | Bcrypt hashes missing `$$` escaping | Edit `.env.staging` so each `$` in the hash is doubled. Restart stack (Caddy reload occurs automatically). |
| `make staging-stack-up` fails with "Missing .env.staging" | Forgot to create env file | Copy `.env.staging.example`, populate secrets, rerun command. |
| `alembic` command fails inside container | Database unreachable | Run migrations from operator laptop against the same DSN to confirm network path; check security groups / firewalls. |
| Prometheus health OK but no metrics from API | `ENABLE_PROMETHEUS_METRICS` not set or scrape job misconfigured | Confirm env var inherits from `x-app-env` block, ensure `monitoring/prometheus/prometheus-docker.yml` contains `signal-harvester` target `http://signal-harvester:8000/metrics/prometheus`. |

---

## 8. Escalation

- On-call SRE: `sre@signalharvester.io`
- Slack: `#signal-harvester-ops`
- Pager escalation after 15 minutes of unresolved outage.
