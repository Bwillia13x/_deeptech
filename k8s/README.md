# Kubernetes Deployment Manifests

This directory contains production-ready Kubernetes manifests for deploying Signal Harvester using Kustomize overlays.

## Directory Structure

```
k8s/
├── base/                           # Base manifests (common to all environments)
│   ├── namespace.yaml              # Namespace definition
│   ├── configmap.yaml              # Application configuration
│   ├── secrets.yaml                # Secrets template (replace with actual values)
│   ├── pvc.yaml                    # Persistent Volume Claims
│   ├── redis.yaml                  # Redis deployment and service
│   ├── deployment.yaml             # Main API deployment and service
│   ├── cronjob.yaml                # Scheduled pipeline jobs
│   ├── ingress.yaml                # Ingress configuration
│   ├── autoscaling.yaml            # HPA, PDB, ResourceQuota, LimitRange
│   └── kustomization.yaml          # Base kustomization
├── overlays/
│   ├── staging/                    # Staging environment
│   │   ├── kustomization.yaml
│   │   ├── deployment-patch.yaml   # Lower resources for staging
│   │   ├── configmap-patch.yaml    # Staging-specific config
│   │   └── ingress-patch.yaml      # Staging domain
│   └── production/                 # Production environment
│       ├── kustomization.yaml
│       ├── deployment-patch.yaml   # Higher resources for production
│       ├── configmap-patch.yaml    # Production-specific config
│       ├── ingress-patch.yaml      # Production domain
│       └── autoscaling-patch.yaml  # Production-specific HPA
└── README.md                       # This file
```

## Prerequisites

### Required Tools

```bash
# Install kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/darwin/arm64/kubectl"
chmod +x kubectl
sudo mv kubectl /usr/local/bin/

# Install kustomize
brew install kustomize

# Or download directly
curl -s "https://raw.githubusercontent.com/kubernetes-sigs/kustomize/master/hack/install_kustomize.sh" | bash
```

### Kubernetes Cluster

You need a running Kubernetes cluster. Examples:

**GKE (Google Kubernetes Engine):**

```bash
gcloud container clusters create signal-harvester \
  --zone us-central1-a \
  --num-nodes 3 \
  --machine-type n2-standard-4 \
  --disk-size 100 \
  --enable-autoscaling \
  --min-nodes 2 \
  --max-nodes 10
```

**EKS (Amazon Elastic Kubernetes Service):**

```bash
eksctl create cluster \
  --name signal-harvester \
  --region us-east-1 \
  --nodegroup-name standard-workers \
  --node-type t3.xlarge \
  --nodes 3 \
  --nodes-min 2 \
  --nodes-max 10
```

**AKS (Azure Kubernetes Service):**

```bash
az aks create \
  --resource-group signal-harvester-rg \
  --name signal-harvester \
  --node-count 3 \
  --node-vm-size Standard_D4s_v3 \
  --enable-cluster-autoscaler \
  --min-count 2 \
  --max-count 10
```

## Configuration

### 1. Update Secrets

**IMPORTANT:** Replace placeholder values in `base/secrets.yaml` before deploying:

```bash
# Option 1: Edit secrets.yaml directly
vi k8s/base/secrets.yaml

# Option 2: Create secrets from environment variables
kubectl create secret generic signal-harvester-secrets \
  --from-literal=X_BEARER_TOKEN="${X_BEARER_TOKEN}" \
  --from-literal=OPENAI_API_KEY="${OPENAI_API_KEY}" \
  --from-literal=ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY}" \
  --from-literal=HARVEST_API_KEY="${HARVEST_API_KEY}" \
  --namespace=signal-harvester \
  --dry-run=client -o yaml > k8s/base/secrets.yaml

# Option 3: Use External Secrets Operator (recommended for production)
# See: https://external-secrets.io/
```

### 2. Update Domain Names

Edit `ingress-patch.yaml` in staging/production overlays:

```yaml
# k8s/overlays/production/ingress-patch.yaml
spec:
  tls:
  - hosts:
    - your-domain.com  # ← Change this
    secretName: prod-signal-harvester-tls
  rules:
  - host: your-domain.com  # ← Change this
```

### 3. Configure Storage Class

Update `base/pvc.yaml` to match your cloud provider:

