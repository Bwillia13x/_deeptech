# Signal Harvester Monitoring Guide

## Overview

Signal Harvester uses a comprehensive monitoring stack based on Prometheus and Grafana to provide real-time visibility into application performance, resource utilization, and operational health.

## Architecture

```
┌─────────────────────┐
│   Signal Harvester  │
│   FastAPI App       │──────> Prometheus Metrics Endpoint
│   /metrics/prometheus │      (/metrics/prometheus)
└─────────────────────┘
         │
         │ Metrics Collection
         ▼
┌─────────────────────┐
│    Prometheus       │
│  - Scrapes metrics  │
│  - Evaluates alerts │──────> Alert Manager
│  - Stores time      │        (notifications)
│    series data      │
└─────────────────────┘
         │
         │ PromQL Queries
         ▼
┌─────────────────────┐
│      Grafana        │
│  - Dashboards       │
│  - Visualizations   │
│  - User Interface   │
└─────────────────────┘
```

## Metrics Collected

### HTTP Metrics

- **http_requests_total**: Total HTTP requests by endpoint, method, status
- **http_request_duration_seconds**: Request latency histogram
- **http_requests_in_progress**: Current concurrent requests

### Database Metrics

- **db_size_bytes**: Database file size
- **db_connections_active**: Active database connections
- **db_query_duration_seconds**: Query execution time histogram

### Discovery Pipeline Metrics

- **discoveries_total**: Total discoveries collected
- **discoveries_by_source**: Discoveries by source (arXiv, GitHub, X, etc.)
- **discoveries_fetch_duration_seconds**: Fetch operation duration
- **pipeline_runs_total**: Pipeline executions by status
- **pipeline_run_duration_seconds**: Pipeline execution time
- **pipeline_errors_total**: Pipeline errors by stage

### Topic Metrics

- **topics_total**: Total topics tracked
- **topics_active**: Currently active topics
- **topic_artifacts_total**: Topic-artifact assignments

### Entity Metrics

- **entities_total**: Total entities tracked
- **entity_resolutions_total**: Entity resolution operations
- **entity_merges_total**: Entity merge operations

### LLM Metrics

- **llm_requests_total**: LLM API requests by provider, model, status
- **llm_request_duration_seconds**: LLM request latency
- **llm_tokens_total**: Token usage by provider, model, type (prompt/completion)

### Cache Metrics

- **cache_hits_total**: Cache hit count
- **cache_misses_total**: Cache miss count
- **cache_size_items**: Current cache size
- **cache_evictions_total**: Cache evictions

### Embedding Metrics

- **embeddings_generated_total**: Embeddings computed
- **embedding_cache_size**: Embedding cache size

## Dashboards

### 1. API Performance Dashboard

**URL**: <http://grafana.signal-harvester.example.com/d/api-performance>

**Panels**:

- Request Rate (requests/sec by status code)
- Error Rate (% of 5xx responses)
- Request Duration p95 (by endpoint)
- Concurrent Requests
- Database Size & Query Duration
- Signals/Discoveries/Topics Total
- Cache Hit Rate

**Use Cases**:

- Monitor API health and responsiveness
- Identify slow endpoints
- Track error rates
- Verify database performance

### 2. Discovery Pipeline Dashboard

**URL**: <http://grafana.signal-harvester.example.com/d/discovery-pipeline>

**Panels**:

- Discoveries by Source (stacked graph)
- Fetch Duration by Source (p50, p95)
- Pipeline Success Rate
- Pipeline Duration
- Topic Evolution (active topics, new topics/hour)
- Topic-Artifact Coverage (gauge showing % coverage)
- Entity Resolution Activity
- Cross-Source Relationships
- Pipeline Errors (24h count)
- Last Pipeline Run (hours ago)

**Use Cases**:

- Monitor pipeline execution health
- Track source-specific performance
- Verify topic coverage requirements (95%+ target)
- Identify relationship detection trends
- Detect pipeline failures

### 3. LLM Usage & Costs Dashboard

**URL**: <http://grafana.signal-harvester.example.com/d/llm-usage>

**Panels**:

- LLM Requests by Provider (OpenAI, Anthropic, xAI)
- Request Duration by Provider (p50, p95)
- Token Usage by Provider (prompt vs completion)
- Model Usage Distribution (pie chart)
- LLM Error Rate
- Estimated Hourly Cost (OpenAI)
- Total Requests/Tokens (24h)
- Average Response Time
- Estimated Daily Cost (all providers)
- Success Rate by Provider

**Use Cases**:

- Monitor LLM API costs
- Optimize provider selection
- Track token consumption
- Identify high-latency models
- Budget forecasting

