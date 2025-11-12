# Kubernetes Deployment Guide

Complete guide for deploying Signal Harvester to a Kubernetes cluster with production-ready configuration.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Architecture Overview](#architecture-overview)
- [Deployment Steps](#deployment-steps)
- [Autoscaling Configuration](#autoscaling-configuration)
- [Monitoring Integration](#monitoring-integration)
- [Security Configuration](#security-configuration)
- [Migration from Docker Compose](#migration-from-docker-compose)
- [Troubleshooting](#troubleshooting)
- [Maintenance](#maintenance)

## Prerequisites

### Required Tools

1. **kubectl** (v1.25+)
   ```bash
   # macOS
   brew install kubectl
   
   # Linux
   curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
   chmod +x kubectl
   sudo mv kubectl /usr/local/bin/
   ```

2. **Kubernetes Cluster**
   - Local: [minikube](https://minikube.sigs.k8s.io/) or [kind](https://kind.sigs.k8s.io/)
   - Cloud: GKE, EKS, AKS, or DigitalOcean Kubernetes
   - Minimum: 3 nodes, 4 CPU cores, 8GB RAM per node

3. **NGINX Ingress Controller**
   ```bash
   # Install with Helm
   helm upgrade --install ingress-nginx ingress-nginx \
     --repo https://kubernetes.github.io/ingress-nginx \
     --namespace ingress-nginx --create-namespace
   
   # Or using manifest
   kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/cloud/deploy.yaml
   ```

4. **cert-manager** (for TLS certificates)
   ```bash
   kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml
   ```

5. **Storage Class** (for persistent volumes)
   ```bash
   # Check available storage classes
   kubectl get storageclass
   
   # Most cloud providers have a default storage class
   # For local clusters, you may need to configure one
   ```

### Optional Tools

- **Helm** (for easier monitoring stack management)
- **kubectx/kubens** (for easier context switching)
- **k9s** (terminal UI for Kubernetes)

## Quick Start

```bash
# 1. Configure kubectl to connect to your cluster
kubectl config use-context your-cluster-context

# 2. Verify cluster connection
kubectl cluster-info

# 3. Run deployment script
cd signal-harvester
./scripts/deploy-k8s.sh

# 4. Monitor deployment
kubectl get pods -n signal-harvester --watch

# 5. Access services (port forwarding)
kubectl port-forward -n signal-harvester svc/signal-harvester-api 8000:8000
kubectl port-forward -n signal-harvester svc/grafana 3000:3000
kubectl port-forward -n signal-harvester svc/prometheus 9090:9090
```

## Architecture Overview

### Components Deployed

1. **Signal Harvester API**
   - 2 initial replicas (scales 2-10 based on load)
   - Resource requests: 250m CPU, 512Mi memory
   - Resource limits: 1000m CPU, 2Gi memory
   - Can handle 300+ VUs per pod (based on load test p95=11.58ms)
   - Zero-downtime rolling updates

2. **Prometheus**
   - 1 replica (monitoring time-series database)
   - 50Gi persistent storage for metrics
   - Scrapes API, Alertmanager, Grafana, node metrics
   - Retention: 15 days

3. **Grafana**
   - 1 replica (visualization dashboard)
   - 10Gi persistent storage for dashboards
   - Pre-configured Prometheus datasource
   - Dashboard provisioning via ConfigMaps

4. **Alertmanager**
   - 1 replica (alert routing and notification)
   - 5Gi persistent storage for alert state
   - Slack integration (requires webhook configuration)
   - Alert grouping and inhibition rules

### Resource Requirements

**Minimum Cluster Capacity:**
- 3 nodes
- Total: 8 CPU cores, 16GB RAM, 100GB storage
- Per node: ~2.5 CPUs, ~5GB RAM, ~30GB storage

**Production Recommendations:**
- 5+ nodes for high availability
- Node auto-scaling enabled
- Regional distribution for redundancy

## Deployment Steps

### Step 1: Prepare Configuration

1. **Create .env file** with API keys:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

2. **Update ingress hosts** in manifests:
   ```bash
   # Edit k8s/signal-harvester-api.yaml
   sed -i 's/api.signal-harvester.example.com/your-domain.com/g' k8s/signal-harvester-api.yaml
   
   # Edit monitoring manifests
   sed -i 's/prometheus.signal-harvester.example.com/prometheus.your-domain.com/g' monitoring/k8s/prometheus.yaml
   sed -i 's/grafana.signal-harvester.example.com/grafana.your-domain.com/g' monitoring/k8s/grafana.yaml
   sed -i 's/alertmanager.signal-harvester.example.com/alertmanager.your-domain.com/g' monitoring/k8s/alertmanager.yaml
   ```

3. **Configure Slack webhooks** for Alertmanager:
   ```bash
   # Edit monitoring/k8s/alertmanager.yaml
   # Replace placeholder URLs in the Secret resource
   ```

### Step 2: Run Automated Deployment

```bash
./scripts/deploy-k8s.sh
```

The script will:
1. ✅ Check prerequisites (kubectl, cluster connection, required files)
2. ✅ Create namespace `signal-harvester`
3. ✅ Create ConfigMaps from Prometheus/Grafana config files
4. ✅ Create secrets from .env file
5. ✅ Apply all Kubernetes manifests
6. ✅ Wait for deployments to become ready
7. ✅ Run health checks
8. ✅ Display access information

### Step 3: Configure DNS

Point your domain names to the ingress controller's external IP:

```bash
# Get ingress IP
kubectl get svc -n ingress-nginx ingress-nginx-controller

# Create DNS A records
api.your-domain.com         → INGRESS_IP
prometheus.your-domain.com  → INGRESS_IP
grafana.your-domain.com     → INGRESS_IP
alertmanager.your-domain.com → INGRESS_IP
```

### Step 4: Verify TLS Certificates

cert-manager will automatically provision Let's Encrypt certificates:

```bash
# Check certificate status
kubectl get certificates -n signal-harvester

# View certificate details
kubectl describe certificate signal-harvester-api-tls -n signal-harvester
```

### Step 5: Import Grafana Dashboards

```bash
# Port forward to Grafana
kubectl port-forward -n signal-harvester svc/grafana 3000:3000

# Access Grafana at http://localhost:3000
# Login: admin / (password from secret)
# Import dashboards from monitoring/grafana/dashboards/*.json
```

## Autoscaling Configuration

### Horizontal Pod Autoscaler (HPA)

The API deployment includes HPA configuration for automatic scaling:

```yaml
# HPA Configuration (from k8s/signal-harvester-api.yaml)
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: signal-harvester-api
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70  # Scale up at 70% CPU
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80  # Scale up at 80% memory
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
        - type: Percent
          value: 50
          periodSeconds: 60
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Pods
          value: 1
          periodSeconds: 60
```

### Scaling Behavior

**Based on Load Test Baseline (p95=11.58ms @ 100 VUs):**

- **Per Pod Capacity**: ~300 VUs (with headroom)
- **2 Replicas (min)**: ~600 VUs
- **10 Replicas (max)**: ~3,000 VUs

**Scale-Up Triggers:**
- CPU > 70% for 60 seconds
- Memory > 80% for 60 seconds
- Can scale up by 50% per minute

**Scale-Down Triggers:**
- CPU < 70% and Memory < 80% for 300 seconds
- Scales down by 1 pod per minute maximum

**Monitor Scaling:**
```bash
# Watch HPA status
kubectl get hpa -n signal-harvester --watch

# View HPA events
kubectl describe hpa signal-harvester-api -n signal-harvester

# View current metrics
kubectl top pods -n signal-harvester
```

### Manual Scaling

Override HPA temporarily:

```bash
# Scale to 5 replicas
kubectl scale deployment signal-harvester-api -n signal-harvester --replicas=5

# HPA will resume control after stabilization window
```

## Monitoring Integration

### Prometheus Configuration

Prometheus automatically discovers and scrapes:
- **API pods**: via Kubernetes service discovery
- **Alertmanager**: static config
- **Grafana**: static config
- **Node exporters**: (if deployed separately)

**View Targets:**
```bash
kubectl port-forward -n signal-harvester svc/prometheus 9090:9090
# Navigate to http://localhost:9090/targets
```

### Grafana Dashboards

**Pre-configured dashboards** (import manually):
1. `signal-harvester-overview.json` - API metrics, request rates, latency
2. `discovery-pipeline.json` - Discovery pipeline metrics
3. `kubernetes-pods.json` - Pod resource usage

**Import Process:**
1. Access Grafana: `kubectl port-forward -n signal-harvester svc/grafana 3000:3000`
2. Login with admin credentials
3. Navigate to Dashboards → Import
4. Upload JSON files from `monitoring/grafana/dashboards/`

### Alertmanager Configuration

**Default Alert Routing:**
- **Critical alerts** → #signal-harvester-critical (immediate)
- **Warning alerts** → #signal-harvester-alerts (grouped, 30s delay)
- **Discovery alerts** → #signal-harvester-discovery
- **LLM alerts** → #signal-harvester-llm

**Update Slack Webhooks:**
```bash
kubectl edit secret alertmanager-slack-urls -n signal-harvester
```

**Test Alerts:**
```bash
# Port forward to Alertmanager
kubectl port-forward -n signal-harvester svc/alertmanager 9093:9093

# Access UI at http://localhost:9093
# View active alerts and silence rules
```

## Security Configuration

### Network Policies

The deployment includes NetworkPolicy resources that restrict traffic:

**API Pod Network Policy:**
- **Ingress**: Only from ingress-nginx and Prometheus
- **Egress**: Only DNS (port 53) and HTTPS (port 443)

**Verify Network Policies:**
```bash
kubectl get networkpolicies -n signal-harvester
kubectl describe networkpolicy signal-harvester-api -n signal-harvester
```

### Pod Security

**Security Context Configuration:**
```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1000
  fsGroup: 1000
  seccompProfile:
    type: RuntimeDefault
  capabilities:
    drop:
      - ALL
```

### RBAC

**Service Accounts:**
- `signal-harvester-api`: Limited permissions for API pods
- `prometheus`: ClusterRole for service discovery

**View RBAC:**
```bash
kubectl get serviceaccounts -n signal-harvester
kubectl get clusterrole prometheus
kubectl get clusterrolebinding prometheus
```

### Secrets Management

**API Keys stored in Secrets:**
```bash
# View secrets (names only)
kubectl get secrets -n signal-harvester

# Edit secret (requires .env file recreation)
kubectl delete secret signal-harvester-api-keys -n signal-harvester
./scripts/deploy-k8s.sh  # Recreates secrets from .env
```

**Secret Rotation:**
1. Update API keys in .env file
2. Delete existing secret: `kubectl delete secret signal-harvester-api-keys -n signal-harvester`
3. Recreate secret: `./scripts/deploy-k8s.sh`
4. Restart API pods: `kubectl rollout restart deployment signal-harvester-api -n signal-harvester`

## Migration from Docker Compose

### Pre-Migration Checklist

- [ ] Backup SQLite database from Docker volume
- [ ] Export Grafana dashboards
- [ ] Document custom Prometheus alerts
- [ ] Save Alertmanager configuration
- [ ] Note current API configuration

### Migration Steps

1. **Backup Docker Compose Data:**
   ```bash
   # Backup database
   docker cp signal-harvester-api:/app/var/app.db ./backup/app.db
   
   # Backup Prometheus data (optional)
   docker cp prometheus:/prometheus ./backup/prometheus-data
   
   # Backup Grafana dashboards (optional)
   docker cp grafana:/var/lib/grafana/dashboards ./backup/grafana-dashboards
   ```

2. **Stop Docker Compose Stack:**
   ```bash
   docker-compose -f docker-compose.monitoring.yml down
   ```

3. **Prepare Database for K8s:**
   ```bash
   # Copy database to K8s persistent volume (after deployment)
   kubectl cp ./backup/app.db signal-harvester/POD_NAME:/app/var/app.db
   ```

4. **Deploy to Kubernetes:**
   ```bash
   ./scripts/deploy-k8s.sh
   ```

5. **Restore Data:**
   ```bash
   # Get API pod name
   API_POD=$(kubectl get pods -n signal-harvester -l app=signal-harvester-api -o jsonpath='{.items[0].metadata.name}')
   
   # Copy database
   kubectl cp ./backup/app.db signal-harvester/$API_POD:/app/var/app.db
   
   # Restart API to load new database
   kubectl rollout restart deployment signal-harvester-api -n signal-harvester
   ```

6. **Verify Migration:**
   ```bash
   # Check API health
   kubectl exec -n signal-harvester $API_POD -- curl http://localhost:8000/health
   
   # View logs
   kubectl logs -n signal-harvester -l app=signal-harvester-api -f
   
   # Test API endpoint
   kubectl port-forward -n signal-harvester svc/signal-harvester-api 8000:8000
   curl http://localhost:8000/discoveries
   ```

### Post-Migration Tasks

- [ ] Import Grafana dashboards
- [ ] Configure Slack webhook URLs in Alertmanager
- [ ] Update DNS records to point to K8s ingress
- [ ] Set up TLS certificates (cert-manager handles this)
- [ ] Monitor for 24 hours to ensure stability
- [ ] Remove Docker Compose volumes (after confirmation)

## Troubleshooting

### Pod Not Starting

**Symptoms:** Pod stuck in `Pending`, `CrashLoopBackOff`, or `Error` state

**Diagnosis:**
```bash
# Check pod status
kubectl get pods -n signal-harvester

# View pod events
kubectl describe pod POD_NAME -n signal-harvester

# View logs
kubectl logs POD_NAME -n signal-harvester
kubectl logs POD_NAME -n signal-harvester --previous  # Previous container
```

**Common Causes:**

1. **Insufficient Resources:**
   ```bash
   # Check node capacity
   kubectl describe nodes
   
   # Check resource requests
   kubectl describe deployment signal-harvester-api -n signal-harvester
   
   # Solution: Add more nodes or reduce resource requests
   ```

2. **PVC Not Bound:**
   ```bash
   # Check PVC status
   kubectl get pvc -n signal-harvester
   
   # View PVC events
   kubectl describe pvc signal-harvester-data -n signal-harvester
   
   # Solution: Verify storage class exists and has capacity
   kubectl get storageclass
   ```

3. **Secret Not Found:**
   ```bash
   # Check secrets
   kubectl get secrets -n signal-harvester
   
   # Recreate secret
   kubectl delete secret signal-harvester-api-keys -n signal-harvester
   ./scripts/deploy-k8s.sh
   ```

4. **Image Pull Errors:**
   ```bash
   # Check image pull status
   kubectl describe pod POD_NAME -n signal-harvester | grep -A5 "Events"
   
   # Verify image exists
   docker pull bwillia13x/signal-harvester:latest
   ```

### Ingress Not Working

**Symptoms:** Cannot access services via ingress hostname

**Diagnosis:**
```bash
# Check ingress status
kubectl get ingress -n signal-harvester

# View ingress details
kubectl describe ingress signal-harvester-api -n signal-harvester

# Check ingress controller logs
kubectl logs -n ingress-nginx -l app.kubernetes.io/name=ingress-nginx
```

**Common Causes:**

1. **DNS Not Configured:**
   ```bash
   # Get ingress IP
   kubectl get svc -n ingress-nginx ingress-nginx-controller
   
   # Test DNS resolution
   nslookup api.your-domain.com
   
   # Solution: Create DNS A record pointing to ingress IP
   ```

2. **TLS Certificate Not Ready:**
   ```bash
   # Check certificate status
   kubectl get certificates -n signal-harvester
   kubectl describe certificate signal-harvester-api-tls -n signal-harvester
   
   # Check cert-manager logs
   kubectl logs -n cert-manager -l app=cert-manager
   
   # Solution: Wait for cert-manager to provision certificate (can take 5-10 minutes)
   ```

3. **Ingress Controller Not Installed:**
   ```bash
   # Check for ingress controller
   kubectl get pods -n ingress-nginx
   
   # Install if missing
   kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/cloud/deploy.yaml
   ```

### High Latency

**Symptoms:** API response times > 50ms (p95)

**Diagnosis:**
```bash
# Check pod metrics
kubectl top pods -n signal-harvester

# View HPA status
kubectl get hpa -n signal-harvester

# Check for CPU/memory throttling
kubectl describe pod POD_NAME -n signal-harvester | grep -A10 "Resource Requests"
```

**Solutions:**

1. **Increase Resource Limits:**
   ```bash
   # Edit deployment
   kubectl edit deployment signal-harvester-api -n signal-harvester
   
   # Increase CPU limits to 2000m, memory to 4Gi
   ```

2. **Scale Horizontally:**
   ```bash
   # Manual scale
   kubectl scale deployment signal-harvester-api -n signal-harvester --replicas=5
   
   # Or adjust HPA
   kubectl edit hpa signal-harvester-api -n signal-harvester
   # Lower CPU threshold from 70% to 60%
   ```

3. **Check Database Performance:**
   ```bash
   # Execute into pod
   kubectl exec -it -n signal-harvester POD_NAME -- /bin/sh
   
   # Check database file size and queries
   ls -lh /app/var/app.db
   ```

### HPA Not Scaling

**Symptoms:** HPA shows `<unknown>` for metrics or doesn't scale

**Diagnosis:**
```bash
# Check HPA status
kubectl get hpa -n signal-harvester
kubectl describe hpa signal-harvester-api -n signal-harvester

# Check metrics server
kubectl get deployment metrics-server -n kube-system

# View metrics
kubectl top pods -n signal-harvester
```

**Solutions:**

1. **Install Metrics Server:**
   ```bash
   kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
   
   # For local clusters (minikube/kind), may need to disable TLS:
   kubectl edit deployment metrics-server -n kube-system
   # Add: --kubelet-insecure-tls
   ```

2. **Check Resource Requests:**
   ```bash
   # HPA requires resource requests to be set
   kubectl describe deployment signal-harvester-api -n signal-harvester | grep -A5 "Requests"
   
   # Ensure requests are defined in deployment spec
   ```

### Prometheus Not Scraping Targets

**Symptoms:** Prometheus shows targets as DOWN

**Diagnosis:**
```bash
# Port forward to Prometheus
kubectl port-forward -n signal-harvester svc/prometheus 9090:9090

# Navigate to http://localhost:9090/targets
# Check which targets are DOWN

# View Prometheus logs
kubectl logs -n signal-harvester -l app=prometheus
```

**Solutions:**

1. **Network Policy Blocking:**
   ```bash
   # Check network policies
   kubectl get networkpolicies -n signal-harvester
   
   # Temporarily remove to test
   kubectl delete networkpolicy signal-harvester-api -n signal-harvester
   ```

2. **Service Discovery Issues:**
   ```bash
   # Check Prometheus service discovery
   kubectl exec -n signal-harvester prometheus-POD-NAME -- cat /etc/prometheus/prometheus.yml
   
   # Verify services exist
   kubectl get svc -n signal-harvester
   ```

3. **RBAC Permissions:**
   ```bash
   # Check Prometheus ServiceAccount
   kubectl get serviceaccount prometheus -n signal-harvester
   
   # Check ClusterRole binding
   kubectl get clusterrolebinding prometheus
   ```

## Maintenance

### Rolling Updates

```bash
# Update API image
kubectl set image deployment/signal-harvester-api \
  signal-harvester-api=bwillia13x/signal-harvester:v2.0.0 \
  -n signal-harvester

# Monitor rollout
kubectl rollout status deployment signal-harvester-api -n signal-harvester

# Rollback if needed
kubectl rollout undo deployment signal-harvester-api -n signal-harvester
```

### Backup Procedures

**Database Backup:**
```bash
# Automated backup script
kubectl exec -n signal-harvester POD_NAME -- \
  sqlite3 /app/var/app.db ".backup /app/var/app.db.backup"

# Copy to local machine
kubectl cp signal-harvester/POD_NAME:/app/var/app.db.backup ./backup/app-$(date +%Y%m%d).db
```

**Prometheus Backup:**
```bash
# Create snapshot
kubectl exec -n signal-harvester prometheus-POD-NAME -- \
  curl -XPOST http://localhost:9090/api/v1/admin/tsdb/snapshot

# Copy snapshot
kubectl cp signal-harvester/prometheus-POD-NAME:/prometheus/snapshots/SNAPSHOT_NAME ./backup/
```

### Monitoring Resource Usage

```bash
# View resource usage
kubectl top nodes
kubectl top pods -n signal-harvester

# View persistent volume usage
kubectl exec -n signal-harvester POD_NAME -- df -h

# Check for pod restarts
kubectl get pods -n signal-harvester -o wide
```

### Log Management

```bash
# View logs
kubectl logs -n signal-harvester -l app=signal-harvester-api -f

# Save logs to file
kubectl logs -n signal-harvester POD_NAME > api-logs-$(date +%Y%m%d).log

# View logs from all replicas
kubectl logs -n signal-harvester -l app=signal-harvester-api --tail=100 --all-containers
```

### Cleanup

```bash
# Remove entire deployment
./scripts/deploy-k8s.sh cleanup

# Or manually delete namespace
kubectl delete namespace signal-harvester
```

## Performance Tuning

### Based on Load Test Results

**Baseline Performance (p95=11.58ms @ 100 VUs):**
- Current resource requests are well-tuned
- Each pod can handle 300+ VUs comfortably
- 2 replicas can handle 600+ VUs

**Optimization Recommendations:**

1. **For Higher Throughput:**
   - Increase `maxReplicas` in HPA to 15-20
   - Lower CPU threshold to 60% for faster scaling
   - Consider dedicated node pool for API pods

2. **For Lower Latency:**
   - Increase CPU limits to 2000m
   - Use faster storage class for database PVC (SSD)
   - Consider read replicas if using PostgreSQL

3. **For Cost Optimization:**
   - Use spot instances for non-critical replicas
   - Reduce `minReplicas` to 1 in dev/staging
   - Enable cluster autoscaler for node optimization

## Additional Resources

- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [NGINX Ingress Controller](https://kubernetes.github.io/ingress-nginx/)
- [cert-manager Documentation](https://cert-manager.io/docs/)
- [Prometheus Operator](https://github.com/prometheus-operator/prometheus-operator)
- [Grafana in Kubernetes](https://grafana.com/docs/grafana/latest/setup-grafana/installation/kubernetes/)

---

**Last Updated:** November 12, 2025  
**Version:** 1.0.0  
**Deployment Script:** `scripts/deploy-k8s.sh`