```yaml
# GKE
storageClassName: standard-rwo  # or premium-rwo

# EKS
storageClassName: gp3  # or gp2

# AKS
storageClassName: managed-csi  # or managed-premium
```

## Deployment

### Staging Environment

```bash
# Verify manifests
kubectl kustomize k8s/overlays/staging

# Apply
kubectl apply -k k8s/overlays/staging

# Watch deployment
kubectl get pods -n signal-harvester-staging -w

# Check logs
kubectl logs -n signal-harvester-staging -l app.kubernetes.io/component=api -f
```

### Production Environment

```bash
# Verify manifests
kubectl kustomize k8s/overlays/production

# Apply
kubectl apply -k k8s/overlays/production

# Watch rollout
kubectl rollout status deployment/prod-signal-harvester -n signal-harvester-production

# Verify health
kubectl get pods -n signal-harvester-production
kubectl get ingress -n signal-harvester-production
```

## CI/CD Integration

The GitHub Actions workflow (`.github/workflows/deploy.yml`) automatically deploys to staging and production:

1. **Staging**: Auto-deploys on push to `main` branch
2. **Production**: Manual approval required for version tags (e.g., `v1.2.3`)

The workflow:

- Builds Docker image
- Pushes to GHCR
- Scans with Trivy
- Updates Kustomize image tag
- Applies to cluster via `kubectl`

## Monitoring

### Check Application Health

```bash
# API health endpoint
kubectl port-forward -n signal-harvester-production svc/prod-signal-harvester-service 8080:80
curl http://localhost:8080/health

# Pod status
kubectl get pods -n signal-harvester-production -l app.kubernetes.io/component=api

# Logs
kubectl logs -n signal-harvester-production -l app.kubernetes.io/component=api --tail=100
```

### Check Scheduled Jobs

```bash
# List CronJobs
kubectl get cronjobs -n signal-harvester-production

# View job history
kubectl get jobs -n signal-harvester-production

# Check latest job logs
kubectl logs -n signal-harvester-production job/discovery-pipeline-28392839 -f
```

### Resource Utilization

```bash
# CPU/Memory usage
kubectl top pods -n signal-harvester-production

# HPA status
kubectl get hpa -n signal-harvester-production
kubectl describe hpa prod-signal-harvester-hpa -n signal-harvester-production
```

## Scaling

### Manual Scaling

```bash
# Scale deployment
kubectl scale deployment/prod-signal-harvester -n signal-harvester-production --replicas=5

# Horizontal Pod Autoscaler handles automatic scaling
# Edit HPA to change min/max replicas
kubectl edit hpa prod-signal-harvester-hpa -n signal-harvester-production
```

### Update Resources

```bash
# Edit deployment resources
kubectl edit deployment prod-signal-harvester -n signal-harvester-production

# Or update overlay and reapply
vi k8s/overlays/production/deployment-patch.yaml
kubectl apply -k k8s/overlays/production
```

## Updates and Rollbacks

### Rolling Update

```bash
# Update image tag in kustomization
cd k8s/overlays/production
kustomize edit set image ghcr.io/bwillia13x/signal-harvester:v1.2.3

# Apply
kubectl apply -k .

# Watch rollout
kubectl rollout status deployment/prod-signal-harvester -n signal-harvester-production
```

### Rollback

```bash
# Rollback to previous version
kubectl rollout undo deployment/prod-signal-harvester -n signal-harvester-production

# Rollback to specific revision
kubectl rollout history deployment/prod-signal-harvester -n signal-harvester-production
kubectl rollout undo deployment/prod-signal-harvester -n signal-harvester-production --to-revision=2
```

## Troubleshooting

### Pod Not Starting

```bash
# Describe pod
kubectl describe pod <pod-name> -n signal-harvester-production

# Check events
kubectl get events -n signal-harvester-production --sort-by='.lastTimestamp'

# Check logs (including init containers)
kubectl logs <pod-name> -n signal-harvester-production -c init-db
kubectl logs <pod-name> -n signal-harvester-production -c api
```

### Database Migration Issues

