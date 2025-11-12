# Monitoring Stack Setup Guide

## Overview

Signal Harvester includes a comprehensive monitoring stack built on industry-standard tools:

- **Prometheus** - Metrics collection and storage
- **Grafana** - Visualization and dashboards
- **Alertmanager** - Alert routing and notifications
- **Node Exporter** - System-level metrics

This guide covers local development deployment using Docker Compose.

## Quick Start

### Prerequisites

- Docker and Docker Compose installed
- Signal Harvester codebase cloned
- `.env` file configured (for Slack notifications in production)

### Deploy the Stack

```bash
cd signal-harvester
./scripts/deploy-monitoring-docker.sh
```

The deployment script will:

1. Check prerequisites (Docker, Docker Compose)
2. Build the Signal Harvester API image if needed
3. Deploy all monitoring services
4. Wait for services to become healthy
5. Display service URLs and access instructions

### Service URLs

Once deployed, access the monitoring services at:

- **Grafana**: <http://localhost:3000>
  - Default credentials: `admin` / `admin` (change on first login)
  - Pre-configured Prometheus datasource
  - Import dashboards from `monitoring/grafana/`

- **Prometheus**: <http://localhost:9090>
  - Query interface for metrics
  - View scraping targets at <http://localhost:9090/targets>
  - View active alerts at <http://localhost:9090/alerts>

- **Alertmanager**: <http://localhost:9093>
  - View active alerts
  - Manage alert silences
  - Configure notification routing

- **API Metrics**: <http://localhost:8000/prometheus>
  - Raw Prometheus metrics from Signal Harvester API
  - Includes request latency, error rates, and Python runtime metrics

- **Node Exporter**: <http://localhost:9100/metrics>
  - System-level metrics (CPU, memory, disk, network)

## Architecture

### Service Configuration

The monitoring stack is defined in `docker-compose.monitoring.yml`:

```yaml
services:
  prometheus:       # Metrics collection (port 9090)
  grafana:          # Visualization (port 3000)
  alertmanager:     # Alert routing (port 9093)
  node-exporter:    # System metrics (port 9100)
  signal-harvester: # API with /prometheus endpoint (port 8000)
```

All services share a `monitoring` Docker network for communication.

### Data Persistence

Three Docker volumes persist monitoring data:

- `prometheus-data` - Metrics storage (30-day retention)
- `grafana-data` - Dashboard configurations and user settings
- `alertmanager-data` - Alert state and silences

### Scraping Configuration

Prometheus scrapes metrics from:

1. **Signal Harvester API** (`signal-harvester:8000/prometheus`)
   - Request latency (p50, p95, p99)
   - Error rates by status code
   - Active requests
   - Python runtime metrics (GC, memory, threads)
   - Scrape interval: 15s

2. **Node Exporter** (`node-exporter:9100/metrics`)
   - CPU usage
   - Memory utilization
   - Disk I/O
   - Network traffic
   - Scrape interval: 15s

3. **Self-monitoring**
   - Prometheus itself (`prometheus:9090/metrics`)
   - Grafana (`grafana:3000/metrics`)
   - Alertmanager (`alertmanager:9093/metrics`)

Configuration: `monitoring/prometheus/prometheus-docker.yml`

## Grafana Dashboards

### Pre-configured Dashboards

Four dashboards are available in `monitoring/grafana/`:

1. **API Performance Dashboard** (`api-performance-dashboard.json`)
   - Request rate and latency (p50, p95, p99)
   - Error rate by status code
   - Active requests
   - Response time heatmap

2. **Discovery Pipeline Dashboard** (`discovery-pipeline-dashboard.json`)
   - Artifact processing rate
   - Source-specific metrics (X, arXiv, GitHub)
   - Discovery scoring performance
   - Pipeline execution time

3. **LLM Usage Dashboard** (`llm-usage-dashboard.json`)
   - LLM API call rate
   - Token usage (prompt and completion)
   - LLM error rates
   - Cost estimation

4. **System Resources Dashboard** (`system-resources-dashboard.json`)
   - CPU utilization
   - Memory usage
   - Disk I/O
   - Network traffic

### Importing Dashboards

#### Method 1: Auto-provisioning (Recommended)

Dashboards in `monitoring/grafana/` are auto-imported on Grafana startup via provisioning directory.

#### Method 2: Manual Import

1. Access Grafana at <http://localhost:3000>
2. Login with `admin` / `admin`
3. Navigate to **Dashboards** → **Import**
4. Click **Upload JSON file**
5. Select a dashboard from `monitoring/grafana/`
6. Choose "Prometheus" as the datasource
7. Click **Import**

## Alerting

### Alert Rules

Prometheus alert rules are defined in `monitoring/prometheus/alerts.yml`:

- **HighErrorRate** - Triggers when error rate >5% for 5 minutes
- **SlowResponseTime** - Triggers when p95 latency >5s for 5 minutes
- **HighRequestLatency** - Triggers when p99 latency >10s for 5 minutes
- **API Down** - Triggers when API health check fails
- **High Memory Usage** - Triggers when memory >90% for 5 minutes
- **Disk Space Low** - Triggers when disk usage >85%