### 4. System Resources Dashboard

**URL**: <http://grafana.signal-harvester.example.com/d/system-resources>

**Panels**:

- CPU Usage (%)
- Memory Usage (RSS, Virtual)
- Database Size Growth (size + growth rate)
- Database Connections
- Cache Performance (hits, misses, evictions)
- Cache Size
- Pod Restarts
- Open File Descriptors
- Current CPU % (gauge)
- Current Memory (gauge)
- Cache Hit Rate (gauge)
- Database Size (stat)

**Use Cases**:

- Monitor resource utilization
- Detect memory leaks
- Track database growth
- Identify pod stability issues
- Verify cache efficiency

## Alerting Rules

### Critical Alerts

#### HighErrorRate

- **Condition**: Error rate > 5% for 5 minutes
- **Severity**: Critical
- **Action**: Investigate API errors, check logs, verify external dependencies

#### APIDown

- **Condition**: No successful requests for 2 minutes
- **Severity**: Critical
- **Action**: Check pod status, verify service health, restart if needed

#### HighMemoryUsage

- **Condition**: Memory usage > 90% for 5 minutes
- **Severity**: Critical
- **Action**: Investigate memory leaks, consider scaling, restart pod

#### HighCPUUsage

- **Condition**: CPU usage > 90% for 10 minutes
- **Severity**: Critical
- **Action**: Check for infinite loops, optimize hot paths, scale horizontally

### Warning Alerts

#### SlowResponseTime

- **Condition**: p95 latency > 5s for 5 minutes
- **Severity**: Warning
- **Action**: Profile slow endpoints, optimize queries, check external APIs

#### DatabaseSizeGrowingRapidly

- **Condition**: Database growing > 1GB/hour
- **Severity**: Warning
- **Action**: Review retention policies, check for data leaks, plan capacity

#### PipelineFailures

- **Condition**: Pipeline failure rate > 10%
- **Severity**: Warning
- **Action**: Check source API availability, verify credentials, review errors

#### HighLLMErrorRate

- **Condition**: LLM error rate > 5%
- **Severity**: Warning
- **Action**: Check API keys, verify rate limits, review error responses

#### LowCacheHitRate

- **Condition**: Cache hit rate < 50% for 30 minutes
- **Severity**: Warning
- **Action**: Review cache TTL, verify Redis connectivity, check eviction rate

### Info Alerts

#### PipelineNotRunning

- **Condition**: No pipeline runs for 25 hours
- **Severity**: Info
- **Action**: Check scheduler, verify cron jobs, manual trigger if needed

#### NoDiscoveriesFetched

- **Condition**: Zero discoveries fetched for 2 hours
- **Severity**: Info
- **Action**: Verify source APIs, check search queries, review filters

## Setup Instructions

### Prerequisites

- Kubernetes cluster with kubectl access
- Helm 3.x (optional, for Prometheus Operator)
- Basic auth credentials for Prometheus
- Admin password for Grafana

### Deployment Steps

#### Option 1: Automated Deployment (Recommended)

Use the provided deployment script:

```bash
cd signal-harvester
./scripts/deploy-monitoring.sh [namespace]
```

The script will:

- Create namespace if needed
- Deploy Prometheus ConfigMaps from `monitoring/prometheus/*.yml`
- Deploy Grafana dashboard ConfigMaps from `monitoring/grafana/*.json`
- Create default Grafana admin secret (if not exists)
- Deploy all monitoring resources
- Wait for pods to be ready
- Display access instructions

#### Option 2: Manual Deployment

1. **Create Namespace**:

```bash
kubectl create namespace signal-harvester
```

2. **Deploy Prometheus ConfigMaps**:

```bash
kubectl create configmap prometheus-config \
  --from-file=prometheus.yml=monitoring/prometheus/prometheus.yml \
  --from-file=alerts.yml=monitoring/prometheus/alerts.yml \
  --namespace=signal-harvester \
  --dry-run=client -o yaml | kubectl apply -f -
```

3. **Deploy Prometheus Resources**:

```bash
kubectl apply -f monitoring/k8s/prometheus.yaml --namespace=signal-harvester
```

4. **Verify Prometheus**:

```bash
kubectl -n signal-harvester get pods -l app=prometheus
kubectl -n signal-harvester port-forward svc/prometheus 9090:9090
# Visit http://localhost:9090
```

5. **Create Grafana Admin Secret**:

```bash
kubectl -n signal-harvester create secret generic grafana-admin \
  --from-literal=password='YOUR_SECURE_PASSWORD'
```

6. **Deploy Grafana ConfigMaps**:

```bash
kubectl create configmap grafana-dashboards \
  --from-file=api-performance.json=monitoring/grafana/api-performance-dashboard.json \
  --from-file=discovery-pipeline.json=monitoring/grafana/discovery-pipeline-dashboard.json \
  --from-file=llm-usage.json=monitoring/grafana/llm-usage-dashboard.json \
  --from-file=system-resources.json=monitoring/grafana/system-resources-dashboard.json \
  --namespace=signal-harvester \
  --dry-run=client -o yaml | kubectl apply -f -
```

7. **Deploy Grafana Resources**:

```bash
kubectl apply -f monitoring/k8s/grafana.yaml --namespace=signal-harvester
```

5. **Deploy Grafana**:

```bash
kubectl apply -f monitoring/k8s/grafana.yaml
```

6. **Verify Grafana**:

```bash
kubectl -n signal-harvester get pods -l app=grafana
kubectl -n signal-harvester port-forward svc/grafana 3000:3000
# Visit http://localhost:3000
# Login: admin / YOUR_SECURE_PASSWORD
```

7. **Configure Ingress**:
Edit `prometheus.yaml` and `grafana.yaml` to set correct hostnames:

```yaml
# Update these lines
- host: prometheus.your-domain.com
- host: grafana.your-domain.com
```

8. **Apply Ingress Updates**:

```bash
kubectl apply -f monitoring/k8s/prometheus.yaml
kubectl apply -f monitoring/k8s/grafana.yaml
```

9. **Verify Metrics Collection**:

- Open Prometheus UI
- Navigate to Status > Targets
- Verify signal-harvester pods are UP
- Query: `up{job="signal-harvester"}`

10. **Import Dashboards**:
Dashboards are automatically provisioned from ConfigMaps. Verify in Grafana:

- Home > Dashboards
- Should see 4 dashboards under "Signal Harvester" folder

### Local Development

For local development without Kubernetes:

1. **Run Prometheus Locally**:

```bash
cd monitoring/prometheus
prometheus --config.file=prometheus.yml
```

2. **Run Grafana Locally**:

```bash
docker run -d \
  -p 3000:3000 \
  --name=grafana \
  -v $(pwd)/monitoring/grafana:/var/lib/grafana/dashboards \
  grafana/grafana:10.0.0
```

3. **Configure Datasource**:

- Add Prometheus datasource pointing to <http://localhost:9090>

4. **Import Dashboards**:

- Import each JSON file from `monitoring/grafana/`

## Monitoring Workflows

### Daily Health Check

1. Open API Performance dashboard
2. Verify error rate < 1%
3. Check p95 latency < 2s
4. Confirm no active alerts

### Weekly Review

1. Open LLM Usage dashboard
2. Review daily cost trends
3. Identify optimization opportunities
4. Check token usage patterns

### Monthly Capacity Planning

1. Open System Resources dashboard
2. Review database growth trends
3. Project storage needs
4. Plan scaling actions

### Incident Response

1. Check active alerts in Prometheus
2. Open relevant dashboard
3. Identify affected metrics
4. Follow alert-specific action items
5. Document resolution

## Alert Response Procedures

### High Error Rate

1. Check recent deployments: `kubectl -n signal-harvester rollout history deployment/signal-harvester`
2. Review logs: `kubectl -n signal-harvester logs -l app=signal-harvester --tail=100`
3. Check external dependencies (X API, LLM providers)
4. Rollback if needed: `kubectl -n signal-harvester rollout undo deployment/signal-harvester`

### API Down

1. Check pod status: `kubectl -n signal-harvester get pods`
2. Describe failing pod: `kubectl -n signal-harvester describe pod <pod-name>`
3. Check events: `kubectl -n signal-harvester get events --sort-by=.metadata.creationTimestamp`
4. Restart deployment: `kubectl -n signal-harvester rollout restart deployment/signal-harvester`

### High Memory/CPU

1. Check resource metrics: `kubectl -n signal-harvester top pods`
2. Review recent pipeline runs
3. Check for memory leaks in logs
4. Profile application if issue persists
5. Scale horizontally: `kubectl -n signal-harvester scale deployment/signal-harvester --replicas=3`

### Pipeline Failures

1. Check pipeline logs: `harvest pipeline --dry-run`
2. Verify source API connectivity
3. Check API credentials in secrets
4. Review error patterns in database
5. Manual pipeline run: `harvest discover fetch`

### LLM Errors

1. Check API key validity
2. Review rate limit headers in logs
3. Verify provider status pages
4. Switch provider if needed
5. Adjust retry backoff

## Prometheus Queries

