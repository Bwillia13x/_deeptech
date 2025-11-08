# Signal Harvester - Operations Guide

## 📋 Daily Operations Checklist

### 🌅 Morning Check (First thing)

- [ ] **Check system health**
  ```bash
  curl http://localhost:8000/health
  ```
  Should return `"status": "healthy"`

- [ ] **Review overnight pipeline runs**
  ```bash
  docker-compose logs --since=8h signal-harvester
  ```
  Look for errors or warnings

- [ ] **Check metrics**
  ```bash
  curl http://localhost:8000/metrics | jq
  ```
  Verify tweet counts and processing rates

- [ ] **Verify Slack notifications were sent**
  Check your Slack channel for notifications

### 🔄 Throughout the Day

- [ ] **Monitor API response times**
  ```bash
  # Check for slow responses in logs
  docker-compose logs signal-harvester | grep -E "(slow|timeout)"
  ```

- [ ] **Check database size**
  ```bash
  ls -lh var/app.db
  ```
  Should not grow unexpectedly fast

- [ ] **Monitor rate limiting**
  ```bash
  docker-compose logs signal-harvester | grep "429"
  ```
  Occasional 429s are normal, frequent 429s may indicate abuse

- [ ] **Verify snapshot rotation**
  ```bash
  ls -lt snapshots/ | head
  ```
  Should have recent snapshots

### 🌙 Evening Check (End of day)

- [ ] **Review day's statistics**
  ```bash
  harvest stats --db-path var/app.db
  ```

- [ ] **Check for errors**
  ```bash
  docker-compose logs signal-harvester | grep -i error
  ```

- [ ] **Verify backups completed**
  ```bash
  ls -lt /backups/signal-harvester/ | head
  ```

- [ ] **Check disk space**
  ```bash
  df -h
  ```

## 🔧 Common Operations

### Starting the System

```bash
# Start all services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f signal-harvester
```

### Stopping the System

```bash
# Graceful shutdown
docker-compose down

# With volume preservation
docker-compose down --volumes

# Emergency stop
docker-compose kill
```

### Running Manual Pipeline

```bash
# Run full pipeline
docker-compose exec signal-harvester harvest pipeline

# Run specific stages
docker-compose exec signal-harvester harvest fetch
docker-compose exec signal-harvester harvest analyze
docker-compose exec signal-harvester harvest score
docker-compose exec signal-harvester harvest notify

# With custom parameters
docker-compose exec signal-harvester harvest pipeline \
  --notify-threshold 80.0 \
  --notify-limit 10
```

### Database Maintenance

```bash
# Check database integrity
docker-compose exec signal-harvester harvest verify

# Run migrations
docker-compose exec signal-harvester harvest migrate

# Check database stats
docker-compose exec signal-harvester harvest stats

# Vacuum database (reclaim space)
docker-compose exec signal-harvester sqlite3 var/app.db "VACUUM;"
```

### Log Management

```bash
# View real-time logs
docker-compose logs -f signal-harvester

# View last 100 lines
docker-compose logs --tail=100 signal-harvester

# View logs since specific time
docker-compose logs --since="2024-01-01T10:00:00" signal-harvester

# Search for errors
docker-compose logs signal-harvester | grep -i error

# Follow logs with filtering
docker-compose logs -f signal-harvester | grep -E "(error|warning|critical)"
```

### Snapshot Management

```bash
# Create manual snapshot
docker-compose exec signal-harvester harvest snapshot \
  --base-dir ./snapshots \
  --gzip

# List snapshots
docker-compose exec signal-harvester harvest stats

# Prune old snapshots
docker-compose exec signal-harvester harvest prune \
  --base-dir ./snapshots \
  --keep 30 \
  --force

# Retain snapshots by age
docker-compose exec signal-harvester harvest retain \
  --base-dir ./snapshots \
  --keep-age 30d \
  --force
```

## 🚨 Incident Response

### API Down

**Symptoms:** Health check fails, no API response

**Immediate actions:**
1. Check container status: `docker-compose ps`
2. Check logs: `docker-compose logs --tail=50 signal-harvester`
3. Check resources: `docker stats`
4. Restart if needed: `docker-compose restart signal-harvester`

**Common causes:**
- Database locked: Wait 30s and retry
- Out of memory: Check system resources
- Configuration error: Review recent changes

### Database Locked

**Symptoms:** "database is locked" errors in logs

**Immediate actions:**
1. Stop pipeline: `docker-compose stop scheduler`
2. Wait 30 seconds for locks to clear
3. Check active connections: `lsof var/app.db`
4. Restart scheduler: `docker-compose start scheduler`

**Prevention:**
- Reduce pipeline frequency
- Optimize database queries
- Consider WAL mode settings

### Rate Limiting Issues

**Symptoms:** Many 429 responses, legitimate users blocked