### Alert Routing

Alertmanager routes alerts based on severity and component:

- **Critical Alerts** → `critical-alerts` receiver (immediate notification)
- **Warning Alerts** → `warning-alerts` receiver (grouped, 4-hour repeat)
- **Discovery Alerts** → `discovery-alerts` receiver
- **LLM Alerts** → `llm-alerts` receiver

Configuration: `monitoring/alertmanager.yml`

### Slack Notifications (Production)

For production deployment with Slack notifications:

1. Create Slack incoming webhooks for each channel:
   - `#signal-harvester-critical`
   - `#signal-harvester-alerts`
   - `#signal-harvester-discovery`
   - `#signal-harvester-llm`

2. Update `monitoring/alertmanager.yml` with Slack webhook URLs:

```yaml
receivers:
  - name: 'critical-alerts'
    slack_configs:
      - api_url: 'https://hooks.slack.com/services/YOUR/WEBHOOK/URL'
        channel: '#signal-harvester-critical'
        title: '🚨 CRITICAL: {{ .GroupLabels.alertname }}'
        send_resolved: true
```

3. Restart Alertmanager to apply changes

### Testing Alerts

Generate test alert by triggering a threshold:

```bash
# Trigger high latency alert (query slow endpoint repeatedly)
for i in {1..100}; do curl http://localhost:8000/discoveries?limit=1000; done

# View active alerts in Prometheus
open http://localhost:9090/alerts

# View alerts in Alertmanager
open http://localhost:9093
```

## Performance Baseline

Signal Harvester API performance baseline (established 2025-11-12):

- **p95 Latency**: 11.58ms (98% better than 500ms SLA)
- **p99 Latency**: 39.17ms (96% better than 1000ms SLA)
- **Error Rate**: 0% (on implemented endpoints)
- **Throughput**: 7.46 req/s (100 concurrent users)

Detailed report: `results/LOAD_TEST_BASELINE_REPORT.md`

## Monitoring Best Practices

### Regular Checks

1. **Daily**: Review Grafana dashboards for anomalies
2. **Weekly**: Check Prometheus target health (`/targets` page)
3. **Monthly**: Review alert rule effectiveness and tune thresholds

### Prometheus Query Examples

```promql
# API request rate (requests per second)
rate(http_requests_total[5m])

# API p95 latency
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# Error rate by status code
rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m])

# Memory usage percentage
process_resident_memory_bytes / node_memory_MemTotal_bytes * 100
```

### Alert Tuning

If experiencing alert fatigue:

1. Increase thresholds in `monitoring/prometheus/alerts.yml`
2. Adjust `repeat_interval` in `monitoring/alertmanager.yml`
3. Add inhibition rules to suppress redundant alerts

## Troubleshooting

### Service Not Starting

```bash
# Check service logs
docker-compose -f docker-compose.monitoring.yml logs <service-name>

# Common issues:
# - Port conflicts: Stop conflicting services or change ports
# - Volume permissions: Check Docker volume mount permissions
# - Configuration errors: Validate YAML syntax
```

### Prometheus Not Scraping API

```bash
# Verify API /prometheus endpoint
curl http://localhost:8000/prometheus

# Check Prometheus targets page
open http://localhost:9090/targets

# Common issues:
# - API not exposing /prometheus endpoint (check PrometheusMiddleware)
# - Network connectivity (verify monitoring Docker network)
# - Scrape timeout (increase timeout in prometheus-docker.yml)
```

### Grafana Datasource Connection Failed

```bash
# Verify Prometheus is healthy
curl http://localhost:9090/-/healthy

# Check Grafana datasource config
docker exec signal-harvester-grafana cat /etc/grafana/provisioning/datasources/datasources.yml

# Common issues:
# - Incorrect Prometheus URL (should be http://prometheus:9090)
# - Datasource not auto-provisioned (check volume mount)
```

### Alertmanager Configuration Error

```bash
# Validate Alertmanager config
docker exec signal-harvester-alertmanager amtool check-config /etc/alertmanager/alertmanager.yml

# Common issues:
# - Invalid YAML syntax
# - Missing receiver definitions
# - Slack webhook URL format (must be full HTTPS URL)
```

## Stopping the Stack

```bash
# Stop all services (keeps volumes)
docker-compose -f docker-compose.monitoring.yml down

# Stop and remove volumes (WARNING: deletes metrics data)
docker-compose -f docker-compose.monitoring.yml down -v
```

## Next Steps

1. **Week 2 Task 3**: Deploy to Kubernetes for production
2. **Autoscaling**: Configure HPA based on load test findings
3. **Service Mesh**: Implement Istio for advanced traffic management
4. **Distributed Tracing**: Add OpenTelemetry for request tracing

## References

- [Prometheus Documentation](https://prometheus.io/docs/introduction/overview/)
- [Grafana Documentation](https://grafana.com/docs/grafana/latest/)
- [Alertmanager Documentation](https://prometheus.io/docs/alerting/latest/alertmanager/)
- [Load Test Baseline](../results/LOAD_TEST_BASELINE_REPORT.md)
- [Phase Three Roadmap](../ARCHITECTURE_AND_READINESS.md)
