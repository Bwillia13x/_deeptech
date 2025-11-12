# CI/CD Pipeline Documentation

## Overview

Signal Harvester uses GitHub Actions for continuous integration and deployment. The pipeline ensures code quality, security, and reliable deployments across environments.

## Workflows

### 1. Test Workflow (`test.yml`)

**Trigger**: Push/PR to `main` or `develop` branches

**Jobs**:

- **test**: Runs pytest suite with coverage reporting
  - Python 3.12 matrix
  - Initializes test database
  - Runs Alembic migrations
  - Generates coverage reports (term, XML, HTML)
  - Uploads to Codecov
  - Requires ≥70% coverage threshold
  
- **test-integration**: Integration tests with Redis
  - Runs after unit tests pass
  - Uses Redis service container
  - Tests API endpoints with caching
  - Validates database connections

**Environment Variables**:

```bash
DATABASE_PATH=var/test.db
REDIS_HOST=localhost
REDIS_PORT=6379
```

**Artifacts**:

- Coverage HTML report (30 days retention)
- Coverage XML for Codecov

### 2. Lint Workflow (`lint.yml`)

**Trigger**: Push/PR to `main` or `develop` branches

**Checks**:

- **Ruff linting**: Code style and quality checks
- **Ruff formatting**: Consistent code formatting
- **MyPy type checking**: Static type analysis
- **TODO detection**: Warns on unresolved TODO comments

**Output**: GitHub-formatted annotations for easy review

### 3. Frontend Workflow (`frontend.yml`)

**Trigger**: Push/PR affecting `frontend/**` files

**Jobs**:

- **build**:
  - TypeScript type checking
  - ESLint validation
  - Production build
  - Bundle size reporting
  
- **test**:
  - Frontend unit tests (if present)

**Artifacts**:

- Built frontend (`frontend/dist/`) with 30 days retention

**Node Version**: 20.x with npm caching

### 4. Deploy Workflow (`deploy.yml`)

**Trigger**:

- Push to `main` branch
- Version tags (`v*.*.*`)
- Pull requests (build-only)

**Jobs**:

#### build-and-push

- Builds multi-platform Docker image
- Pushes to GitHub Container Registry (`ghcr.io`)
- Tags: branch name, PR number, semver, SHA, `latest`
- Trivy security scanning
- Uploads results to GitHub Security

#### deploy-staging

- **Trigger**: Push to `main`
- **Environment**: `staging`
- **Steps**:
  1. Configure kubectl with staging cluster
  2. Update deployment image
  3. Wait for rollout completion
  4. Run smoke tests

#### deploy-production

- **Trigger**: Version tags (`v*.*.*`)
- **Environment**: `production`
- **Requires**: Successful staging deployment
- **Steps**:
  1. Configure kubectl with production cluster
  2. Update deployment image with tagged version
  3. Wait for rollout completion
  4. Run smoke tests
  5. Send deployment notifications

**Image Tags**:

```
ghcr.io/bwillia13x/_deeptech:main
ghcr.io/bwillia13x/_deeptech:v1.2.3
ghcr.io/bwillia13x/_deeptech:main-a1b2c3d
ghcr.io/bwillia13x/_deeptech:latest
```

### 5. Security Workflow (`security.yml`)

**Trigger**:

- Push/PR to `main` or `develop`
- Daily schedule (2 AM UTC)

**Jobs**:

#### dependency-check

- **Safety**: Checks for known vulnerabilities in Python packages
- **pip-audit**: Audits pip packages for security issues

#### codeql-analysis

- Runs CodeQL analysis for Python and JavaScript
- Uploads findings to GitHub Security

#### secret-scanning

- **Gitleaks**: Scans git history for secrets
- **Pattern matching**: Checks for common API key patterns
  - OpenAI keys: `sk-[a-zA-Z0-9]{48}`
  - Slack tokens: `xoxb-*`

## Configuration

### Required Secrets

Set these in GitHub repository settings → Secrets and variables → Actions:

```bash
CODECOV_TOKEN          # For coverage reporting
GITHUB_TOKEN           # Auto-provided by GitHub Actions
```

### Optional Secrets (for deployment)

```bash
KUBE_CONFIG_STAGING    # Kubernetes config for staging
KUBE_CONFIG_PRODUCTION # Kubernetes config for production
SLACK_WEBHOOK_URL      # Deployment notifications
```

### Branch Protection Rules

Recommended settings for `main` branch:

- ✅ Require pull request before merging
- ✅ Require approvals: 1
- ✅ Require status checks to pass:
  - `test / test`
  - `test / test-integration`
  - `lint / lint`
  - `frontend / build`
  - `security / dependency-check`
  - `security / codeql-analysis`
- ✅ Require conversation resolution before merging
- ✅ Require linear history
- ✅ Do not allow force pushes