**Immediate actions:**
1. Check rate limit logs: `docker-compose logs | grep "429"`
2. Identify source IP: `docker-compose logs | grep "Rate limit"
3. Temporarily disable rate limiting if needed:
   ```bash
   docker-compose exec signal-harvester bash
   export RATE_LIMITING_ENABLED=false
   # Restart API
   ```

**Long-term fix:**
- Adjust rate limits in configuration
- Implement IP whitelisting
- Use Redis for distributed rate limiting

### X API Rate Limit Exceeded

**Symptoms:** "Rate limited (429)" in logs

**Immediate actions:**
1. Pause fetching: `docker-compose stop scheduler`
2. Check X API dashboard for rate limit status
3. Wait for reset (usually 15 minutes)
4. Resume: `docker-compose start scheduler`

**Prevention:**
- Reduce fetch frequency
- Optimize queries to fetch fewer tweets
- Upgrade X API tier if needed

### High Disk Usage

**Symptoms:** Disk full, errors writing to database

**Immediate actions:**
1. Check disk usage: `df -h`
2. Check database size: `ls -lh var/app.db`
3. Check snapshot size: `du -sh snapshots/`
4. Clean old snapshots: `harvest prune --keep 10 --force`
5. Vacuum database: `sqlite3 var/app.db "VACUUM;"`

**Long-term fix:**
- Implement aggressive retention policies
- Move snapshots to object storage
- Increase disk size

### LLM API Errors

**Symptoms:** Analysis failures, "API key not set" errors

**Immediate actions:**
1. Check API key: `echo $OPENAI_API_KEY`
2. Check LLM provider status page
3. Verify API key hasn't expired
4. Switch to fallback provider if needed

**Prevention:**
- Set up multiple LLM providers
- Implement circuit breaker pattern
- Monitor API usage and costs

## 📊 Performance Monitoring

### Key Metrics to Track

1. **Pipeline Execution Time**
   ```bash
   # Time the pipeline
   time docker-compose exec signal-harvester harvest pipeline
   ```

2. **API Response Times**
   ```bash
   # Test API speed
   time curl -H "X-API-Key: $KEY" http://localhost:8000/top?limit=50
   ```

3. **Database Query Performance**
   ```bash
   # Check slow queries
   docker-compose exec signal-harvester sqlite3 var/app.db \
     "SELECT * FROM sqlite_stat1;"
   ```

4. **Memory Usage**
   ```bash
   # Monitor container memory
   docker stats signal-harvester
   ```

### Performance Optimization

**If pipeline is slow:**
- Reduce `max_results` in settings
- Increase analysis batch size
- Check LLM API response times
- Optimize database indexes

**If API is slow:**
- Check database size (may need indexes)
- Review query complexity
- Consider read replicas
- Implement caching

**If database is slow:**
- Run `ANALYZE` on tables
- Check for missing indexes
- Vacuum database
- Consider archiving old data

## 🔐 Security Operations

### Rotating API Keys

1. **Generate new API key:**
   ```bash
   openssl rand -base64 32
   ```

2. **Update environment:**
   ```bash
   # Edit .env
   HARVEST_API_KEY=new_key_here
   ```

3. **Restart service:**
   ```bash
   docker-compose up -d signal-harvester
   ```

4. **Update all clients with new key**

5. **Monitor for old key usage:**
   ```bash
   docker-compose logs | grep "Invalid API key"
   ```

### Updating Secrets

**For X API key rotation:**
1. Update `.env` with new `X_BEARER_TOKEN`
2. Restart scheduler: `docker-compose restart scheduler`
3. Test with manual fetch: `harvest fetch`

**For LLM API keys:**
1. Update `.env` with new API key
2. Restart API: `docker-compose restart signal-harvester`
3. Test with manual analysis: `harvest analyze`

### Security Audit

**Monthly security checks:**
- [ ] Review API access logs
- [ ] Check for unusual rate limiting patterns
- [ ] Verify backup encryption
- [ ] Update dependencies: `pip list --outdated`
- [ ] Review Slack webhook access
- [ ] Check X API usage vs. quota

## 🛠️ Maintenance Tasks

### Daily
- [ ] Monitor health endpoint
- [ ] Review error logs
- [ ] Check disk space
- [ ] Verify notifications sent

### Weekly
- [ ] Review performance metrics
- [ ] Clean up old logs
- [ ] Check for system updates
- [ ] Verify backup completion

### Monthly
- [ ] Update dependencies
- [ ] Review and prune old data
- [ ] Test restore from backup
- [ ] Security audit
- [ ] Review and update configurations

### Quarterly
- [ ] Performance review and optimization
- [ ] Capacity planning
- [ ] Disaster recovery drill
- [ ] Architecture review

## 📞 Escalation

### When to Escalate

**Immediate escalation (critical):**
- Database corruption
- Complete data loss
- Security breach
- System completely down > 1 hour

**Next business day (high):**
- Performance degradation > 50%
- Frequent errors affecting users
- Backup failures
- Rate limiting blocking legitimate users

**Next sprint (medium):**
- Minor performance issues
- Occasional errors
- Documentation updates needed

### Escalation Contacts

1. **Primary On-call**: [Your contact]
2. **Secondary**: [Your contact]
3. **Engineering Manager**: [Your contact]
4. **Create Issue**: https://github.com/your-org/signal-harvester/issues

## 📚 Additional Resources

- [Deployment Guide](DEPLOYMENT.md)
- [Backup Procedures](BACKUP.md)
- [API Documentation](API.md)
- [Troubleshooting Guide](TROUBLESHOOTING.md)
