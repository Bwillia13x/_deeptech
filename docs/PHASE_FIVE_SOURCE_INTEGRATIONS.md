# Phase Five: Extended Source Integration Plan

## Overview

Phase Five extends the Signal Harvester data strategy beyond X/Twitter and legacy discovery sources. The goal is to capture contextual signals from broader ecosystems (community conversations, academic publishing, multimedia) while keeping the existing Phase Two/Phase Three guarantees (LLM-backed classification, Redis caching, SSE progress, observability, and rate-limited APIs).

Key outcomes:

- Add at least two new high-value sources per release (Reddit, Hacker News, YouTube, select academic publishers, patents).
- Reuse the existing scoring/embedding pipeline (`src/signal_harvester/scoring.py`, `src/signal_harvester/embeddings.py`) so new signals surface with consistent salience.
- Keep ingestion resilient by instrumenting SSE progress, caching, and Prometheus metrics for each new source.
- Establish integration tests and contract checks to prevent schema drift.

## Source Prioritization

1. **Reddit (pushshift + API)**  
   - Ingest: subreddit metadata, threads, and comments via OAuth or Pushshift snapshots, honoring rate limits (`60/min` per client) and data retention policies.  
   - Classification: reuse `scoring.py` + `llm_client.py` for text, add subreddit/topic tagging, map Reddit IDs to artifact metadata.  
   - Testing: mock requests with sample thread JSON, assert `harvest fetch --source reddit` produces expected artifacts and SSE events.

2. **Hacker News (Firebase API)**  
   - Ingest: top/kids item polling, story/comment hierarchy (via `https://hacker-news.firebaseio.com/v0`).  
   - Scoring: treat posts and comments as discovery artifacts, highlight author reputation, use existing topic matching for `item_type = hn_story`.  
   - Tests: contract tests to ensure event payload matches backend TypeScript `HnSignal` interface and retains numeric IDs as strings.

3. **YouTube (Data API v3)**  
   - Ingest: channel uploads, comments, transcripts (via `youtube-transcript-api`), and engagement metrics (views, likes, comments).  
   - Evidence: extend `metadata_json` with `youtube_stats` (views, likes, comment_count) and `ur` list for linking to `artifact_relationships`.  
   - Tests: simulate `fetch` plus embedding to ensure SSE progress events include `source: youtube`.

4. **Academic / Technical Publications (PubMed, IEEE, arXiv follow-ups)**  
   - Ingest: metadata (title, authors, DOI, abstract), connect to existing arXiv pipeline, add DOIs via `relationship_detection`.  
   - Plan: start with PubMed/IEEE RSS or APIs; reuse `relationship_detection` for citations and `topic_evolution` for growth.  
   - Tests: contract tests verifying `Discovery` and `Artifact` models accept DOIs/citation arrays.

5. **Patent Filings / Standards (USPTO, WIPO)**  
   - Ingest: abstracts, inventors, application dates, classifications.  
   - Use: tie to entity resolution (inventors + firms) and experiments (measure recall for patent signals).  
   - Tests: ensure unique patent IDs and classification strings survive deduplication.

## Integration Strategy

1. **Client Pattern**  
   - Follow the existing structure `x_client.py`, `facebook_client.py`, `linkedin_client.py`: each source exports `fetch_artifacts(settings, since, limit)` returning DTOs with canonical fields `id`, `source`, `text`, `published_at`, `metadata`.  
   - Add source-specific config sections to `config/settings.yaml` for endpoints, credentials, and default fetch cadence.

2. **Pipeline Hook**  
   - Extend `pipeline_discovery.py` to include `if settings.sources.enable_reddit` style switches. Each new source logs SSE progress via the bulk job helper, records metrics (`discoveries_fetched_total` with `source` tag), and updates `metadata_json` with ingestion metadata.

