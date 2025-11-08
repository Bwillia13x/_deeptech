# Signal Harvester - Production Deployment Guide

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
```

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

queries:
  - name: "brand_support"
    enabled: true
    query: "(@YourBrand OR #YourBrand) (help OR support OR broken OR down OR bug OR crash) -is:retweet -is:reply lang:en"
  
  - name: "competitor_chatter"
    enabled: false
    query: "(CompetitorA OR CompetitorB) (switch OR alternatives) -is:retweet -is:reply lang:en"
```

## 🐳 Docker Deployment

### Quick Start

1. **Clone and build:**
```bash
git clone <repository-url>
cd signal-harvester
docker build -t signal-harvester .
```

2. **Run with Docker Compose:**
```bash
# Copy environment file
cp .env.example .env
# Edit .env with your API keys

# Start services
docker-compose up -d

# View logs
docker-compose logs -f signal-harvester
```

### Docker Compose Services

- `signal-harvester`: Main API server (port 8000)
- `scheduler`: Optional periodic pipeline runner

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
- [Monitoring Setup](MONITORING.md)
