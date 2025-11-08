# Signal Harvester - Beta Quick Reference

## 🚀 Quick Start (Beta)

### Deploy Beta Environment
```bash
cd signal-harvester

# 1. Copy beta environment file
cp .env.example .env.beta

# 2. Edit .env.beta with your configuration
nano .env.beta

# 3. Deploy with Docker
docker-compose -f docker-compose.yml up -d

# 4. Initialize database
docker-compose exec signal-harvester harvest init-db

# 5. Create beta invite for yourself
docker-compose exec signal-harvester harvest beta-invite your-email@example.com --name "Your Name"
```

### Run Beta Locally (Development)
```bash
# Terminal 1: Backend
cd signal-harvester
source .env.beta
harvest-api

# Terminal 2: Frontend
cd signal-harvester/frontend
npm run dev

# Terminal 3: Pipeline (optional)
harvest daemon --interval 300
```

---

## 📊 Monitoring

### Check Health
```bash
# API Health
curl http://localhost:8000/health

# Frontend
curl http://localhost:5173

# Docker containers
docker-compose ps
```

### View Logs
```bash
# All services
docker-compose logs -f

# Backend only
docker-compose logs -f signal-harvester

# Structured JSON logs (if configured)
docker-compose logs -f signal-harvester | jq '.'
```

### Error Tracking
- **Sentry**: https://sentry.io/organizations/your-org/projects/signal-harvester/
- **Alerts**: Check email/Slack for error notifications
- **Logs**: `docker-compose logs -f`

---

## 👥 Beta User Management

### Create Invite
```bash
# Create single invite
docker-compose exec signal-harvester harvest beta-invite user@example.com --name "User Name"

# Create multiple invites (from file)
while read email name; do
  docker-compose exec signal-harvester harvest beta-invite "$email" --name "$name"
done < beta-users.txt
```

### List Beta Users
```bash
# All users
docker-compose exec signal-harvester harvest beta-list

# Filter by status
docker-compose exec signal-harvester harvest beta-list --status active
docker-compose exec signal-harvester harvest beta-list --status pending
```

### Invite Email Template
```
Subject: You're invited to Signal Harvester Beta! 🎉

Hi {name},

You've been invited to the private beta of Signal Harvester!

Signal Harvester helps you collect and analyze social signals from X (Twitter) 
to identify customer issues, feature requests, and churn risks.

Get started in 3 simple steps:

1. Visit: https://beta.signal-harvester.com
2. Enter invite code: {invite_code}
3. Follow the onboarding tutorial

Your invite code: {invite_code}

Need help? Reply to this email or join our Slack: https://slack.signal-harvester.com

Happy signal hunting!
The Signal Harvester Team
```

---

## 🧪 Testing Checklist

### Pre-Beta Launch Tests

**API Tests** (Run these commands)
```bash
# Test API health
curl http://localhost:8000/health

# Test authentication (should fail without key)
curl http://localhost:8000/top

# Test with API key
curl -H "X-API-Key: $HARVEST_API_KEY" http://localhost:8000/top

# Test pipeline endpoint
curl -X POST -H "X-API-Key: $HARVEST_API_KEY" http://localhost:8000/refresh

# Test tweet endpoint (replace with actual ID)
curl -H "X-API-Key: $HARVEST_API_KEY" http://localhost:8000/tweet/123456
```

**Frontend Tests**
```bash
cd frontend

# Run type check
npm run typecheck

# Run linter
npm run lint

# Run tests (if you have unit tests)
npm test

# Build for production
npm run build

# Run E2E tests (if using Cypress)
npm run test:e2e:headless
```

**Integration Tests**
```bash
# Run full test suite
cd ..
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src/signal_harvester --cov-report=html

# Open coverage report
open htmlcov/index.html
```

---

## 🔧 Common Commands

### Database Operations
```bash
# Backup database
docker-compose exec signal-harvester sqlite3 /app/var/app.db ".backup /app/data/backup.db"

# Restore database
docker-compose exec signal-harvester cp /app/data/backup.db /app/var/app.db

# Run migrations
docker-compose exec signal-harvester alembic upgrade head

# Create new migration
docker-compose exec signal-harvester alembic revision --autogenerate -m "description"
```

