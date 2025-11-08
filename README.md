# Signal Harvester

A social media intelligence platform that harvests, triages, and scores signals from X (Twitter) using LLM-assisted classification. The system identifies customer signals such as bug reports, churn risks, feature requests, and support issues, then scores them by salience to surface the most important items for business attention.

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

- **Backend**: Python 3.12+ FastAPI with SQLite database
- **Frontend**: React 18 + TypeScript + Vite + TailwindCSS
- **Database**: SQLite with Alembic migrations
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
   OPENAI_API_KEY=your_openai_api_key
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

- `GET /top` - Get top-scored tweets
- `GET /tweet/{id}` - Get specific tweet details
- `POST /refresh` - Run the harvest pipeline
- `GET /health` - Health check endpoint
- `GET /metrics` - Application metrics (JSON)
- `GET /metrics/prometheus` - Prometheus metrics
- `GET /docs` - Interactive API documentation

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
    model: "gpt-4o-mini"
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

- 📖 [Documentation](https://github.com/Bwillia13x/_deeptech/wiki)
- 🐛 [Issue Tracker](https://github.com/Bwillia13x/_deeptech/issues)
- 💬 [Discussions](https://github.com/Bwillia13x/_deeptech/discussions)

---

Built with ❤️ for social media intelligence