## Deployment Process

### Staging Deployment

1. Merge PR to `main` branch
2. CI runs all tests and builds
3. Docker image built and pushed
4. Auto-deploy to staging environment
5. Smoke tests validate deployment
6. Manual verification in staging

### Production Deployment

1. Create version tag:

   ```bash
   git tag -a v1.2.3 -m "Release v1.2.3"
   git push origin v1.2.3
   ```

2. CI builds and tags Docker image
3. Deploys to staging first
4. Manual approval required for production
5. Deploys to production
6. Runs smoke tests
7. Sends deployment notification

### Rollback Procedure

```bash
# List recent deployments
kubectl rollout history deployment/signal-harvester

# Rollback to previous version
kubectl rollout undo deployment/signal-harvester

# Rollback to specific revision
kubectl rollout undo deployment/signal-harvester --to-revision=5

# Verify rollback
kubectl rollout status deployment/signal-harvester
```

## Monitoring CI/CD

### GitHub Actions Dashboard

View at: `https://github.com/Bwillia13x/_deeptech/actions`

**Status Badges**: Added to README.md for quick overview

### Workflow Run Analytics

```bash
# List recent workflow runs
gh run list --workflow=test.yml --limit 10

# View specific run
gh run view <run-id>

# Watch current run
gh run watch

# Download artifacts
gh run download <run-id>
```

### Common Issues

#### Test Failures

```bash
# Run tests locally to debug
pytest tests/ -v --tb=short

# Check specific test file
pytest tests/test_api.py -v -k test_name

# Run with coverage
pytest tests/ --cov=src/signal_harvester --cov-report=html
open htmlcov/index.html
```

#### Build Failures

```bash
# Test Docker build locally
docker build -t signal-harvester:test .

# Run container locally
docker run -p 8000:8000 signal-harvester:test

# Check logs
docker logs <container-id>
```

#### Deployment Failures

```bash
# Check deployment status
kubectl get deployments
kubectl describe deployment signal-harvester

# Check pod status
kubectl get pods
kubectl logs deployment/signal-harvester

# Check events
kubectl get events --sort-by=.metadata.creationTimestamp
```

## Performance

### Typical Run Times

- **Tests**: 2-3 minutes
- **Lint**: 30-45 seconds
- **Frontend Build**: 1-2 minutes
- **Docker Build**: 3-5 minutes
- **Security Scans**: 2-4 minutes

### Optimization Tips

1. **Cache Dependencies**:
   - Python pip cache enabled
   - Node npm cache enabled
   - Docker layer caching with BuildKit

2. **Parallel Jobs**:
   - Tests and lint run in parallel
   - Frontend builds independently
   - Security scans run concurrently

3. **Conditional Execution**:
   - Frontend only runs when frontend files change
   - Deployments skip on PR builds

## Best Practices

### Pull Request Workflow

1. Create feature branch from `develop`
2. Make changes and commit
3. Push and create PR
4. Wait for CI checks to pass
5. Request review
6. Address feedback
7. Merge when approved and CI green

### Commit Messages

Follow conventional commits:

```
feat: add citation graph visualization
fix: resolve memory leak in embedding cache
docs: update API documentation
test: add integration tests for Redis cache
chore: update dependencies
```

### Version Tagging

Use semantic versioning:

- **Major** (v2.0.0): Breaking changes
- **Minor** (v1.2.0): New features, backward compatible
- **Patch** (v1.1.1): Bug fixes, backward compatible

```bash
# Create release
git checkout main
git pull
git tag -a v1.2.3 -m "Release v1.2.3: Feature description"
git push origin v1.2.3
```

## Maintenance

### Weekly Tasks

- Review security scan results
- Update dependencies if needed
- Check workflow run analytics
- Review failed runs

### Monthly Tasks

- Audit secrets and rotate if needed
- Review and update branch protection rules
- Archive old workflow runs
- Update CI/CD documentation

### Quarterly Tasks

- Review and optimize workflow performance
- Update GitHub Actions versions
- Security audit of CI/CD pipeline
- Disaster recovery testing

## Troubleshooting

### "Tests timed out"

- Increase timeout in workflow
- Check for infinite loops
- Review database connection handling

### "Docker build failed"

- Verify Dockerfile syntax
- Check base image availability
- Review build context size

### "Coverage below threshold"

- Add tests for uncovered code
- Review coverage report: `htmlcov/index.html`
- Consider adjusting threshold if reasonable

### "Deployment stuck"

- Check Kubernetes cluster status
- Verify kubectl credentials
- Review pod events and logs
- Check resource quotas

## References

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Docker Build Push Action](https://github.com/docker/build-push-action)
- [Codecov](https://about.codecov.io/)
- [Trivy Security Scanner](https://github.com/aquasecurity/trivy)