### Pipeline Operations
```bash
# Run full pipeline once
docker-compose exec signal-harvester harvest pipeline

# Run pipeline in daemon mode
docker-compose exec signal-harvester harvest daemon --interval 300

# Fetch only
docker-compose exec signal-harvester harvest fetch

# Analyze only
docker-compose exec signal-harvester harvest analyze

# Score only
docker-compose exec signal-harvester harvest score

# Notify only
docker-compose exec signal-harvester harvest notify
```

### Snapshot Operations
```bash
# Create snapshot
docker-compose exec signal-harvester harvest snapshot --name "daily-backup"

# List snapshots
docker-compose exec signal-harvester harvest stats

# Prune old snapshots
docker-compose exec signal-harvester harvest prune --keep 10

# Retain by policy
docker-compose exec signal-harvester harvest retain

# Enforce quota
docker-compose exec signal-harvester harvest quota --max-size 1GB
```

### Data Operations
```bash
# Export to CSV
docker-compose exec signal-harvester harvest export --file /app/data/export.csv

# Show statistics
docker-compose exec signal-harvester harvest stats

# Verify integrity
docker-compose exec signal-harvester harvest verify

# Check quotas
docker-compose exec signal-harvester harvest quota
```

---

## 📈 Analytics & Metrics

### Key Metrics to Monitor

**Technical Metrics**
```bash
# API request rates
docker-compose logs -f signal-harvester | grep "GET\|POST\|PUT\|DELETE"

# Error rates
docker-compose logs -f signal-harvester | grep "ERROR\|500\|Traceback"

# Database size
docker-compose exec signal-harvester ls -lh /app/var/app.db

# Disk usage
docker-compose exec signal-harvester du -sh /app/data /app/var
```

**User Metrics** (via analytics dashboard)
- Daily active users
- Feature adoption rates
- Most used API endpoints
- Average session duration
- Error rates per user

### Prometheus Metrics
```bash
# View metrics endpoint
curl http://localhost:8000/metrics

# Key metrics to watch
# - http_requests_total
# - http_request_duration_seconds
# - pipeline_runs_total
# - pipeline_duration_seconds
# - tweets_fetched_total
# - tweets_analyzed_total
# - notifications_sent_total
```

---

## 🐛 Troubleshooting

### Common Issues

**Problem**: API won't start
```bash
# Check logs
docker-compose logs signal-harvester

# Check if port is in use
lsof -i :8000

# Check environment variables
docker-compose exec signal-harvester env | grep -E "X_BEARER|OPENAI|ANTHROPIC"
```

**Problem**: Frontend can't connect to API
```bash
# Check CORS settings
cat config/settings.yaml

# Test API directly
curl -H "X-API-Key: $HARVEST_API_KEY" http://localhost:8000/health

# Check browser console for CORS errors
# Check network tab for failed requests
```

**Problem**: Pipeline not fetching tweets
```bash
# Check X API credentials
echo $X_BEARER_TOKEN | wc -c  # Should be ~100 chars

# Test X API directly
curl -H "Authorization: Bearer $X_BEARER_TOKEN" \
  "https://api.twitter.com/2/tweets/search/recent?query=test&max_results=10"

# Check rate limits
docker-compose exec signal-harvester harvest quota
```

**Problem**: LLM analysis failing
```bash
# Check API keys
echo $OPENAI_API_KEY | wc -c  # Should be ~50 chars
echo $ANTHROPIC_API_KEY | wc -c  # Should be ~100 chars

# Test OpenAI API
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"

# Check logs for specific errors
docker-compose logs -f signal-harvester | grep -i "openai\|anthropic\|llm\|analysis"
```

**Problem**: Database locked errors
```bash
# Check for long-running queries
docker-compose exec signal-harvester sqlite3 /app/var/app.db ".timer on" "SELECT * FROM tweets LIMIT 1"

# Enable WAL mode if not already enabled
docker-compose exec signal-harvester sqlite3 /app/var/app.db "PRAGMA journal_mode=WAL;"

# Check for zombie connections
lsof | grep app.db
```