### Useful PromQL Examples

**Top 10 Slowest Endpoints**:

```promql
topk(10, 
  histogram_quantile(0.95, 
    sum(rate(http_request_duration_seconds_bucket[5m])) by (le, endpoint)
  )
)
```

**Error Rate by Endpoint**:

```promql
sum(rate(http_requests_total{status=~"5.."}[5m])) by (endpoint) 
/ 
sum(rate(http_requests_total[5m])) by (endpoint) 
* 100
```

**LLM Cost per Hour**:

```promql
(
  sum(rate(llm_tokens_total{provider="openai",token_type="prompt"}[1h])) * 0.0015 / 1000
) + (
  sum(rate(llm_tokens_total{provider="openai",token_type="completion"}[1h])) * 0.002 / 1000
)
```

**Database Growth Rate**:

```promql
deriv(db_size_bytes[1h])
```

**Cache Efficiency**:

```promql
sum(rate(cache_hits_total[5m])) 
/ 
(sum(rate(cache_hits_total[5m])) + sum(rate(cache_misses_total[5m]))) 
* 100
```

**Pipeline Success Rate**:

```promql
sum(rate(pipeline_runs_total{status="success"}[1h])) 
/ 
sum(rate(pipeline_runs_total[1h])) 
* 100
```

**Topic Coverage**:

```promql
topic_artifacts_total / discoveries_total * 100
```

## Performance Baselines

### API Performance

- **p50 Latency**: < 200ms
- **p95 Latency**: < 2s
- **p99 Latency**: < 5s
- **Error Rate**: < 1%

### Discovery Pipeline

- **Fetch Duration (arXiv)**: < 30s
- **Fetch Duration (GitHub)**: < 45s
- **Fetch Duration (X)**: < 20s
- **Pipeline Success Rate**: > 95%
- **Topic Coverage**: > 95%

### LLM Performance

- **p95 Latency**: < 10s
- **Error Rate**: < 2%
- **Daily Cost**: Monitor and budget

### Resource Utilization

- **CPU**: < 70% avg
- **Memory**: < 80% avg
- **Database Size**: Plan for 50GB+
- **Cache Hit Rate**: > 80%

## Troubleshooting

### Metrics Not Appearing

**Symptom**: Prometheus shows no data for signal-harvester

**Solutions**:

1. Verify pod annotations:

```bash
kubectl -n signal-harvester get pods -o yaml | grep prometheus.io
```

2. Check Prometheus targets:
   - Open Prometheus UI > Status > Targets
   - Look for signal-harvester pods
3. Verify /metrics/prometheus endpoint:

```bash
kubectl -n signal-harvester port-forward svc/signal-harvester 8000:8000
curl http://localhost:8000/metrics/prometheus
```

### Dashboard Shows "No Data"

**Symptom**: Grafana dashboard panels show "No data"

**Solutions**:

1. Verify datasource:
   - Grafana > Configuration > Data Sources
   - Test Prometheus connection
2. Check time range (top-right)
3. Verify metric exists in Prometheus:
   - Prometheus UI > Graph
   - Query: `{__name__=~".+"}`
4. Check panel query syntax

### High Cardinality Warnings

**Symptom**: Prometheus logs show high cardinality warnings

**Solutions**:

1. Review metric labels
2. Avoid using unbounded labels (IDs, UUIDs)
3. Use PrometheusMiddleware endpoint normalization
4. Adjust recording rules

### Alert Not Firing

**Symptom**: Alert should trigger but doesn't

**Solutions**:

1. Verify alert rule syntax in Prometheus UI
2. Check alert evaluation:
   - Prometheus > Alerts
   - View pending/firing state
3. Test PromQL query in Graph tab
4. Verify Alertmanager config

## Best Practices

1. **Set Appropriate Time Ranges**: Use relative ranges (e.g., "Last 6 hours") for dashboards
2. **Use Recording Rules**: For complex queries used in multiple places
3. **Monitor the Monitors**: Set up alerts for Prometheus/Grafana health
4. **Regular Review**: Weekly review of metrics and alerts
5. **Document Changes**: Update this guide when adding metrics/dashboards
6. **Optimize Queries**: Use rate() for counters, avoid expensive regex
7. **Right-Size Retention**: Balance storage costs vs. historical data needs
8. **Secure Access**: Always use authentication for production monitoring

## References

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [PromQL Basics](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [Grafana Dashboard Best Practices](https://grafana.com/docs/grafana/latest/best-practices/)
- Signal Harvester Operations Guide: `docs/OPERATIONS.md`
- Signal Harvester API Documentation: `docs/API.md`