```bash
# Manually run migrations
kubectl run -it --rm debug --image=ghcr.io/bwillia13x/signal-harvester:latest \
  --restart=Never -n signal-harvester-production \
  -- alembic upgrade head

# Or exec into pod
kubectl exec -it <pod-name> -n signal-harvester-production -- /bin/bash
alembic current
alembic upgrade head
```

### Network/Ingress Issues

```bash
# Check ingress
kubectl get ingress -n signal-harvester-production
kubectl describe ingress prod-signal-harvester-ingress -n signal-harvester-production

# Check service
kubectl get svc -n signal-harvester-production
kubectl describe svc prod-signal-harvester-service -n signal-harvester-production

# Test internal connectivity
kubectl run -it --rm debug --image=curlimages/curl --restart=Never -n signal-harvester-production \
  -- curl http://prod-signal-harvester-service/health
```

### Persistent Volume Issues

```bash
# Check PVCs
kubectl get pvc -n signal-harvester-production

# Check PVs
kubectl get pv

# Describe PVC
kubectl describe pvc signal-harvester-data -n signal-harvester-production
```

## Security Best Practices

### Secrets Management

- **Never commit secrets to Git**
- Use External Secrets Operator or Sealed Secrets
- Rotate secrets regularly (90-day cycle recommended)
- Use separate secrets for staging/production

### Network Policies

```bash
# Apply network policies (create separate file)
kubectl apply -f k8s/base/network-policy.yaml
```

### RBAC

```bash
# Create limited service account
kubectl apply -f k8s/base/rbac.yaml
```

### Pod Security

- Run as non-root user (UID 1000)
- Drop all capabilities
- Read-only root filesystem (where possible)
- Security context applied to all pods

## Resource Management

### Storage

- **Data volume**: 20Gi (adjustable in `pvc.yaml`)
- **Logs volume**: 10Gi
- **Redis data**: 5Gi
- Consider using dynamic provisioning with storage classes

### Compute

**Staging:**

- CPU: 250m-1000m per pod
- Memory: 512Mi-2Gi per pod
- 1 replica

**Production:**

- CPU: 1000m-4000m per pod
- Memory: 2Gi-8Gi per pod
- 3-20 replicas (HPA controlled)

### Quotas

Resource quotas are defined in `autoscaling.yaml`:

- Total CPU requests: 10 cores
- Total memory requests: 20Gi
- Max replicas: 20 (via HPA)

## Backup and Disaster Recovery

### Database Backups

```bash
# Create backup
kubectl exec -n signal-harvester-production deployment/prod-signal-harvester \
  -- sqlite3 /data/signal_harvester.db ".backup '/data/backup.db'"

# Copy backup locally
kubectl cp signal-harvester-production/<pod-name>:/data/backup.db ./backup.db
```

### Full Cluster Backup

```bash
# Using Velero (recommended)
velero backup create signal-harvester-backup \
  --include-namespaces signal-harvester-production

# Restore
velero restore create --from-backup signal-harvester-backup
```

## Performance Optimization

### Connection Pooling

Configured in `configmap.yaml`:

- SQLite: 20 pool size, 10 max overflow
- Redis: 50 max connections

### Caching

- Redis cache for embeddings (7-day TTL)
- In-memory fallback when Redis unavailable

### Rate Limiting

- Ingress: 100 RPS, 50 concurrent connections
- Application: 60 requests/minute per API key

## Monitoring Integration

### Prometheus Metrics

Pods are annotated for Prometheus scraping:

```yaml
prometheus.io/scrape: "true"
prometheus.io/port: "8000"
prometheus.io/path: "/metrics"
```

### Grafana Dashboards

See `docs/MONITORING.md` for dashboard setup (upcoming in Task 3).

## Support

For issues or questions:

1. Check logs: `kubectl logs -n signal-harvester-production -l app.kubernetes.io/component=api`
2. Review events: `kubectl get events -n signal-harvester-production`
3. See troubleshooting section above
4. Consult `docs/DEPLOYMENT.md` for detailed deployment guide

## Additional Resources

- [Kustomize Documentation](https://kustomize.io/)
- [Kubernetes Best Practices](https://kubernetes.io/docs/concepts/configuration/overview/)
- [CI/CD Guide](../docs/CI_CD.md)
- [Deployment Guide](../docs/DEPLOYMENT.md)
- [Operations Manual](../docs/OPERATIONS.md)