**Problem**: Slack notifications not working
```bash
# Test Slack webhook
curl -X POST -H 'Content-type: application/json' \
  --data '{"text":"Test from Signal Harvester"}' \
  $SLACK_WEBHOOK_URL

# Check logs for Slack errors
docker-compose logs -f signal-harvester | grep -i "slack\|webhook\|notification"

# Verify webhook URL format (should start with https://hooks.slack.com/services/)
echo $SLACK_WEBHOOK_URL
```

---

## 🆘 Emergency Procedures

### Rollback Deployment
```bash
# Stop current deployment
docker-compose down

# Restore previous version (example with git)
git checkout previous-tag

# Re-deploy
docker-compose up -d --build

# Restore database if needed
docker-compose exec signal-harvester cp /app/data/backup-before-deploy.db /app/var/app.db
```

### Reset Database
```bash
# WARNING: This will delete all data!
docker-compose down
rm var/app.db
docker-compose up -d
docker-compose exec signal-harvester harvest init-db
```

### Clear Cache/Reset State
```bash
# Restart services
docker-compose restart signal-harvester

# Clear temporary data
docker-compose exec signal-harvester rm -rf /app/data/tmp/

# Reset API rate limits (if using Redis)
docker-compose exec signal-harvester redis-cli FLUSHALL
```

### Scale Up for Load
```bash
# Increase workers for API
docker-compose up -d --scale signal-harvester=3

# Or modify docker-compose.yml
# Change: replicas: 3 under deploy section
```

---

## 📚 Additional Resources

### Documentation
- [Full Deployment Guide](docs/DEPLOYMENT.md)
- [Operations Guide](docs/OPERATIONS.md)
- [API Documentation](http://localhost:8000/docs)
- [Architecture Overview](docs/API.md)

### External Services
- **Sentry**: Error tracking and performance monitoring
- **Slack**: Team notifications and alerts
- **X API**: Twitter data source
- **OpenAI/Anthropic**: LLM analysis providers

### Support
- GitHub Issues: https://github.com/your-org/signal-harvester/issues
- Slack Channel: #signal-harvester-support
- Email: support@signal-harvester.com

---

## ✅ Beta Launch Day Checklist

### Morning (2 hours before)
- [ ] All services healthy: `docker-compose ps`
- [ ] No critical errors in logs: `docker-compose logs --tail=20`
- [ ] API responding: `curl http://localhost:8000/health`
- [ ] Frontend loading: Open in browser
- [ ] Database backed up: `docker-compose exec signal-harvester harvest snapshot`
- [ ] Sentry configured and tested
- [ ] Analytics working
- [ ] Invite emails ready to send

### Launch (0 hour)
- [ ] Send first batch of invites (10 users)
- [ ] Monitor Sentry for errors
- [ ] Monitor API logs
- [ ] Check analytics real-time
- [ ] Post in Slack #beta-launch channel

### Post-Launch (1 hour after)
- [ ] Verify users can sign up
- [ ] Check error rates < 1%
- [ ] Verify API response times < 200ms
- [ ] Confirm Slack notifications working
- [ ] Respond to any immediate user issues
- [ ] Document any issues in launch log

### End of Day
- [ ] Review all metrics
- [ ] Check user feedback
- [ ] Document lessons learned
- [ ] Plan next day's priorities

---

## 🎉 Success Indicators

### Green Flags ✅
- Error rate < 1%
- API response time < 200ms p95
- Users completing onboarding
- Positive feedback in surveys
- Feature adoption > 60%

### Red Flags 🚨
- Error rate > 5%
- API response time > 500ms p95
- Users stuck on onboarding
- Negative feedback
- Low feature adoption (< 20%)

---

**Remember**: This is a beta! It's okay if everything isn't perfect. The goal is to learn and improve.

**Beta Support**: #signal-harvester-beta on Slack
**Emergency Contact**: Your phone number here