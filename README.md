# Signal Harvester

[![Tests](https://github.com/Bwillia13x/_deeptech/actions/workflows/test.yml/badge.svg)](https://github.com/Bwillia13x/_deeptech/actions/workflows/test.yml)
[![Lint](https://github.com/Bwillia13x/_deeptech/actions/workflows/lint.yml/badge.svg)](https://github.com/Bwillia13x/_deeptech/actions/workflows/lint.yml)
[![Frontend](https://github.com/Bwillia13x/_deeptech/actions/workflows/frontend.yml/badge.svg)](https://github.com/Bwillia13x/_deeptech/actions/workflows/frontend.yml)
[![Security](https://github.com/Bwillia13x/_deeptech/actions/workflows/security.yml/badge.svg)](https://github.com/Bwillia13x/_deeptech/actions/workflows/security.yml)
[![Docker](https://github.com/Bwillia13x/_deeptech/actions/workflows/deploy.yml/badge.svg)](https://github.com/Bwillia13x/_deeptech/actions/workflows/deploy.yml)

Signal Harvester is a production-ready (beta) social and research intelligence platform that:

- Harvests signals from X (Twitter) and adjacent sources.
- Uses LLM-assisted classification and scoring to identify high-value items:
  - Product feedback, bugs, outages, churn risk, competitors.
  - Deep-tech discoveries, research fronts, influential entities (with full artifact classifications stored for auditing).
- Surfaces prioritized, explainable signals for teams via API, CLI, static reports, and a React dashboard.
For the canonical, up-to-date architecture, readiness posture, and prioritized roadmap, see:
- [`signal-harvester/ARCHITECTURE_AND_READINESS.md`](signal-harvester/ARCHITECTURE_AND_READINESS.md:1)

For a single pass/fail verification of the current implementation and docs, run from the repository root:

- `cd signal-harvester && make verify-all` (see [`signal-harvester/Makefile`](signal-harvester/Makefile:7))

## Features

- **Fetch**: Collect tweets from X/Twitter API with configurable search queries
- **Analyze**: LLM-powered content analysis with support for OpenAI, Anthropic, and heuristic fallback
- **Score**: Advanced salience scoring algorithm with configurable weights and recency attenuation
- **Notify**: Slack notifications for high-priority items
- **API**: RESTful API with authentication, rate limiting, and monitoring
- **Frontend**: Modern React + TypeScript interface with real-time updates
- **Observability**: Prometheus metrics, structured logging, and Sentry error tracking
- **Docker**: Production-ready containerization with multi-stage builds

## Architecture

- **Backend**: Python 3.12+ FastAPI with SQLite database (primary supported storage)
- **Frontend**: React 18 + TypeScript + Vite + TailwindCSS
- **Database**: SQLite with Alembic migrations (PostgreSQL requires a manual migration and is not enabled by default)
- **Note**: If you still want PostgreSQL, the `scripts/migrate_sqlite_to_postgresql.py` script and related docs walk through the manual migration, but the app itself only runs against SQLite at this time.
- **Container**: Docker multi-stage builds with docker-compose
- **LLM Integration**: OpenAI, Anthropic, and xAI providers
- **Monitoring**: Prometheus metrics, structured JSON logging, Sentry integration

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 18+
- Docker & Docker Compose (optional)

### Installation

1. **Clone and setup**

   ```bash
   git clone https://github.com/Bwillia13x/_deeptech.git
   cd _deeptech/signal-harvester
   ```

2. **Backend setup**

   ```bash
   # Install Python dependencies
   python -m pip install -e ".[dev]"
   
   # Copy environment template
   cp .env.example .env
   
   # Initialize database
   harvest init-db
   ```

3. **Frontend setup**

   ```bash
   cd frontend
   npm install
   cd ..
   ```

4. **Configure API keys**

   Edit `.env` with your credentials:

   ```bash
   # X (Twitter) API
   X_BEARER_TOKEN=your_x_api_bearer_token
   
   # LLM Providers (choose one or more)
   OPENAI_API_KEY=your_openai_api_key  # Required for research discovery classification
   OPENAI_MODEL=gpt-4o-mini
   ANTHROPIC_API_KEY=your_anthropic_api_key
   
   # Optional: Error tracking
   SENTRY_DSN=your_sentry_dsn
   
   # Optional: Slack notifications
   SLACK_WEBHOOK_URL=your_slack_webhook_url
   ```

5. **Configure search queries**

   Edit `config/settings.yaml` to define what to monitor:

   ```yaml
   queries:
     bugs:
       query: "your_app_name bug OR issue OR problem"
       enabled: true
     feedback:
       query: "your_app_name feedback OR suggestion"
       enabled: true
   ```

### Running the Application

#### Option 1: Development (Recommended)

```bash
# Terminal 1: Start API server
harvest-api --reload

# Terminal 2: Start frontend dev server
cd frontend && npm run dev

# Terminal 3: Run pipeline manually
harvest pipeline
```

#### Option 2: Docker Production

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f signal-harvester
```

#### Option 3: CLI Operations

```bash
# Run full pipeline
harvest pipeline

# Individual steps
harvest fetch
harvest analyze
harvest score
harvest notify

# View top signals
harvest top --limit 20

# Browse deep-tech discoveries (table or JSON)
harvest discoveries --min-score 85 --limit 25
harvest discoveries --output json --limit 10 | jq '.'

# Export data
harvest export --format json --output signals.json
```

## API Documentation

### Authentication

Most endpoints require an API key passed in the `X-API-Key` header:

```bash
export HARVEST_API_KEY=your-secret-key
```

### Key Endpoints

#### Legacy Tweet Endpoints

- `GET /top` - Get top-scored tweets
- `GET /tweet/{id}` - Get specific tweet details
- `POST /refresh` - Run the harvest pipeline

#### Modern Signals & Snapshots API

- `GET /signals` - List signals with pagination and filtering
- `GET /signals/stats` - Get signal statistics
- `GET /signals/{id}` - Get specific signal
- `POST /signals` - Create new signal
- `PATCH /signals/{id}` - Update signal
- `DELETE /signals/{id}` - Delete signal
- `GET /snapshots` - List snapshots
- `GET /snapshots/{id}` - Get specific snapshot

#### Bulk Operations

- `POST /signals/bulk/status` - Bulk update signal status
- `POST /signals/bulk/delete` - Bulk delete signals
- `GET /bulk-jobs/{id}` - Get bulk job status
- `GET /bulk-jobs/{id}/stream` - SSE stream for job progress
- `POST /bulk-jobs/{id}/cancel` - Cancel bulk job

#### Monitoring & Documentation

- `GET /health` - Health check endpoint
- `GET /metrics` - Application metrics (JSON)
- `GET /metrics/prometheus` - Prometheus metrics
- `GET /docs` - Interactive API documentation (Swagger UI)
- `GET /redoc` - ReDoc API documentation

See [docs/API.md](docs/API.md) for complete API documentation.

### Rate Limiting

API endpoints are rate-limited to 10 requests per minute per client. Configure via:

```bash
export RATE_LIMITING_ENABLED=false  # Disable rate limiting
export CORS_ORIGINS="https://yourapp.com"  # Restrict CORS
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `X_BEARER_TOKEN` | X/Twitter API bearer token | Required |
| `OPENAI_API_KEY` | OpenAI API key | Optional |
| `ANTHROPIC_API_KEY` | Anthropic API key | Optional |
| `DATABASE_PATH` | SQLite database path | `var/app.db` |
| `HARVEST_API_KEY` | API authentication key | Optional |
| `SLACK_WEBHOOK_URL` | Slack notifications webhook | Optional |
| `SENTRY_DSN` | Sentry error tracking DSN | Optional |
| `LOG_LEVEL` | Logging level (DEBUG/INFO/WARNING/ERROR) | `INFO` |
| `LOG_FORMAT` | Log format (text/json) | `text` |

### Settings File

`config/settings.yaml` provides detailed configuration:

```yaml
app:
  database_path: "var/app.db"
  fetch:
    max_results: 100
    lang: "en"
  llm:
    provider: "openai"  # openai, anthropic, dummy
    model: "gpt-4o-mini"  # Required for research discovery pipeline
    temperature: 0.0
  scoring:
    weights:
      likes: 1.0
      retweets: 3.0
      replies: 2.0
      quotes: 2.5
      urgency: 4.0
      base: 1.0
      cap: 100.0
      recency_half_life_hours: 24.0
      category_boosts:
        outage: 2.0
        security: 1.8
        bug: 1.3
      sentiment_positive: 1.0
      sentiment_negative: 1.2
      sentiment_neutral: 0.9
```

## Development

### Running Tests

Tests require the `PYTHONPATH` to be set to include the `src` directory, or you can use the provided make targets:

```bash
# Recommended: Use make targets (handles PYTHONPATH automatically)
make test           # Run all tests
make verify-all     # Run complete verification suite (lint, format, test, frontend build)

# Or manually with PYTHONPATH
PYTHONPATH=src pytest tests/ -v

# Run specific test file
PYTHONPATH=src pytest tests/test_api_signals.py -v

# Run with coverage
PYTHONPATH=src pytest --cov=signal_harvester tests/
```

### Code Quality

```bash
# Lint and format
make lint
make format

# Type checking
mypy src/

# Run tests
pytest

# Test coverage
pytest --cov=signal_harvester
```

### Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback migration
alembic downgrade -1
```

### Adding New LLM Providers

1. Implement provider class in `src/signal_harvester/llm_client.py`
2. Add configuration options to `config/settings.yaml`
3. Update `get_llm_client()` function
4. Add tests in `tests/test_llm_client.py`

## Deployment

For deployment, Docker, and operations details, use this README as an entrypoint and refer to:

- [`signal-harvester/docs/DEPLOYMENT.md`](signal-harvester/docs/DEPLOYMENT.md:1) for deployment specifics.
- [`signal-harvester/docs/OPERATIONS.md`](signal-harvester/docs/OPERATIONS.md:1) for runbook guidance.
- [`signal-harvester/docs/BACKUP.md`](signal-harvester/docs/BACKUP.md:1) for backup and restore.
- [`signal-harvester/docs/API.md`](signal-harvester/docs/API.md:1) and [`signal-harvester/docs/API_EXAMPLES.md`](signal-harvester/docs/API_EXAMPLES.md:1) for API usage.
- [`signal-harvester/docs/USER_GUIDE.md`](signal-harvester/docs/USER_GUIDE.md:1) for user-facing workflows.

These documents are maintained to align with the canonical architecture and readiness view in [`signal-harvester/ARCHITECTURE_AND_READINESS.md`](signal-harvester/ARCHITECTURE_AND_READINESS.md:1). In case of discrepancy, treat statements here and in those docs as historical and defer to the canonical file plus `make verify-all`.

### Production Docker

```bash
# Build and deploy
docker-compose -f docker-compose.yml up -d

# Scale services
docker-compose up -d --scale signal-harvester=3
```

### Environment Setup

- **Development**: Use `harvest serve` for local development
- **Staging**: Use Docker Compose with staging environment variables
- **Production**: Use Docker Swarm/Kubernetes with proper secrets management

### Monitoring

- **Health Checks**: `GET /health` endpoint
- **Metrics**: Prometheus endpoint at `/metrics/prometheus`
- **Logs**: Structured JSON logs in production
- **Error Tracking**: Sentry integration (configure `SENTRY_DSN`)

## Security

- API key authentication for sensitive endpoints
- Rate limiting to prevent abuse
- Input validation and sanitization
- Security headers (HSTS, X-Frame-Options, etc.)
- CORS configuration
- Non-root Docker user
- Environment-based secret management

## Performance

- SQLite with WAL mode for concurrent access
- Database indexes on frequently queried columns
- Connection pooling and timeouts
- Retry logic with exponential backoff for external APIs
- Efficient pagination and filtering
- Prometheus metrics for monitoring

## Troubleshooting

### Common Issues

1. **"X API rate limited"**
   - Reduce fetch frequency in `settings.yaml`
   - Upgrade X API plan for higher limits

2. **"LLM provider failed"**
   - Check API key configuration
   - Verify network connectivity
   - System falls back to heuristic analysis

3. **"Database locked"**
   - Ensure only one pipeline instance runs
   - Check for long-running transactions

4. **"Frontend not connecting"**
   - Verify API server is running
   - Check CORS configuration
   - Ensure proper API key usage

### Debug Mode

```bash
# Enable debug logging
export LOG_LEVEL=DEBUG

# Run with verbose output
harvest pipeline --verbose
```

## Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

### Development Guidelines

- Follow PEP 8 and use ruff for formatting
- Add type hints for all functions
- Write tests for new features
- Update documentation
- Use conventional commit messages

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- X/Twitter for the API access
- OpenAI and Anthropic for LLM services
- FastAPI for the web framework
- React and Vite for the frontend
- Prometheus for metrics collection

## Support

For the living architecture, readiness status, and roadmap, always start with:

- [`signal-harvester/ARCHITECTURE_AND_READINESS.md`](signal-harvester/ARCHITECTURE_AND_READINESS.md:1)
- `cd signal-harvester && make verify-all` as the single health/consistency check.

Historical or external documentation (including older wiki pages) may be outdated; prefer the files in this repository that explicitly reference the canonical architecture document.

---

Built with ❤️ for social media intelligence
