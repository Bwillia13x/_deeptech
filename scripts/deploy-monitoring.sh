#!/usr/bin/env bash
#
# deploy-monitoring.sh - Deploy Prometheus and Grafana monitoring stack to Kubernetes
#
# Usage:
#   ./scripts/deploy-monitoring.sh [namespace]
#
# Arguments:
#   namespace - Kubernetes namespace (default: signal-harvester)
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
NAMESPACE="${1:-signal-harvester}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo -e "${GREEN}Signal Harvester Monitoring Stack Deployment${NC}"
echo "Namespace: ${NAMESPACE}"
echo ""

# Function to check if command exists
check_command() {
    if ! command -v "$1" &> /dev/null; then
        echo -e "${RED}Error: $1 is not installed${NC}"
        exit 1
    fi
}

# Check required commands
echo "Checking prerequisites..."
check_command kubectl
check_command jq
echo -e "${GREEN}✓ Prerequisites met${NC}"
echo ""

# Create namespace if it doesn't exist
echo "Creating namespace ${NAMESPACE}..."
kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -
echo -e "${GREEN}✓ Namespace ready${NC}"
echo ""

# Deploy Prometheus ConfigMaps
echo "Deploying Prometheus configuration..."
kubectl create configmap prometheus-config \
    --from-file=prometheus.yml="${PROJECT_ROOT}/monitoring/prometheus/prometheus.yml" \
    --from-file=alerts.yml="${PROJECT_ROOT}/monitoring/prometheus/alerts.yml" \
    --namespace="${NAMESPACE}" \
    --dry-run=client -o yaml | kubectl apply -f -
echo -e "${GREEN}✓ Prometheus ConfigMap created${NC}"

# Deploy Prometheus resources (excluding ConfigMap)
echo "Deploying Prometheus..."
kubectl apply -f "${PROJECT_ROOT}/monitoring/k8s/prometheus.yaml" --namespace="${NAMESPACE}"
echo -e "${GREEN}✓ Prometheus deployed${NC}"
echo ""

# Wait for Prometheus to be ready
echo "Waiting for Prometheus to be ready..."
kubectl wait --for=condition=ready pod -l app=prometheus --namespace="${NAMESPACE}" --timeout=300s || {
    echo -e "${YELLOW}Warning: Prometheus pod not ready within timeout${NC}"
}
echo -e "${GREEN}✓ Prometheus ready${NC}"
echo ""

# Deploy Grafana ConfigMaps
echo "Deploying Grafana dashboards..."
kubectl create configmap grafana-dashboards \
    --from-file=api-performance.json="${PROJECT_ROOT}/monitoring/grafana/api-performance-dashboard.json" \
    --from-file=discovery-pipeline.json="${PROJECT_ROOT}/monitoring/grafana/discovery-pipeline-dashboard.json" \
    --from-file=llm-usage.json="${PROJECT_ROOT}/monitoring/grafana/llm-usage-dashboard.json" \
    --from-file=system-resources.json="${PROJECT_ROOT}/monitoring/grafana/system-resources-dashboard.json" \
    --namespace="${NAMESPACE}" \
    --dry-run=client -o yaml | kubectl apply -f -
echo -e "${GREEN}✓ Grafana dashboards ConfigMap created${NC}"

# Check if Grafana admin secret exists
if ! kubectl get secret grafana-admin --namespace="${NAMESPACE}" &> /dev/null; then
    echo -e "${YELLOW}Warning: grafana-admin secret not found${NC}"
    echo "Creating default Grafana admin secret (change in production!)..."
    kubectl create secret generic grafana-admin \
        --from-literal=password='admin123' \
        --namespace="${NAMESPACE}"
    echo -e "${YELLOW}⚠ Default password created. Change immediately in production!${NC}"
fi

# Deploy Grafana resources (excluding ConfigMaps)
echo "Deploying Grafana..."
kubectl apply -f "${PROJECT_ROOT}/monitoring/k8s/grafana.yaml" --namespace="${NAMESPACE}"
echo -e "${GREEN}✓ Grafana deployed${NC}"
echo ""

# Wait for Grafana to be ready
echo "Waiting for Grafana to be ready..."
kubectl wait --for=condition=ready pod -l app=grafana --namespace="${NAMESPACE}" --timeout=300s || {
    echo -e "${YELLOW}Warning: Grafana pod not ready within timeout${NC}"
}
echo -e "${GREEN}✓ Grafana ready${NC}"
echo ""

# Display access information
echo -e "${GREEN}Deployment complete!${NC}"
echo ""
echo "Access Prometheus:"
echo "  kubectl -n ${NAMESPACE} port-forward svc/prometheus 9090:9090"
echo "  Then visit: http://localhost:9090"
echo ""
echo "Access Grafana:"
echo "  kubectl -n ${NAMESPACE} port-forward svc/grafana 3000:3000"
echo "  Then visit: http://localhost:3000"
echo "  Default credentials: admin / admin123 (change immediately!)"
echo ""
echo "Check Prometheus targets:"
echo "  kubectl -n ${NAMESPACE} port-forward svc/prometheus 9090:9090"
echo "  Visit: http://localhost:9090/targets"
echo ""
echo "View deployed resources:"
echo "  kubectl -n ${NAMESPACE} get all -l component=monitoring"
echo ""
echo -e "${YELLOW}Note: Update hostnames in Ingress resources for external access${NC}"
