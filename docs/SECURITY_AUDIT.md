# Security Audit & Compliance Guide

**Signal Harvester - Phase Three Week 4**  
**Date:** November 12, 2025  
**Version:** 1.0

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Security Audit Checklist](#security-audit-checklist)
3. [Secrets Rotation Procedures](#secrets-rotation-procedures)
4. [Compliance Requirements](#compliance-requirements)
5. [Vulnerability Management](#vulnerability-management)
6. [Monitoring & Incident Response](#monitoring--incident-response)
7. [API Security](#api-security)
8. [Database Security](#database-security)
9. [Deployment Security](#deployment-security)

---

## Executive Summary

This document provides comprehensive security guidelines for Signal Harvester, including audit procedures, secrets rotation, compliance requirements, and incident response protocols. All personnel with access to production systems should review this document and follow the procedures outlined.

### Security Objectives

- **Confidentiality**: Protect sensitive data and API keys
- **Integrity**: Ensure data accuracy and prevent unauthorized modifications
- **Availability**: Maintain system uptime and resilience
- **Compliance**: Meet industry standards and regulatory requirements

---

## Security Audit Checklist

### Monthly Security Audit (First Monday of Each Month)

#### 1. Dependency Scanning

```bash
# Run security vulnerability scan
cd signal-harvester
harvest security scan --output security-report.json

# Review findings
cat security-report.json | jq '.vulnerabilities[] | select(.severity == "critical" or .severity == "high")'

# Apply updates
pip install --upgrade <package>
```

**Success Criteria:**
- ✅ Zero critical vulnerabilities
- ✅ Zero high vulnerabilities older than 7 days
- ✅ Medium vulnerabilities addressed within 30 days

#### 2. API Key Audit

```bash
# Check API key status
# Review keys in environment or secrets manager

# Verify last rotation dates
# API keys should be rotated every 90 days
```

**Check:**
- [ ] X (Twitter) API bearer token (expires: _______)
- [ ] OpenAI API key (last rotated: _______)
- [ ] Anthropic API key (last rotated: _______)
- [ ] xAI API key (last rotated: _______)
- [ ] GitHub token (for repository ingestion) (expires: _______)
- [ ] Slack webhook URL (active: _______)
- [ ] Internal API keys (last rotated: _______)

#### 3. Access Control Review

**Review:**
- [ ] Database access logs (no unauthorized access)
- [ ] API access logs (rate limiting working correctly)
- [ ] Admin user accounts (remove stale accounts)
- [ ] SSH key access (remove old keys)
- [ ] Cloud provider IAM roles (principle of least privilege)

#### 4. Infrastructure Security

**Check:**
- [ ] SSL/TLS certificates (expiry > 30 days)
- [ ] Firewall rules (no unnecessary open ports)
- [ ] Database backups (last successful backup within 24 hours)
- [ ] Log aggregation (logs flowing correctly)
- [ ] Container image scanning (no critical CVEs in base images)

#### 5. Code Security

```bash
# Run linters and security checks
cd signal-harvester
make lint

# Check for secrets in code
git secrets --scan-history || echo "git-secrets not installed"
gitleaks detect --source . || echo "gitleaks not installed"
```

**Review:**
- [ ] No hardcoded secrets in code
- [ ] `.env` files not committed
- [ ] Proper input validation
- [ ] SQL injection prevention (parameterized queries)
- [ ] XSS prevention (output escaping)

#### 6. Compliance Verification

**Review:**
- [ ] Data retention policy applied (90 days for X data)
- [ ] User deletion requests processed within 30 days
- [ ] Privacy policy up to date
- [ ] Terms of service up to date
- [ ] Cookie consent banner functional
- [ ] GDPR data export available

### Quarterly Security Audit (First Monday of Jan/Apr/Jul/Oct)

#### 1. Penetration Testing

- [ ] API endpoint security testing
- [ ] Authentication bypass attempts
- [ ] SQL injection testing
- [ ] XSS testing
- [ ] CSRF testing
- [ ] Rate limiting validation

#### 2. Disaster Recovery Testing

- [ ] Database backup restore test
- [ ] Failover testing
- [ ] Incident response drill
- [ ] Backup integrity verification

#### 3. Compliance Audit

- [ ] SOC 2 controls review (if applicable)
- [ ] GDPR compliance check
- [ ] CCPA compliance check (if applicable)
- [ ] Industry-specific regulations

---

## Secrets Rotation Procedures

### API Key Rotation Schedule

| Secret Type | Rotation Frequency | Lead Time | Owner |
|-------------|-------------------|-----------|-------|
| X API Bearer Token | 90 days | 7 days | Platform Team |
| OpenAI API Key | 90 days | 7 days | ML Team |
| Anthropic API Key | 90 days | 7 days | ML Team |
| xAI API Key | 90 days | 7 days | ML Team |
| GitHub Token | 365 days | 14 days | Platform Team |
| Database Credentials | 180 days | 14 days | Database Team |
| Internal API Keys | 90 days | 7 days | Platform Team |

### Rotation Procedure

#### Step 1: Generate New Key

```bash
# For X API
# 1. Log in to https://developer.twitter.com/
# 2. Navigate to your project/app
# 3. Regenerate Bearer Token
# 4. Copy new token (shown once)

# For OpenAI
# 1. Log in to https://platform.openai.com/
# 2. Navigate to API Keys
# 3. Create new secret key
# 4. Copy new key (shown once)

# For Anthropic
# 1. Log in to https://console.anthropic.com/
# 2. Navigate to API Keys
# 3. Create new key
# 4. Copy new key

# For Internal API Keys
harvest security generate-key --name "Production API" --expires-days 90
```

#### Step 2: Test New Key

```bash
# Update .env.staging with new key
echo "X_BEARER_TOKEN=new_token_here" >> .env.staging

# Test in staging environment
harvest fetch --max-results 10

# Verify successful fetch
harvest stats
```

#### Step 3: Deploy to Production

```bash
# Update secrets in production
# Option A: Kubernetes secrets
kubectl create secret generic harvest-api-keys \
  --from-literal=x-bearer-token=$NEW_X_TOKEN \
  --from-literal=openai-api-key=$NEW_OPENAI_KEY \
  --dry-run=client -o yaml | kubectl apply -f -

# Option B: Cloud provider secrets manager
# AWS Secrets Manager
aws secretsmanager update-secret \
  --secret-id harvest/api-keys \
  --secret-string '{"x_bearer_token":"'$NEW_X_TOKEN'"}'

# Option C: Direct environment update (not recommended)
# Update .env file on production server
```

#### Step 4: Verify Production

```bash
# Check API health
curl https://api.yourdomain.com/health

# Verify pipeline runs successfully
# Monitor logs for 15 minutes
kubectl logs -f deployment/signal-harvester --tail=50
```

#### Step 5: Revoke Old Key

```bash
# After 24 hours of successful production use:

# For X API
# Delete old bearer token from developer portal

# For OpenAI/Anthropic
# Revoke old key from console

# For Internal API Keys
harvest security revoke-key <old_key>
```

#### Step 6: Document Rotation

```bash
# Record rotation in tracking sheet
echo "$(date): Rotated X API key - Success" >> security/rotation_log.txt

# Update secrets rotation spreadsheet
# Include: Date, Secret Type, Rotated By, Status
```

### Emergency Key Revocation

If a key is compromised:

```bash
# 1. IMMEDIATELY revoke the key
# For X API: Delete from developer portal
# For OpenAI/Anthropic: Revoke from console
# For Internal: harvest security revoke-key <key>

# 2. Generate new key (follow rotation procedure)

# 3. Deploy to production ASAP (emergency deployment)

# 4. Review access logs for suspicious activity
grep "compromised_key_hash" logs/*.log

# 5. Notify security team
# Send incident report to security@yourdomain.com

# 6. Document incident
# Create post-mortem document
```

---

## Compliance Requirements

### X (Twitter) API Compliance

#### Data Retention

```bash
# Signal Harvester enforces 90-day retention for X data
# Automated via retention policy

# Verify retention policy active
harvest retention-check

# Manual cleanup if needed
harvest prune --older-than 90
```

**Requirements:**
- ✅ Delete tweet content after 90 days
- ✅ Retain only tweet IDs and metadata
- ✅ Respect user deletion requests within 30 days
- ✅ Display proper attribution (Twitter logo, "via Twitter")
- ✅ No modification of tweet content
- ✅ Rate limiting respected

#### User Deletion Requests

```bash
# Process user deletion request
harvest delete-user-data --user-id <twitter_user_id>

# Verify deletion
harvest verify-deletion --user-id <twitter_user_id>

# Log deletion for compliance
echo "$(date): Deleted data for user $USER_ID" >> compliance/deletion_log.txt
```

### GDPR Compliance (EU Users)

#### Right to Access

```bash
# Export all data for a user
harvest export-user-data --user-id <id> --format json --output user_data_export.json

# Include:
# - All tweets/signals
# - Processing history
# - Stored preferences
# - Access logs
```

#### Right to Erasure

```bash
# Delete all user data
harvest delete-user-data --user-id <id> --confirm

# Verify complete deletion
# - Database records deleted
# - Backups updated (if possible)
# - Logs anonymized
```

#### Right to Portability

```bash
# Export in machine-readable format
harvest export-user-data --user-id <id> --format json
```

### SOC 2 Controls (If Applicable)

**Control Requirements:**
- [ ] Access controls implemented (RBAC)
- [ ] Encryption at rest (database)
- [ ] Encryption in transit (TLS 1.2+)
- [ ] Audit logging enabled
- [ ] Change management process
- [ ] Incident response plan
- [ ] Business continuity plan
- [ ] Vendor management
- [ ] Security awareness training

---

## Vulnerability Management

### Vulnerability Response Timeline

| Severity | Detection | Patching | Verification |
|----------|-----------|----------|--------------|
| Critical | Immediate | 24 hours | 48 hours |
| High | Daily scan | 7 days | 14 days |
| Medium | Weekly scan | 30 days | 45 days |
| Low | Monthly scan | 90 days | 120 days |

### Vulnerability Remediation Process

#### 1. Detection

```bash
# Automated scans (GitHub Actions)
# Manual scans
harvest security scan --output scan_results.json

# Review vulnerabilities
cat scan_results.json | jq '.vulnerabilities[]'
```

#### 2. Triage

**Assess:**
- Severity level
- Exploitability
- Impact on systems
- Available patches
- Workarounds

**Prioritize:**
1. Critical + Exploitable + Production = P0 (24h)
2. High + Exploitable + Production = P1 (7d)
3. Medium + Production = P2 (30d)
4. Low or Development Only = P3 (90d)

#### 3. Remediation

```bash
# Update dependency
pip install --upgrade <vulnerable_package>

# Test changes
pytest tests/

# Verify fix
harvest security scan
```

#### 4. Verification

```bash
# Confirm vulnerability resolved
harvest security scan | grep <CVE-ID>

# Should return no results

# Deploy to production
git tag v1.x.x
git push --tags
```

#### 5. Documentation

- Update CHANGELOG.md
- Document in security incident log
- Notify stakeholders if customer-impacting

---

## Monitoring & Incident Response

### Security Monitoring

#### 1. Log Monitoring

```bash
# Monitor for suspicious activity
tail -f logs/api.log | grep -i "401\|403\|429"

# Failed authentication attempts
grep "401" logs/api.log | wc -l

# Rate limit violations
grep "429" logs/api.log

# Large data exports (potential data exfiltration)
grep "export" logs/api.log | grep "GB"
```

#### 2. Metrics Monitoring

**Alerting Thresholds:**
- Failed auth attempts > 100/hour → Alert
- Rate limit violations > 1000/hour → Alert
- Database query time p95 > 1000ms → Alert
- API error rate > 5% → Alert
- Disk usage > 80% → Warning
- Disk usage > 90% → Alert

#### 3. Audit Logging

```bash
# Enable audit logging
export ENABLE_AUDIT_LOG=true

# View audit log
tail -f logs/audit.log

# Audit log format: timestamp, user, action, resource, result
```

### Incident Response Plan

#### Phase 1: Detection & Analysis (0-15 minutes)

1. **Detect incident**
   - Monitoring alert fires
   - User report
   - Security scan finding

2. **Initial assessment**
   - Severity: Critical/High/Medium/Low
   - Scope: Number of affected users/systems
   - Type: Data breach, service outage, unauthorized access

3. **Assemble response team**
   - Incident Commander
   - Technical Lead
   - Security Lead
   - Communications Lead

#### Phase 2: Containment (15 minutes - 2 hours)

1. **Immediate containment**
   ```bash
   # Revoke compromised API keys
   harvest security revoke-key <key>

   # Block malicious IPs
   iptables -A INPUT -s <malicious_ip> -j DROP

   # Isolate affected systems
   kubectl scale deployment signal-harvester --replicas=0
   ```

2. **Evidence preservation**
   ```bash
   # Capture logs
   kubectl logs deployment/signal-harvester > incident_logs.txt

   # Capture database snapshot
   harvest snapshot create --tag incident-$(date +%Y%m%d)

   # Capture network traffic (if applicable)
   tcpdump -i any -w incident_traffic.pcap
   ```

3. **Short-term containment**
   - Patch vulnerabilities
   - Update firewall rules
   - Enable additional monitoring

#### Phase 3: Eradication (2 hours - 24 hours)

1. **Root cause analysis**
   - Identify attack vector
   - Determine extent of compromise
   - Document timeline

2. **Remove threat**
   ```bash
   # Remove malware/backdoors
   # Update all credentials
   # Patch vulnerabilities
   ```

3. **Verify systems clean**
   ```bash
   # Run security scans
   harvest security scan

   # Check for persistence mechanisms
   # Verify no unauthorized changes
   ```

#### Phase 4: Recovery (24 hours - 7 days)

1. **Restore services**
   ```bash
   # Deploy patched version
   kubectl set image deployment/signal-harvester \
     signal-harvester=signal-harvester:v1.x.x-patched

   # Verify functionality
   curl https://api.yourdomain.com/health

   # Monitor for issues
   kubectl logs -f deployment/signal-harvester
   ```

2. **Incremental rollout**
   - 10% of traffic → Monitor 1 hour
   - 50% of traffic → Monitor 2 hours
   - 100% of traffic → Monitor 24 hours

#### Phase 5: Post-Incident (7+ days)

1. **Post-mortem**
   - Timeline of events
   - Root cause
   - Response effectiveness
   - Lessons learned
   - Action items

2. **Implement improvements**
   - Add monitoring alerts
   - Update runbooks
   - Conduct training
   - Update security controls

3. **Communicate**
   - Internal stakeholders
   - Customers (if applicable)
   - Regulatory bodies (if required)

---

## API Security

### Authentication & Authorization

#### API Key Management

```bash
# Generate new API key
harvest security generate-key --name "Mobile App" --expires-days 90

# List active keys
harvest security list-keys

# Revoke key
harvest security revoke-key <key>

# Deprecate key (warns but still works)
harvest security deprecate-key <key>
```

#### Rate Limiting

**Default Limits:**
- Unauthenticated: 100 requests/minute
- Authenticated: 1000 requests/minute
- Admin: Unlimited

**Per-Endpoint Limits:**
- `/signals/bulk/*`: 10 requests/minute
- `/pipeline/run`: 1 request/5 minutes
- `/export/*`: 5 requests/hour

### Security Headers

All API responses include:
- `Strict-Transport-Security` (HSTS)
- `Content-Security-Policy` (CSP)
- `X-Frame-Options: DENY`
- `X-Content-Type-Options: nosniff`
- `X-XSS-Protection: 1; mode=block`
- `Referrer-Policy: strict-origin-when-cross-origin`

### Input Validation

**Always validate:**
- Query parameters (limit, offset, sort)
- Request body (JSON schema validation)
- File uploads (type, size, content)
- Headers (authentication, content-type)

**Example:**
```python
from pydantic import BaseModel, Field, validator

class SignalCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    source: str = Field(..., regex="^(x|arxiv|github)$")

    @validator("name")
    def name_must_be_safe(cls, v):
        # No SQL injection attempts
        if any(char in v for char in ["'", '"', ";", "--"]):
            raise ValueError("Invalid characters in name")
        return v
```

---

## Database Security

### Connection Security

```yaml
# config/settings.yaml
database:
  url: postgresql://user:password@host:5432/dbname?sslmode=require
  pool:
    size: 10
    max_overflow: 20
    timeout: 30
    recycle: 3600
```

### Encryption

- ✅ **At rest**: Use encrypted volumes/disks
- ✅ **In transit**: Require SSL/TLS for database connections
- ✅ **Backups**: Encrypt database backups

### Access Control

```sql
-- Create read-only user for reporting
CREATE USER harvest_readonly WITH PASSWORD 'secure_password';
GRANT CONNECT ON DATABASE signalharvester TO harvest_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO harvest_readonly;

-- Create application user with limited permissions
CREATE USER harvest_app WITH PASSWORD 'secure_password';
GRANT CONNECT ON DATABASE signalharvester TO harvest_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO harvest_app;
```

### Audit Logging

```sql
-- Enable PostgreSQL audit logging
ALTER SYSTEM SET log_statement = 'all';
ALTER SYSTEM SET log_connections = 'on';
ALTER SYSTEM SET log_disconnections = 'on';
SELECT pg_reload_conf();
```

---

## Deployment Security

### Container Security

```bash
# Scan container images
trivy image signal-harvester:latest

# Run as non-root user
# In Dockerfile:
USER 1000:1000

# No secrets in images
# Use environment variables or secret mounts

# Keep base images updated
docker pull python:3.12-slim
docker build --no-cache -t signal-harvester:latest .
```

### Kubernetes Security

```yaml
# Security context
apiVersion: apps/v1
kind: Deployment
metadata:
  name: signal-harvester
spec:
  template:
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        fsGroup: 1000
      containers:
      - name: api
        securityContext:
          allowPrivilegeEscalation: false
          readOnlyRootFilesystem: true
          capabilities:
            drop:
            - ALL
```

### CI/CD Security

- ✅ Branch protection (require PR reviews)
- ✅ Signed commits
- ✅ Automated security scans
- ✅ Secret scanning (no secrets in code)
- ✅ Dependency scanning
- ✅ Container scanning
- ✅ SAST (static analysis)
- ✅ Integration tests

---

## Appendix

### Security Contacts

- **Security Team**: security@yourdomain.com
- **Incident Response**: incidents@yourdomain.com
- **On-call**: +1-555-0100

### External Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [CWE Top 25](https://cwe.mitre.org/top25/)
- [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework)
- [X API Terms of Service](https://developer.twitter.com/en/developer-terms)

### Changelog

| Date | Version | Changes | Author |
|------|---------|---------|--------|
| 2025-11-12 | 1.0 | Initial version | Phase 3 Team |

---

**END OF DOCUMENT**