3. **LLM Classification & Scoring**  
   - Leverage `embeddings` + `scoring` as-is; new artifacts plug into `signal_salience` and `detect_relationships`.  
   - Provide fallback logic: if a provider API fails, continue with other sources while recording `errors_total` with a new label `source:<name>`.  
   - Update `docs/OPERATIONS.md` (Section “Source Integrations”) with procedures for rotating API keys (OAuth tokens, quota monitoring).

4. **Pagination & Caching**  
   - Ensure paginated endpoints (discoveries, topics, artifacts) continue to work when new source volumes increase; reuse cursor-based logic in `src/signal_harvester/api.py`.  
   - Cache TTLs (1hr live, 24hr historical) already defined via `cache.py` apply uniformly; extend `GET /cache/stats` to break down hits by `source` tag in the next release.

## API Quotas & Rate Limit Plan

| Source | Rate Limit Strategy | Recovery |
| --- | --- | --- |
| Reddit | `60/min` per OAuth app; use `RateLimitTier.ANONYMOUS` fallback for unauthenticated polling + exponential backoff; store backoff metadata in `var/source_backoff.json`. | Retry after TTL, log to `errors_total{source="reddit"}`. |
| HN | Firebase limit ~10k requests/day; batch IDs with chunked fetches; align concurrency with `harvest batch`. | Spread across hours if high backlog. |
| YouTube | 10k units/day; prefer `youtube.search.list` + `videos.list`; persist `nextPageToken`. | Use `SourceRateLimiter` similar to `rate_limiter.py` but scoped to HTTP client. |
| PubMed / IEEE | Use provided API keys with daily quotas; implement caching of metadata in SQLite or Redis for 24h. | Track quotas in `sources.yaml` and warn operators via `logs/quotas.json`. |
| Patents | Download bulk data + incremental updates; fall back to zipped dumps if APIs throttle. | Document manual download step in `docs/POSTGRESQL_SETUP.md` and `docs/MIGRATION_TESTING.md`. |

Every fetch command updates Prometheus counters (`discoveries_fetched_total{source="..."}`) and SSE progress events include `source`. If a fetch exhausts quota, log `errors_total{source}` and mark the job “degraded” in `var/bulk_job_statuses.json`.

## Verification & Tests

- Add contract tests in `tests/test_contract_api_frontend.py` to ensure new fields (e.g., `reddit_thread_id`, `hn_score`, `youtube_stats`) match frontend types.  
- Introduce new unit tests under `tests/test_source_clients.py` for each source (mock HTTP + sample payload).  
- Extend SSE coverage: add `tests/test_bulk_jobs_sse.py` verifying progress events when a multi-source bulk import runs.  
- Maintain per-source integration tests executed via `make verify` (e.g., `python -m pytest tests/test_reddit_fetch.py`).  
- Document requirements for `make verify-all` to include `npm run typecheck` + `build` so UI keeps pace as new data models appear.

## Observability & Documentation

- Prometheus/Grafana dashboards (existing stack) should display invention of new sources by tagging metrics; update `monitoring/prometheus/job_labels.yml` accordingly.  
- SSE progress and `GET /metrics` should expose annotated counts per source for trending dashboards.  
- Document onboarding steps for each source in `docs/OPERATIONS.md` and `docs/PRODUCTION_DEPLOYMENT.md` (sections covering secret rotation and compliance).  
- Keep `docs/ARCHITECTURE_AND_READINESS.md` and `docs/PHASE_THREE_SCALING.md` synchronized with new ingestion flows (add bullet for Phase Five expansions).

## Next Steps

1. Finalize credentials for Reddit + Hacker News and add to `config/settings.yaml`.  
2. Implement `reddit_client.py` + `hn_client.py` with SSE instrumentation and caching.  
3. Coordinate with frontend team to add `sourceFilter` controls, SSE progress to `useBulkOperation` hook, and extend contract tests.  
4. Schedule load tests (k6/Locust) once multiple sources are live to validate p95/p99 SLA.  
5. After two sources are stable, update `ARCHITECTURE_AND_READINESS.md` Section 6/7 to reflect Phase Five launch and highlight remaining Phase Four UI work.
