# Signal Harvester - Production Deployment Guide

> This guide is part of the maintained documentation set for Signal Harvester.
> For the canonical architecture, readiness status, and prioritized roadmap, see [`signal-harvester/ARCHITECTURE_AND_READINESS.md`](signal-harvester/ARCHITECTURE_AND_READINESS.md:1).
> For a full project health check (tests, builds, and migrations), from the `signal-harvester` directory run `make verify-all` (see [`signal-harvester/Makefile`](signal-harvester/Makefile:7)).
> For CI/CD pipeline setup and workflow documentation, see [`CI_CD.md`](CI_CD.md).
> For Kubernetes manifest details and deployment helper scripts, see [`k8s/README.md`](../k8s/README.md).
> For production monitoring setup with Prometheus and Grafana, see [`MONITORING.md`](MONITORING.md).

## Table of Contents

- [Prerequisites](#-prerequisites)
- [Quick Start](#-quick-start)
- [Local Development Setup](#-local-development-deployment)
- [Kubernetes Production Deployment](#-kubernetes-production-deployment)
  - [Cluster Setup](#cluster-setup)
  - [Kubectl Configuration](#kubectl-configuration-for-github-actions)
  - [GitHub Container Registry](#github-container-registry-authentication)
  - [Environment Configuration](#environment-configuration)
  - [Deployment Steps](#deployment-steps)
  - [Deployment Helper Script](#deployment-helper-script)
  - [Rollback Procedures](#rollback-procedures)
- [Configuration](#-configuration)
- [Monitoring and Maintenance](#monitoring-and-maintenance)

## 🚀 Quick Start

### Using Deployment Helper Script

```bash
# Validate manifests
./deploy.sh validate production

# Deploy to staging
./deploy.sh deploy staging

# Deploy to production
./deploy.sh deploy production

# Check status
./deploy.sh status production

# View logs
./deploy.sh logs production

# Rollback if needed
./deploy.sh rollback production
```

For detailed Kubernetes deployment instructions, see [`k8s/README.md`](../k8s/README.md).

## 📋 Prerequisites

- Docker and Docker Compose installed
- Python 3.12+ (for local development)
- X/Twitter API Bearer Token
- LLM API keys (OpenAI, Anthropic, or both)
- Slack Webhook URL (optional, for notifications)

## 🔧 Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# X/Twitter API (Required)
X_BEARER_TOKEN=your_x_api_bearer_token_here

# LLM APIs (At least one required)
OPENAI_API_KEY=your_openai_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# If using OpenAI
OPENAI_MODEL=gpt-4o-mini

# If using Anthropic
ANTHROPIC_MODEL=claude-3-5-haiku-latest

# Slack Notifications (Optional)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# API Security (Recommended for production)
HARVEST_API_KEY=your_secure_random_api_key_here

# Database (Optional, defaults to var/app.db)
DATABASE_PATH=var/app.db

# Rate Limiting (Optional, defaults to enabled)
RATE_LIMITING_ENABLED=true

# Logging (Optional, defaults to console)
LOG_LEVEL=INFO
LOG_FORMAT=json  # Use 'json' for production log aggregation

# Redis for Rate Limiting (Optional, uses in-memory if not set)
REDIS_URL=redis://localhost:6379/0

# ============================================
# Phase Two: Advanced Discovery Features
# ============================================

# Redis for Enhanced Embeddings (Recommended for Phase Two)
# Provides persistent caching for embeddings with TTL management
REDIS_EMBEDDINGS_ENABLED=true
REDIS_EMBEDDINGS_HOST=localhost
REDIS_EMBEDDINGS_PORT=6379
REDIS_EMBEDDINGS_DB=1  # Use different DB from rate limiting
REDIS_EMBEDDINGS_PASSWORD=  # Optional

# Facebook Graph API (Optional, for social media ingestion)
FACEBOOK_ACCESS_TOKEN=your_facebook_access_token_here
# Get token from: https://developers.facebook.com/tools/explorer/

# LinkedIn API v2 (Optional, for professional network ingestion)
LINKEDIN_ACCESS_TOKEN=your_linkedin_access_token_here
# Generate via: https://www.linkedin.com/developers/apps
# Required scopes: r_organization_social, r_basicprofile

# Sentry Error Tracking (Optional, for production monitoring)
SENTRY_DSN=https://your-sentry-dsn@sentry.io/project-id
SENTRY_ENVIRONMENT=production  # or staging, development
SENTRY_TRACES_SAMPLE_RATE=0.1  # 10% of transactions
```

**Phase Two Environment Variable Notes:**

- **Redis Embeddings**: Highly recommended for production. Dramatically improves performance by caching embeddings across restarts. Falls back to in-memory cache if disabled.
- **Facebook/LinkedIn**: Optional. Only required if ingesting social media content. Tokens must be refreshed periodically (Facebook: 60 days, LinkedIn: 60 days).
- **Sentry**: Recommended for production error tracking and performance monitoring.

### Settings Configuration

Edit `config/settings.yaml`:

```yaml
app:
  database_path: "var/app.db"  # Override with DATABASE_PATH env var
  fetch:
    max_results: 50  # Tweets per query
    lang: "en"  # Language filter
  llm:
    provider: "openai"  # or "anthropic" or "dummy" for testing
    model: "gpt-4o-mini"  # Override with OPENAI_MODEL env var
    temperature: 0.2
  scoring:
    weights:
      likes: 1.0
      retweets: 3.0
      replies: 2.0
      quotes: 2.5
      urgency: 4.0
      sentiment_positive: 1.0
      sentiment_negative: 1.2
      sentiment_neutral: 0.9
      category_boosts:
        outage: 2.0
        security: 1.8
        bug: 1.3
        question: 1.0
        praise: 0.8
        other: 1.0
      recency_half_life_hours: 24.0
      base: 1.0
      cap: 100.0
  
  # Phase Two: Enhanced Embeddings Configuration
  embeddings:
    redis_enabled: true  # Use Redis for persistent caching
    redis_host: "localhost"  # Override with env var
    redis_port: 6379
    redis_db: 1
    ttl_seconds: 604800  # 7 days cache lifetime
    max_memory_cache_size: 10000  # Fallback in-memory cache
    model_name: "all-MiniLM-L6-v2"  # 384-dimensional embeddings
    batch_size: 32  # Parallel embedding computation
    refresh_enabled: true
    refresh_interval_hours: 24
    refresh_stale_threshold_days: 3
  
  # Phase Two: Identity Resolution Configuration
  identity_resolution:
    enabled: true
    similarity_threshold: 0.75  # Match threshold for entity merging
    name_weight: 0.50  # Weighted field importance
    affiliation_weight: 0.30
    domain_weight: 0.15
    accounts_weight: 0.05
    use_llm_confirmation: true  # LLM validates matches
  
  # Phase Two: Topic Evolution Configuration
  topic_evolution:
    enabled: true
    min_artifacts_per_topic: 3
    similarity_threshold: 0.70
    recency_decay_days: 30
    emergence_threshold: 0.75
    growth_window_days: 14
    prediction_window_days: 14
  
  # Phase Two: Social Media Sources
  sources:
    facebook:
      pages:
        - "YourOrgPage"
        - "YourLabPage"
      groups: []
      search_queries: []
      max_results: 100
    
    linkedin:
      organizations:
        - "1234567"  # Numeric organization IDs
      max_results: 100
    
    # Existing sources (arXiv, GitHub, X)
    arxiv:
      categories: ["cs.AI", "cs.LG", "cs.CL"]
      max_results: 100
    
    github:
      topics: ["machine-learning", "deep-learning"]
      languages: ["Python", "Jupyter Notebook"]
      min_stars: 100
      max_results: 50
    
    x:
      max_results: 50
      lang: "en"

queries:
  - name: "brand_support"
    enabled: true
    query: "(@YourBrand OR #YourBrand) (help OR support OR broken OR down OR bug OR crash) -is:retweet -is:reply lang:en"
  
  - name: "competitor_chatter"
    enabled: false
    query: "(CompetitorA OR CompetitorB) (switch OR alternatives) -is:retweet -is:reply lang:en"
```

**Phase Two Configuration Notes:**

- **Embeddings**: Redis highly recommended for production. Set `redis_enabled: false` to use memory-only cache (loses cache on restart).
- **Identity Resolution**: Adjust weights based on your data quality. Higher `name_weight` for clean name data, higher `affiliation_weight` for institutional content.
- **Topic Evolution**: Lower `min_artifacts_per_topic` for emerging fields, higher for established areas.
- **Social Sources**: Facebook/LinkedIn require valid access tokens in environment variables.

## 🐳 Recommended Docker Compose Deployment

This section is the canonical, minimal path for Docker-based deployment and is aligned with:

- [`signal-harvester/Dockerfile`](signal-harvester/Dockerfile:1)
- [`signal-harvester/docker-compose.yml`](signal-harvester/docker-compose.yml:1)
- The readiness and roadmap in [`signal-harvester/ARCHITECTURE_AND_READINESS.md`](signal-harvester/ARCHITECTURE_AND_READINESS.md:1)
- The `make verify-all` gate in [`signal-harvester/Makefile`](signal-harvester/Makefile:7)

### 1. Pre-deploy verification

From the repository root:

```bash
cd signal-harvester
make verify-all
```

This runs migrations, backend tests, and frontend build/typecheck to validate the codebase before building images.

### 2. Environment setup

In `signal-harvester/`, create `.env` (based on `.env.example`):

```bash
cp .env.example .env
# Edit .env with:
# - X_BEARER_TOKEN
# - OPENAI_API_KEY / ANTHROPIC_API_KEY (at least one)
# - SLACK_WEBHOOK_URL (optional)
# - HARVEST_API_KEY
# - Any other documented settings
```

### 3. Build and run with Docker Compose

From `signal-harvester/`:

```bash
docker-compose up -d
```

Behavior:

- Uses [`signal-harvester/Dockerfile`](signal-harvester/Dockerfile:1) as the build context.
- Runs the API process as a non-root `harvester` user.
- Exposes the API on `localhost:8000`.
- Mounts:
  - `./var` → `/app/var` for SQLite and runtime state.
  - `./data` → `/app/data` for exports/snapshots.
  - `./config` → `/app/config` (read-only) for settings.

### 4. Services

- `signal-harvester`:
  - Entry command: `harvest-api` (FastAPI app via `harvest api` in [`signal-harvester/src/signal_harvester/cli.py`](signal-harvester/src/signal_harvester/cli.py:76))
  - Port: `8000` (host) → `8000` (container)
  - Healthcheck: HTTP GET `http://localhost:8000/health` from inside container.
- `scheduler` (optional):
  - Uses the same image and volumes.
  - Runs `harvest daemon --interval 300` to execute the pipeline periodically.
  - Depends on a healthy `signal-harvester` service.

### 5. Post-deploy verification

After containers are running:

```bash
curl http://localhost:8000/health
```

Expected: a successful JSON health response. This is the canonical runtime check and should be used with any external monitoring.

### 6. Manual Docker run (alternative)

To run the API without Compose:

```bash
docker build -t signal-harvester .
docker run -d \
  --name signal-harvester \
  --env-file .env \
  -p 8000:8000 \
  -v $(pwd)/var:/app/var \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/config:/app/config:ro \
  --restart unless-stopped \
  signal-harvester
```

### Manual Docker Run

```bash
docker run -d \
  --name signal-harvester \
  -p 8000:8000 \
  -e X_BEARER_TOKEN=$X_BEARER_TOKEN \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  -e HARVEST_API_KEY=$HARVEST_API_KEY \
  -e DATABASE_PATH=/app/var/app.db \
  -v $(pwd)/var:/app/var \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/config:/app/config:ro \
  --restart unless-stopped \
  signal-harvester
```

## 🚀 Initial Setup

### 1. Initialize Database

```bash
# Using CLI
docker-compose exec signal-harvester harvest init-db

# Or manually
sqlite3 var/app.db < schema.sql
```

### 2. Run Database Migrations

```bash
# Using CLI
docker-compose exec signal-harvester harvest migrate

# Or using alembic
docker-compose exec signal-harvester alembic upgrade head
```

**Phase Two Migrations:**

Signal Harvester includes 8+ Alembic migrations for Phase Two features. Ensure all migrations complete successfully:

```bash
docker-compose exec signal-harvester alembic current
docker-compose exec signal-harvester alembic history
```

## ☸️ Kubernetes Production Deployment

This section covers deploying Signal Harvester to a production Kubernetes cluster with GitHub Actions CI/CD automation.

### Cluster Setup

**Recommended Cluster Specifications:**

- **Node Pool**: 3 nodes minimum
- **Node Size**: 2 vCPU, 4GB RAM per node
- **Kubernetes Version**: 1.25+
- **Persistent Storage**: Dynamic provisioning with SSD-backed storage class
- **Ingress Controller**: nginx-ingress or cloud provider ingress
- **TLS Certificates**: cert-manager with Let's Encrypt

**Supported Cloud Providers:**

- Google Kubernetes Engine (GKE)
- Amazon Elastic Kubernetes Service (EKS)
- Azure Kubernetes Service (AKS)
- DigitalOcean Kubernetes (DOKS)

**Create Cluster:**

```bash
# GKE Example
gcloud container clusters create signal-harvester-prod \
  --num-nodes=3 \
  --machine-type=e2-standard-2 \
  --zone=us-central1-a \
  --disk-size=50GB \
  --disk-type=pd-ssd \
  --enable-autoscaling \
  --min-nodes=2 \
  --max-nodes=5

# EKS Example
eksctl create cluster \
  --name signal-harvester-prod \
  --region us-west-2 \
  --nodegroup-name standard-workers \
  --node-type t3.medium \
  --nodes 3 \
  --nodes-min 2 \
  --nodes-max 5 \
  --managed

# AKS Example
az aks create \
  --resource-group signal-harvester \
  --name signal-harvester-prod \
  --node-count 3 \
  --node-vm-size Standard_DS2_v2 \
  --enable-cluster-autoscaler \
  --min-count 2 \
  --max-count 5 \
  --location eastus
```

### Kubectl Configuration for GitHub Actions

**Generate Kubeconfig for CI/CD:**

```bash
# Get cluster credentials
kubectl config view --flatten --minify > kubeconfig-staging.yaml

# Create GitHub secret from kubeconfig
cat kubeconfig-staging.yaml | base64 > kubeconfig-staging-base64.txt
```

**Add to GitHub Secrets:**

1. Navigate to repository → Settings → Secrets and variables → Actions
2. Click "New repository secret"
3. Create secrets:
   - Name: `KUBE_CONFIG_STAGING`
   - Value: Contents of `kubeconfig-staging-base64.txt`
   - Name: `KUBE_CONFIG_PRODUCTION`
   - Value: Production cluster kubeconfig (base64 encoded)

**Service Account Alternative (Recommended for Production):**

```bash
# Create service account for GitHub Actions
kubectl create serviceaccount github-actions -n default

# Create role with deployment permissions
kubectl create role github-actions-deployer \
  --verb=get,list,watch,create,update,patch,delete \
  --resource=deployments,services,configmaps,secrets

# Bind role to service account
kubectl create rolebinding github-actions-deployer \
  --role=github-actions-deployer \
  --serviceaccount=default:github-actions

# Get service account token
kubectl create token github-actions --duration=87600h  # 10 years

# Create kubeconfig with service account token
# (Use the token in kubeconfig user section)
```

### GitHub Container Registry Authentication

**GitHub Actions Automatic Authentication:**

GitHub Actions automatically authenticates to GHCR using the `GITHUB_TOKEN` secret. No manual setup needed for push/pull during workflows.

**Pull Images from Kubernetes Cluster:**

```bash
# Create Docker registry secret
kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io \
  --docker-username=<github-username> \
  --docker-password=<github-personal-access-token> \
  --docker-email=<github-email>

# Verify secret
kubectl get secret ghcr-secret -o yaml
```

**Generate GitHub Personal Access Token (PAT):**

1. GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Click "Generate new token (classic)"
3. Scopes required:
   - `read:packages` - Pull container images
   - `write:packages` - Push container images (for workflows)
4. Copy token and use in kubectl command above

### Environment Configuration

**Create Kubernetes Environments in GitHub:**

1. Repository → Settings → Environments
2. Create `staging` environment:
   - Deployment branches: `main`
   - No required reviewers
   - Add environment secrets (if different from staging)
3. Create `production` environment:
   - Deployment branches: Tags matching `v*.*.*`
   - Required reviewers: 1+ team members
   - Environment protection rules enabled

**Environment-Specific Configuration:**

```bash
# Staging namespace
kubectl create namespace staging

# Production namespace
kubectl create namespace production

# Set default namespace (optional)
kubectl config set-context --current --namespace=staging
```

### Deployment Steps

**Prerequisites Completed:**

- ✅ Kubernetes cluster created
- ✅ kubectl configured with cluster credentials
- ✅ Kustomize installed (`brew install kustomize`)
- ✅ Secrets configured in `k8s/base/secrets.yaml`

**Option 1: Using Deployment Helper Script (Recommended)**

The `deploy.sh` script provides a simplified interface for all deployment operations:

```bash
# Validate manifests before deployment
./deploy.sh validate staging
./deploy.sh validate production

# Deploy to staging (auto-confirms)
./deploy.sh deploy staging

# Deploy to production (requires confirmation)
./deploy.sh deploy production

# Check deployment status
./deploy.sh status production

# View live logs
./deploy.sh logs production

# Scale deployment
./deploy.sh scale production 5

# Backup database
./deploy.sh backup production

# Rollback deployment
./deploy.sh rollback production
```

**Option 2: Manual Deployment with Kustomize**

For more control, deploy directly with kubectl and kustomize:

- ✅ Kubeconfig added to GitHub secrets
- ✅ GHCR authentication configured
- ✅ GitHub environments created (staging, production)

**Deployment via GitHub Actions (Recommended):**

1. **Trigger Staging Deployment:**

   ```bash
   # Push to main branch
   git checkout main
   git pull
   git push origin main
   ```

   - GitHub Actions workflow `deploy.yml` automatically triggers
   - Builds Docker image with tag `main-<sha>`
   - Pushes to `ghcr.io/bwillia13x/_deeptech:main`
   - Deploys to staging environment
   - Runs smoke tests

2. **Trigger Production Deployment:**

   ```bash
   # Create version tag
   git checkout main
   git pull
   git tag -a v1.2.3 -m "Release v1.2.3: Add Kubernetes deployment"
   git push origin v1.2.3
   ```

   - GitHub Actions workflow deploys to staging first
   - Waits for manual approval (configured in production environment)
   - After approval, deploys to production
   - Runs smoke tests and notifications

3. **Monitor Deployment:**

   ```bash
   # Watch GitHub Actions
   gh run watch
   
   # Or view in browser
   # https://github.com/Bwillia13x/_deeptech/actions
   ```

**Manual Deployment (Alternative):**

If you need to deploy manually without GitHub Actions:

```bash
# Build and push Docker image
docker build -t ghcr.io/bwillia13x/_deeptech:v1.2.3 .
docker push ghcr.io/bwillia13x/_deeptech:v1.2.3

# Apply Kubernetes manifests (requires Task 2: K8s manifests)
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secrets.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/ingress.yaml

# Wait for rollout
kubectl rollout status deployment/signal-harvester -n production

# Verify deployment
kubectl get pods -n production
kubectl get svc -n production
```

### Rollback Procedures

**Automatic Rollback (GitHub Actions):**

If smoke tests fail, GitHub Actions can automatically trigger rollback:

```yaml
# In deploy.yml workflow (already configured)
- name: Rollback on failure
  if: failure()
  run: |
    kubectl rollout undo deployment/signal-harvester
```

**Manual Rollback:**

```bash
# View deployment history
kubectl rollout history deployment/signal-harvester

# Example output:
# REVISION  CHANGE-CAUSE
# 1         Initial deployment
# 2         Update to v1.2.3
# 3         Update to v1.2.4 (current - broken)

# Rollback to previous version (v1.2.3)
kubectl rollout undo deployment/signal-harvester

# Rollback to specific revision
kubectl rollout undo deployment/signal-harvester --to-revision=2

# Monitor rollback progress
kubectl rollout status deployment/signal-harvester

# Verify pods are running
kubectl get pods -l app=signal-harvester

# Check application health
kubectl exec -it deployment/signal-harvester -- curl localhost:8000/health
```

**Verify Rollback Success:**

```bash
# Check current image version
kubectl get deployment signal-harvester -o jsonpath='{.spec.template.spec.containers[0].image}'

# Check pod events
kubectl describe pods -l app=signal-harvester | grep -A 10 Events

# Check application logs
kubectl logs -l app=signal-harvester --tail=100

# Test API endpoint
kubectl port-forward deployment/signal-harvester 8000:8000
curl http://localhost:8000/health
```

**Emergency Rollback from Bad Release:**

If a version tag was deployed to production and needs immediate rollback:

```bash
# 1. Rollback Kubernetes deployment
kubectl rollout undo deployment/signal-harvester -n production

# 2. Delete bad version tag (prevents re-deployment)
git tag -d v1.2.4
git push origin :refs/tags/v1.2.4

# 3. Create hotfix tag from previous good version
git checkout v1.2.3
git tag -a v1.2.3-hotfix -m "Hotfix: Rollback from v1.2.4"
git push origin v1.2.3-hotfix

# 4. Notify team
echo "Production rolled back to v1.2.3 due to issues in v1.2.4"
```

**Post-Rollback Actions:**

1. Investigate root cause of failure
2. Fix issues in development branch
3. Test thoroughly in staging
4. Create new version tag when ready
5. Update deployment runbook with lessons learned

### Health Checks and Smoke Tests

**Kubernetes Liveness Probe:**

```yaml
# Already configured in deployment manifests
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 3
```

**Smoke Tests After Deployment:**

```bash
# Run from GitHub Actions or manually
export API_URL="https://signal-harvester.example.com"

# 1. Health check
curl -f $API_URL/health || exit 1

# 2. Metrics endpoint
curl -f $API_URL/metrics | jq . || exit 1

# 3. API authentication
curl -f -H "X-API-Key: $HARVEST_API_KEY" $API_URL/api/signals | jq . || exit 1

# 4. Database connectivity
curl -f -H "X-API-Key: $HARVEST_API_KEY" $API_URL/api/discoveries?limit=1 | jq . || exit 1

echo "✅ All smoke tests passed"
```

### Monitoring Production Deployments

**Watch Deployment Progress:**

```bash
# Real-time pod status
watch kubectl get pods -n production

# Real-time deployment events
kubectl get events -n production --watch

# Real-time logs
kubectl logs -f deployment/signal-harvester -n production
```

**Post-Deployment Validation:**

```bash
# Check deployment status
kubectl get deployment signal-harvester -n production

# Check replica count
kubectl get rs -n production | grep signal-harvester

# Check service endpoints
kubectl get endpoints signal-harvester -n production

# Test internal service
kubectl run test-pod --rm -it --image=curlimages/curl -- \
  curl http://signal-harvester.production.svc.cluster.local:8000/health
```

**Deployment Notifications:**

Configure Slack webhook in GitHub secrets for deployment notifications:

```bash
# Add to GitHub secrets
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

GitHub Actions sends notifications on:

- ✅ Successful staging deployment
- ✅ Successful production deployment
- ❌ Deployment failures
- 🔄 Rollback events

```bash
# Check current migration version
docker-compose exec signal-harvester alembic current

# Expected output should show migration 8 or higher:
# INFO  [alembic.runtime.migration] Context impl SQLiteImpl.
# INFO  [alembic.runtime.migration] Will assume non-transactional DDL.
# 8_add_experiments_tables (head)

# List all migrations
docker-compose exec signal-harvester alembic history

# Expected migrations (Phase Two):
# Migration 7: artifact_relationships table (cross-source corroboration)
# Migration 8: experiments, experiment_runs, discovery_labels tables (backtesting)
```

**Migration Rollback (if needed):**

```bash
# Downgrade to specific version
docker-compose exec signal-harvester alembic downgrade <revision>

# Downgrade one version
docker-compose exec signal-harvester alembic downgrade -1

# CAUTION: Downgrades may lose data. Backup first!
cp var/signal_harvester.db var/signal_harvester.db.backup
```

**Database Schema Verification:**

```bash
# Verify Phase Two tables exist
sqlite3 var/signal_harvester.db ".tables" | grep -E "(entities|artifacts|topics|relationships|experiments)"

# Expected tables:
# - entities (researchers, organizations)
# - accounts (cross-platform identities)
# - artifacts (discoveries from all sources)
# - topics (trending research areas)
# - artifact_topics (many-to-many relationships)
# - artifact_relationships (citation graph)
# - experiments (A/B test definitions)
# - experiment_runs (performance metrics)
# - discovery_labels (ground truth annotations)
```

### 3. Test the API

```bash
# Health check
curl http://localhost:8000/health

# Test with API key
curl -H "X-API-Key: $HARVEST_API_KEY" \
  "http://localhost:8000/top?limit=10&min_salience=50.0"

# Run pipeline
curl -X POST -H "X-API-Key: $HARVEST_API_KEY" \
  "http://localhost:8000/refresh?notify_threshold=80.0&notify_limit=5"
```

## 📊 Monitoring

### Health Checks

The API provides a health check endpoint:

```bash
curl http://localhost:8000/health
```

**Response:**

```json
{
  "status": "healthy",
  "version": "0.1.0",
  "timestamp": "2024-01-01T12:00:00Z",
  "checks": {
    "database": "ok",
    "settings": "ok"
  }
}
```

### Logs

**View logs:**

```bash
# Docker
docker-compose logs -f signal-harvester

# View JSON logs
docker-compose logs -f signal-harvester | jq '.'
```

**Log levels:**

- `DEBUG`: Detailed debugging information
- `INFO`: General operational information
- `WARNING`: Warning messages
- `ERROR`: Error messages

### Metrics

**Rate limiting headers:**

```
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 9
X-RateLimit-Reset: 1704067200
```

## 🔒 Security

### API Key Authentication

Always use API key authentication in production:

```bash
curl -H "X-API-Key: YOUR_SECRET_KEY" http://localhost:8000/top
```

### Rate Limiting

Default: 10 requests per minute per IP

Configure via environment:

```bash
RATE_LIMITING_ENABLED=true
REDIS_URL=redis://redis:6379/0  # For distributed rate limiting
```

### Network Security

**Docker Compose with network isolation:**

```yaml
networks:
  frontend:
    driver: bridge
  backend:
    driver: bridge
    internal: true

services:
  signal-harvester:
    networks:
      - frontend
      - backend
  
  # Database (if using external DB)
  # db:
  #   networks:
  #     - backend
```

## 🔄 Automated Pipeline

### Using Docker Compose Scheduler

The scheduler service runs the pipeline every 5 minutes (300 seconds):

```yaml
scheduler:
  build: .
  command: ["harvest", "daemon", "--interval", "300"]
  environment:
    - DATABASE_PATH=/app/var/app.db
    # ... other env vars
```

### Using Systemd

Create `/etc/systemd/system/signal-harvester.service`:

```ini
[Unit]
Description=Signal Harvester API
After=docker.service
Requires=docker.service

[Service]
Type=simple
Restart=always
RestartSec=10
WorkingDirectory=/opt/signal-harvester
ExecStart=/usr/bin/docker-compose up
ExecStop=/usr/bin/docker-compose down

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable signal-harvester
sudo systemctl start signal-harvester
```

## 📦 Production Checklist

### Pre-Deployment

- [ ] API keys configured in `.env`
- [ ] Database initialized
- [ ] Migrations run
- [ ] Health check endpoint tested
- [ ] Rate limiting configured
- [ ] SSL/TLS certificates (for HTTPS)
- [ ] Backup strategy in place

### Deployment

- [ ] Docker image built and tested
- [ ] Environment variables set
- [ ] Volumes configured for persistence
- [ ] Ports exposed correctly
- [ ] Health checks working
- [ ] Logs accessible

### Post-Deployment

- [ ] API responding correctly
- [ ] Pipeline runs successfully
- [ ] Notifications working (if configured)
- [ ] Monitoring alerts configured
- [ ] Regular backups scheduled

## 🔍 Troubleshooting

### Database Issues

**Check database connectivity:**

```bash
docker-compose exec signal-harvester \
  python -c "import sqlite3; conn = sqlite3.connect('var/app.db'); print('OK'); conn.close()"
```

**Reset database:**

```bash
docker-compose exec signal-harvester rm var/app.db
docker-compose exec signal-harvester harvest init-db
```

### API Issues

**Check API status:**

```bash
curl http://localhost:8000/health
```

**Test API key authentication:**

```bash
curl -H "X-API-Key: $HARVEST_API_KEY" http://localhost:8000/top
```

### Rate Limiting

**Check rate limit status:**

```bash
# Look for 429 responses
docker-compose logs signal-harvester | grep "429"
```

**Temporarily disable rate limiting:**

```bash
RATE_LIMITING_ENABLED=false docker-compose up -d
```

## 📈 Scaling

### Horizontal Scaling

Use a shared Redis for rate limiting and external database:

```yaml
# docker-compose.scale.yml
services:
  signal-harvester:
    deploy:
      replicas: 3
    environment:
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - redis
  
  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data

volumes:
  redis_data:
```

### Load Balancing

Use a reverse proxy like Nginx or Traefik:

```yaml
# docker-compose.lb.yml
services:
  traefik:
    image: traefik:v2.10
    command:
      - "--api.insecure=true"
      - "--providers.docker=true"
      - "--entrypoints.web.address=:80"
    ports:
      - "80:80"
      - "8080:8080"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
  
  signal-harvester:
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.harvester.rule=Host(`api.yourdomain.com`)"
      - "traefik.http.services.harvester.loadbalancer.server.port=8000"
```

## 🆘 Emergency Procedures

### Restart Services

```bash
# Restart API
docker-compose restart signal-harvester

# Restart scheduler
docker-compose restart scheduler

# Full restart
docker-compose down && docker-compose up -d
```

### Database Recovery

**From backup:**

```bash
# Stop services
docker-compose down

# Restore database
cp backups/app.db.20240101 var/app.db

# Restart services
docker-compose up -d
```

### Rollback Deployment

```bash
# Use previous image tag
docker-compose pull signal-harvester:previous-tag
docker-compose up -d signal-harvester
```

## 📚 Additional Resources

- [API Documentation](API.md)
- [Operations Guide](OPERATIONS.md)
- [Backup Procedures](BACKUP.md)
- [Monitoring Setup with Prometheus/Grafana](MONITORING.md)
- [CI/CD Pipeline Documentation](CI_CD.md)
- [Kubernetes Deployment Guide](../k8s/README.md)
- [Cross-Source Corroboration](CROSS_SOURCE_CORROBORATION.md)
- [Experiments & Backtesting](EXPERIMENTS.md)

## Monitoring and Production Health

### Monitoring Stack Deployment

After deploying the main application, deploy the monitoring stack:

```bash
# Deploy Prometheus
kubectl apply -f monitoring/k8s/prometheus.yaml

# Create Grafana admin password
kubectl -n signal-harvester create secret generic grafana-admin \
  --from-literal=password='YOUR_SECURE_PASSWORD'

# Deploy Grafana
kubectl apply -f monitoring/k8s/grafana.yaml

# Verify monitoring stack
kubectl -n signal-harvester get pods -l component=monitoring
```

### Accessing Monitoring Dashboards

**Prometheus UI**:

```bash
kubectl -n signal-harvester port-forward svc/prometheus 9090:9090
# Visit http://localhost:9090
```

**Grafana Dashboards**:

```bash
kubectl -n signal-harvester port-forward svc/grafana 3000:3000
# Visit http://localhost:3000
# Login: admin / YOUR_SECURE_PASSWORD
```

### Key Dashboards

1. **API Performance**: HTTP metrics, error rates, latency
2. **Discovery Pipeline**: Source-specific metrics, pipeline health, topic coverage
3. **LLM Usage & Costs**: Token usage, provider performance, cost tracking
4. **System Resources**: CPU, memory, database, cache metrics

### Critical Alerts

Monitor these alerts for production health:

- **HighErrorRate**: Error rate > 5% for 5 minutes (Critical)
- **APIDown**: No successful requests for 2 minutes (Critical)
- **HighMemoryUsage**: Memory > 90% for 5 minutes (Critical)
- **PipelineFailures**: Pipeline failure rate > 10% (Warning)
- **HighLLMErrorRate**: LLM error rate > 5% (Warning)

For detailed monitoring setup, alert response procedures, and troubleshooting guides, see [MONITORING.md](MONITORING.md).
