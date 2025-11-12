# Signal Harvester - Team Onboarding Guide

> **Purpose**: Role-specific onboarding for engineers, data scientists, operators, and product managers working with Signal Harvester.

## 🎯 Quick Start by Role

| Role | Start Here | Key Skills Needed | Time to Productivity |
|------|-----------|-------------------|---------------------|
| **Backend Engineer** | [Backend Development](#-backend-engineer-onboarding) | Python, FastAPI, SQLite, Docker | 2-3 days |
| **Frontend Engineer** | [Frontend Development](#-frontend-engineer-onboarding) | React, TypeScript, TanStack Query | 1-2 days |
| **Data Scientist** | [Data Science](#-data-scientist-onboarding) | Python, embeddings, ML metrics | 3-5 days |
| **Platform Operator** | [Operations](#-platform-operator-onboarding) | Docker, Linux, monitoring | 1-2 days |
| **Product Manager** | [Product Management](#-product-manager-onboarding) | Domain knowledge, analytics | 1 day |

---

## 👨‍💻 Backend Engineer Onboarding

### Day 1: Environment Setup & Architecture

**Prerequisites:**

- Python 3.12+
- Docker & Docker Compose
- Git
- SQLite3 CLI tools

**Setup Steps:**

```bash
# 1. Clone repository
git clone https://github.com/your-org/signal-harvester.git
cd signal-harvester

# 2. Install dependencies
python -m pip install -e ".[dev]"

# 3. Configure environment
cp .env.example .env
# Edit .env with your API keys

# 4. Initialize database
harvest init-db
alembic upgrade head

# 5. Run tests
pytest tests/ -v

# 6. Verify build
make verify-all
```

**Architecture Overview:**

```
src/signal_harvester/
├── api.py              # FastAPI application (626 lines)
├── pipeline.py         # Main orchestration (legacy mode)
├── pipeline_discovery.py  # Phase One discovery pipeline
├── db.py               # Database models & operations (2102 lines)
├── llm_client.py       # LLM integrations (OpenAI, Anthropic)
├── scoring.py          # Signal scoring algorithms
├── discovery_scoring.py  # Discovery scoring (Phase One)
├── identity_resolution.py  # Entity deduplication
├── topic_evolution.py   # Topic lifecycle tracking
├── embeddings.py       # Unified embedding service (544 lines)
├── relationship_detection.py  # Citation graph analysis
├── experiment.py       # A/B testing framework
└── cli/                # Typer command-line interfaces
```

**Key Concepts:**

1. **Dual-Mode Operation**:
   - **Legacy Mode**: Social media signal harvesting (X/Twitter)
   - **Phase One**: Deep tech discovery (arXiv, GitHub, Semantic Scholar, X, Facebook, LinkedIn)

2. **Database Schema**:
   - SQLite with WAL mode for concurrency
   - 8 Alembic migrations (see `migrations/versions/`)
   - Core tables: `signals`, `artifacts`, `entities`, `topics`, `artifact_relationships`, `experiments`

3. **API Design**:
   - Pydantic v2 models for request/response
   - Contract tests ensure API ↔ Frontend alignment (`tests/test_contract_api_frontend.py`)
   - Rate limiting with `SimpleRateLimiter` or Redis

**First Tasks:**

- [ ] Read `ARCHITECTURE_AND_READINESS.md` (master plan)
- [ ] Run full test suite: `pytest tests/ -v` (expect 100+ tests passing)
- [ ] Review API contracts: `pytest tests/test_contract_api_frontend.py -v`
- [ ] Explore database schema: `sqlite3 var/signal_harvester.db ".schema"`
- [ ] Run discovery pipeline: `harvest discover --help`

### Day 2-3: Core Development Workflow

**Development Commands:**

```bash
# Run API server (auto-reload)
harvest api

# Run discovery pipeline
harvest discover

# Run backtesting
harvest backtest --days 3 --metrics

# Database migrations
alembic revision --autogenerate -m "description"
alembic upgrade head

# Code quality
make lint      # Ruff linter
make format    # Auto-format
make test      # pytest
```

**Code Style:**

- **Line Length**: 120 characters (enforced by ruff)
- **Type Hints**: Required (mypy strict mode)
- **Docstrings**: Google or NumPy style
- **Imports**: Sorted by ruff (no manual sorting)

**Testing Guidelines:**

```bash
# Unit tests (fast)
pytest tests/test_scoring.py -v

# Integration tests (database required)
pytest tests/test_api.py -v

# Contract tests (API ↔ Frontend alignment)
pytest tests/test_contract_api_frontend.py -v

# Phase Two tests
pytest tests/test_embeddings.py -v
pytest tests/test_identity_resolution.py -v
pytest tests/test_topic_evolution.py -v
pytest tests/test_experiments.py -v
```

**Common Development Tasks:**

1. **Adding a New API Endpoint**:
   - Add route handler in `api.py`
   - Define Pydantic models for request/response
   - Add contract test in `test_contract_api_frontend.py`
   - Update `frontend/src/lib/api.ts`

2. **Modifying Database Schema**:
   - Update SQLAlchemy models in `db.py`
   - Create migration: `alembic revision --autogenerate`
   - Review and test migration
   - Update frontend types if needed

3. **Adding a New Discovery Source**:
   - Create client module (e.g., `reddit_client.py`)
   - Add configuration to `config.py`
   - Integrate into `pipeline_discovery.py`
   - Add tests and documentation

**Resources:**

- API Documentation: `docs/API.md`
- Deployment Guide: `docs/DEPLOYMENT.md`
- Operations Guide: `docs/OPERATIONS.md`
- Troubleshooting: `docs/TROUBLESHOOTING.md`

---

## 🎨 Frontend Engineer Onboarding

### Day 1: Setup & Tech Stack

**Prerequisites:**

- Node.js 18+ (LTS)
- npm or yarn
- Modern browser with DevTools

**Setup Steps:**

```bash
cd frontend

# 1. Install dependencies
npm install

# 2. Start dev server
npm run dev
# Opens http://localhost:5173

# 3. Run type checking
npm run typecheck

# 4. Run linting
npm run lint
```

**Tech Stack:**

- **Framework**: React 18 with TypeScript
- **Build Tool**: Vite 7
- **Styling**: Tailwind CSS
- **UI Components**: Radix UI primitives
- **Data Fetching**: TanStack Query (React Query)
- **Tables**: TanStack Table
- **Charts**: Recharts
- **Routing**: React Router DOM
- **Error Tracking**: Sentry

**Project Structure:**

```
frontend/src/
├── api/           # API client functions (TanStack Query)
├── components/    # Reusable UI components
├── pages/         # Page components (routes)
├── hooks/         # Custom React hooks
├── lib/
│   ├── api.ts     # API client with fetch wrappers
│   ├── types.ts   # TypeScript types (must match backend)
│   └── utils.ts   # Utility functions
└── App.tsx        # Main application component
```

**Key Concepts:**

1. **Type Safety**: All API responses have TypeScript types that match backend Pydantic models
2. **Data Fetching**: Use TanStack Query hooks for all API calls (caching, refetching, etc.)
3. **Component Structure**: Functional components with hooks (no class components)
4. **Styling**: Utility-first with Tailwind CSS

**First Tasks:**

- [ ] Explore `/discoveries` page (main dashboard)
- [ ] Review `src/lib/types.ts` (TypeScript types)
- [ ] Check `src/api/` (API client functions)
- [ ] Run `npm run build` (production build)
- [ ] Open browser DevTools, check Network tab

### Day 2: Development Workflow

**Adding a New Feature:**

1. **Create Types** (`src/lib/types.ts`):

   ```typescript
   export interface Discovery {
     id: string;
     title: string;
     score: number;
     // ... must match backend Pydantic model
   }
   ```

2. **Create API Client** (`src/api/discoveries.ts`):

   ```typescript
   export function useDiscoveries(minScore: number = 80) {
     return useQuery({
       queryKey: ['discoveries', minScore],
       queryFn: () => api.get<Discovery[]>(`/discoveries?min_score=${minScore}`)
     });
   }
   ```

3. **Create Component** (`src/components/DiscoveryCard.tsx`):

   ```typescript
   export function DiscoveryCard({ discovery }: { discovery: Discovery }) {
     return (
       <div className="bg-white p-4 rounded-lg shadow">
         <h3 className="text-lg font-semibold">{discovery.title}</h3>
         <p className="text-sm text-gray-600">Score: {discovery.score}</p>
       </div>
     );
   }
   ```

4. **Use in Page** (`src/pages/Discoveries.tsx`):

   ```typescript
   export function DiscoveriesPage() {
     const { data, isLoading } = useDiscoveries(80);
     
     if (isLoading) return <div>Loading...</div>;
     
     return (
       <div className="grid grid-cols-1 gap-4">
         {data?.map(d => <DiscoveryCard key={d.id} discovery={d} />)}
       </div>
     );
   }
   ```

**Testing:**

```bash
# Type checking (runs mypy on backend types)
npm run typecheck

# ESLint
npm run lint

# Build (checks for compile errors)
npm run build

# Preview production build
npm run preview
```

**Resources:**

- TanStack Query Docs: <https://tanstack.com/query/latest>
- Radix UI Docs: <https://www.radix-ui.com/>
- Tailwind CSS Docs: <https://tailwindcss.com/>

---

## 📊 Data Scientist Onboarding

### Day 1-2: Understanding the Data Pipeline

**Prerequisites:**

- Python 3.12+ (data science stack: pandas, numpy, scikit-learn)
- Jupyter Notebook or similar
- Understanding of embeddings, similarity metrics, A/B testing

**Setup Steps:**

```bash
# 1. Install with dev dependencies
python -m pip install -e ".[dev]"

# 2. Initialize database with sample data
harvest init-db
harvest seed-discovery-data  # Populate sample artifacts

# 3. Run discovery pipeline
harvest discover fetch --sources arxiv,github --limit 50
harvest discover score
harvest discover top --limit 20
```

**Key Data Science Components:**

1. **Embeddings** (`src/signal_harvester/embeddings.py`):
   - Model: `all-MiniLM-L6-v2` (384 dimensions)
   - Redis-backed caching with 7-day TTL
   - Batch processing (32 batch size)
   - Use cases: Entity resolution, topic similarity, semantic search

2. **Discovery Scoring** (`src/signal_harvester/discovery_scoring.py`):
   - Weighted scoring algorithm:
     - Novelty (35%): How unique the content is
     - Emergence (30%): Growth velocity of related topics
     - Obscurity (20%): Inverse popularity (find hidden gems)
     - Cross-source (10%): Multi-source corroboration
     - Expert signal (5%): Engagement from known researchers
   - Recency decay: 14-day half-life

3. **Identity Resolution** (`src/signal_harvester/identity_resolution.py`):
   - Multi-field weighted matching:
     - Name similarity (50%): Embedding-based
     - Affiliation (30%): Institution matching
     - Domain (15%): Homepage URL
     - Accounts (5%): Social handles
   - Target: >90% precision (validated via test suite)

4. **Topic Evolution** (`src/signal_harvester/topic_evolution.py`):
   - Lifecycle tracking: Emergence, merge, split, decline
   - Coverage: 95.2% of artifacts assigned to topics
   - Growth prediction with confidence intervals

### Day 3-5: Experimentation & Analysis

**A/B Testing Workflow:**

```bash
# 1. Annotate ground truth
harvest annotate --import ground_truth_labels.csv

# 2. Run baseline experiment
harvest backtest --days 7 --experiment baseline_v1 --metrics

# 3. Modify scoring weights in config/settings.yaml
# Edit: weights.discovery.novelty from 0.35 to 0.40

# 4. Run variant experiment
harvest backtest --days 7 --experiment high_novelty_v1 --metrics

# 5. Compare results
harvest backtest --compare 1  # Compare to baseline (experiment ID 1)
```

**Data Exploration:**

```python
import sqlite3
import pandas as pd

# Connect to database
conn = sqlite3.connect('var/signal_harvester.db')

# Load discoveries
discoveries = pd.read_sql("""
    SELECT id, title, source, score, created_at
    FROM artifacts
    WHERE score >= 80
    ORDER BY score DESC
    LIMIT 100
""", conn)

# Load topics
topics = pd.read_sql("""
    SELECT name, description, trend, confidence
    FROM topics
    ORDER BY confidence DESC
""", conn)

# Load experiment results
experiments = pd.read_sql("""
    SELECT e.name, r.precision, r.recall, r.f1_score, r.accuracy
    FROM experiments e
    JOIN experiment_runs r ON e.id = r.experiment_id
    ORDER BY r.created_at DESC
""", conn)

# Analyze score distribution
discoveries['score'].describe()

# Plot score distribution
import matplotlib.pyplot as plt
discoveries['score'].hist(bins=20)
plt.xlabel('Discovery Score')
plt.ylabel('Count')
plt.show()
```

**Metrics Analysis:**

```python
from signal_harvester.experiment import calculate_metrics

# Example: Calculate precision/recall
tp = 45  # True positives
fp = 5   # False positives
tn = 30  # True negatives
fn = 10  # False negatives

metrics = calculate_metrics(tp, fp, tn, fn)
print(f"Precision: {metrics.precision:.3f}")
print(f"Recall: {metrics.recall:.3f}")
print(f"F1 Score: {metrics.f1_score:.3f}")
print(f"Accuracy: {metrics.accuracy:.3f}")
```

**Common Analysis Tasks:**

1. **Evaluate Scoring Algorithm**:
   - Label 100+ discoveries (true positive, false positive, false negative)
   - Run backtest with different weight configurations
   - Compare precision/recall/F1 metrics
   - Deploy best-performing variant

2. **Analyze Topic Trends**:
   - Query `topics` table for emerging topics (trend = 'emerging')
   - Compute topic similarity matrix using embeddings
   - Identify topic merges/splits over time
   - Forecast topic growth

3. **Entity Resolution Quality**:
   - Review merged entities for false positives
   - Adjust similarity thresholds and field weights
   - Run precision test suite
   - Monitor merge statistics

**Resources:**

- Experiment Framework: `docs/EXPERIMENTS.md`
- Embeddings Guide: `docs/OPERATIONS.md` (Enhanced Embeddings section)
- Cross-Source Corroboration: `docs/CROSS_SOURCE_CORROBORATION.md`

---

## 🛠️ Platform Operator Onboarding

### Day 1: Deployment & Monitoring

**Prerequisites:**

- Docker & Docker Compose
- Basic Linux/Unix skills
- Understanding of REST APIs
- Monitoring tools (curl, jq, grep)

**Setup Steps:**

```bash
# 1. Clone and configure
git clone https://github.com/your-org/signal-harvester.git
cd signal-harvester
cp .env.example .env
# Edit .env with API keys

# 2. Build and start
docker-compose up -d

# 3. Verify health
curl http://localhost:8000/health

# 4. Check metrics
curl http://localhost:8000/metrics | jq

# 5. Run migrations
docker-compose exec signal-harvester harvest migrate
```

**Daily Monitoring Checklist:**

See `docs/OPERATIONS.md` for comprehensive daily/weekly/monthly checklists.

**Morning (5 min):**

```bash
# System health
curl http://localhost:8000/health

# Check overnight logs
docker-compose logs --since=8h signal-harvester | grep -i error

# Verify metrics
curl http://localhost:8000/metrics | jq '.discoveries_count, .embeddings_cache_hit_rate'
```

**Throughout Day (as needed):**

```bash
# Monitor API response times
docker-compose logs signal-harvester | tail -100 | grep -E "(slow|timeout)"

# Check database size
ls -lh var/signal_harvester.db

# Monitor rate limiting
docker-compose logs signal-harvester | grep "429"
```

**Evening (5 min):**

```bash
# Review statistics
harvest stats

# Verify backups
ls -lt /backups/signal-harvester/ | head

# Check disk space
df -h
```

**Common Operations:**

1. **Restart Services**:

   ```bash
   docker-compose restart signal-harvester
   docker-compose restart scheduler  # If using daemon mode
   ```

2. **View Logs**:

   ```bash
   # Real-time logs
   docker-compose logs -f signal-harvester
   
   # Errors only
   docker-compose logs signal-harvester | grep -i error
   
   # Specific time range
   docker-compose logs --since="2025-11-11T00:00:00" signal-harvester
   ```

3. **Database Backup**:

   ```bash
   # Manual backup
   sqlite3 var/signal_harvester.db ".backup 'var/signal_harvester_backup_$(date +%Y%m%d).db'"
   
   # Verify backup
   sqlite3 var/signal_harvester_backup_20251111.db "SELECT COUNT(*) FROM artifacts;"
   ```

4. **Token Rotation**:

   ```bash
   # Update .env with new tokens
   nano .env
   
   # Restart services
   docker-compose restart signal-harvester
   
   # Verify new tokens work
   curl http://localhost:8000/health
   ```

**Incident Response:**

See `docs/TROUBLESHOOTING.md` for detailed procedures.

**Quick Fixes:**

- **API not responding**: `docker-compose restart signal-harvester`
- **Database locked**: Check for long-running queries, restart if needed
- **Rate limit errors**: Check X API quota, reduce fetch frequency
- **High memory usage**: Check embedding cache size, consider Redis
- **Disk full**: Prune old snapshots, check database size

**Resources:**

- Operations Guide: `docs/OPERATIONS.md`
- Deployment Guide: `docs/DEPLOYMENT.md`
- Backup Procedures: `docs/BACKUP.md`
- Troubleshooting: `docs/TROUBLESHOOTING.md`

---

## 📈 Product Manager Onboarding

### Day 1: Understanding Capabilities

**What Signal Harvester Does:**

Signal Harvester is a dual-mode intelligence platform that:

1. **Legacy Mode** (Social Media Signals):
   - Monitors X (Twitter) for customer signals
   - Classifies signals by category (outage, security, bug, question, praise)
   - Scores signals by urgency and engagement
   - Sends Slack notifications for high-priority signals

2. **Phase One** (Deep Tech Discovery):
   - Aggregates research artifacts from arXiv, GitHub, Semantic Scholar, X, Facebook, LinkedIn
   - Scores discoveries by novelty, emergence, obscurity, cross-source corroboration
   - Tracks researcher profiles and organizational networks
   - Identifies trending research topics and emerging fields
   - Builds citation graphs linking papers, code, and discussions

**Key Metrics:**

Access via API or dashboard:

```bash
# Overall statistics
curl http://localhost:8000/metrics | jq

# Top discoveries (last 48 hours)
curl "http://localhost:8000/discoveries?min_score=80&hours_back=48" | jq

# Trending topics
curl http://localhost:8000/topics/trending | jq

# Experiment performance
curl http://localhost:8000/experiments | jq
```

**Key Performance Indicators (KPIs):**

1. **Discovery Quality**:
   - Precision: >80% (% of discoveries that are truly valuable)
   - Recall: >70% (% of valuable discoveries caught)
   - F1 Score: >0.75 (balanced metric)

2. **Coverage**:
   - Topic coverage: 95.2% (artifacts assigned to topics)
   - Source diversity: 5+ sources (arXiv, GitHub, X, Facebook, LinkedIn)
   - Entity resolution: >90% precision

3. **Performance**:
   - API latency: <500ms p95
   - Embedding cache hit rate: >80%
   - Database query time: <100ms p95

4. **Operational**:
   - Uptime: >99.9%
   - Migration success rate: 100%
   - Test pass rate: 100%

**User Stories & Features:**

1. **Research Discovery**:
   - As a researcher, I want to discover emerging research papers in my field
   - As a lab director, I want to identify trending research topics
   - As a grant officer, I want to find high-impact researchers

2. **Entity Tracking**:
   - As a recruiter, I want to track prolific researchers across platforms
   - As a collaboration manager, I want to find researchers with overlapping interests
   - As a competitive analyst, I want to monitor competitor research output

3. **Topic Analysis**:
   - As a strategist, I want to identify emerging research areas before they become mainstream
   - As a portfolio manager, I want to understand topic merge/split dynamics
   - As a funding officer, I want to forecast topic growth

**Dashboard Access:**

```bash
# Start frontend
cd frontend
npm run dev
# Open http://localhost:5173

# Key pages:
# - /discoveries - Top discoveries dashboard
# - /topics - Trending topics
# - /entities - Researcher profiles
# - /experiments - A/B test results
```

**Customization:**

Adjust scoring weights in `config/settings.yaml`:

```yaml
app:
  weights:
    discovery:
      novelty: 0.40        # Increase to favor new ideas
      emergence: 0.30      # Increase to favor fast-growing topics
      obscurity: 0.15      # Increase to find hidden gems
      cross_source: 0.10   # Increase to favor corroborated content
      expert_signal: 0.05  # Increase to favor expert engagement
```

**Common Requests:**

1. **Add New Data Source**: Contact engineering team, provide API documentation
2. **Adjust Scoring**: Modify `config/settings.yaml`, run A/B test via backtesting
3. **Export Data**: Use API endpoints (`/discoveries`, `/topics`, `/entities`)
4. **Custom Reports**: SQL queries against SQLite database or API integration

**Resources:**

- User Guide: `docs/USER_GUIDE.md`
- API Documentation: `docs/API.md`
- API Examples: `docs/API_EXAMPLES.md`
- Architecture Overview: `ARCHITECTURE_AND_READINESS.md`

---

## 📚 General Resources

### Documentation

- **[ARCHITECTURE_AND_READINESS.md](../ARCHITECTURE_AND_READINESS.md)**: Master development plan, roadmap, verification procedures
- **[README.md](../README.md)**: Project overview, quick start, features
- **[docs/OPERATIONS.md](OPERATIONS.md)**: Daily operations, monitoring, Phase Two features
- **[docs/DEPLOYMENT.md](DEPLOYMENT.md)**: Production deployment, configuration, migrations
- **[docs/API.md](API.md)**: REST API reference
- **[docs/API_EXAMPLES.md](API_EXAMPLES.md)**: API usage examples
- **[docs/EXPERIMENTS.md](EXPERIMENTS.md)**: Backtesting and A/B testing framework
- **[docs/CROSS_SOURCE_CORROBORATION.md](CROSS_SOURCE_CORROBORATION.md)**: Relationship detection, citation graphs
- **[docs/TROUBLESHOOTING.md](TROUBLESHOOTING.md)**: Common errors, debugging, log analysis

### Communication Channels

- **Engineering**: Slack #signal-harvester-dev
- **Data Science**: Slack #signal-harvester-experiments
- **Operations**: Slack #signal-harvester-ops
- **Product**: Slack #signal-harvester-product
- **Incidents**: Slack #signal-harvester-incidents

### Getting Help

1. **Check Documentation**: Start with `docs/TROUBLESHOOTING.md`
2. **Search Issues**: GitHub Issues for known problems
3. **Ask Team**: Post in relevant Slack channel
4. **Create Issue**: [GitHub Issues](https://github.com/your-org/signal-harvester/issues)
5. **Contact Support**: <signal-harvester-support@your-org.com>

---

## ✅ Onboarding Checklist

### All Roles

- [ ] Read `README.md` and `ARCHITECTURE_AND_READINESS.md`
- [ ] Clone repository and set up environment
- [ ] Run `make verify-all` successfully
- [ ] Access Slack channels
- [ ] Introduce yourself to the team

### Role-Specific

#### Backend Engineers

- [ ] Complete backend onboarding (Days 1-3)
- [ ] Run full test suite (100+ tests passing)
- [ ] Review API contracts and database schema
- [ ] Make first contribution (fix, feature, or docs)

#### Frontend Engineers

- [ ] Complete frontend onboarding (Days 1-2)
- [ ] Build and run frontend locally
- [ ] Review TypeScript types and API client
- [ ] Make first UI contribution

#### Data Scientists

- [ ] Complete data science onboarding (Days 1-5)
- [ ] Run discovery pipeline and generate sample data
- [ ] Perform data exploration in Jupyter
- [ ] Run baseline experiment and review metrics

#### Platform Operators

- [ ] Complete operator onboarding (Day 1)
- [ ] Deploy to staging environment
- [ ] Configure monitoring and alerts
- [ ] Perform backup/restore drill

#### Product Managers

- [ ] Complete PM onboarding (Day 1)
- [ ] Access dashboard and review metrics
- [ ] Understand key features and capabilities
- [ ] Define success metrics and KPIs

---

## 📝 Feedback

Help us improve this guide! If you have suggestions, corrections, or additional topics to cover:

1. **Create Issue**: [GitHub Issues](https://github.com/your-org/signal-harvester/issues)
2. **Submit PR**: Edit `docs/TEAM_GUIDE.md` and submit pull request
3. **Slack Feedback**: Post in #signal-harvester-docs

**Last Updated**: November 11, 2025  
**Maintainer**: Signal Harvester Team
