#!/usr/bin/env bash
#
# validate-monitoring.sh - Validate monitoring stack configuration
#
# Usage:
#   ./scripts/validate-monitoring.sh
#

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo -e "${GREEN}Signal Harvester Monitoring Stack Validation${NC}"
echo ""

ERRORS=0

# Validate Prometheus configuration
echo "Validating Prometheus configuration..."
if command -v promtool &> /dev/null; then
    if promtool check config "${PROJECT_ROOT}/monitoring/prometheus/prometheus.yml"; then
        echo -e "${GREEN}✓ prometheus.yml is valid${NC}"
    else
        echo -e "${RED}✗ prometheus.yml has errors${NC}"
        ((ERRORS++))
    fi
    
    if promtool check rules "${PROJECT_ROOT}/monitoring/prometheus/alerts.yml"; then
        echo -e "${GREEN}✓ alerts.yml is valid${NC}"
    else
        echo -e "${RED}✗ alerts.yml has errors${NC}"
        ((ERRORS++))
    fi
else
    echo -e "${YELLOW}⚠ promtool not installed, skipping Prometheus validation${NC}"
    echo "  Install with: brew install prometheus (macOS) or apt-get install prometheus (Linux)"
fi
echo ""

# Validate Grafana dashboards
echo "Validating Grafana dashboards..."
DASHBOARD_COUNT=0
for dashboard in "${PROJECT_ROOT}"/monitoring/grafana/*.json; do
    if python3 -c "import json; json.load(open('${dashboard}'))" 2>/dev/null; then
        echo -e "${GREEN}✓ $(basename "${dashboard}") is valid JSON${NC}"
        ((DASHBOARD_COUNT++))
    else
        echo -e "${RED}✗ $(basename "${dashboard}") has JSON errors${NC}"
        ((ERRORS++))
    fi
done
echo "Found ${DASHBOARD_COUNT} valid dashboard(s)"
echo ""

# Validate Kubernetes manifests
echo "Validating Kubernetes manifests..."
if command -v kubectl &> /dev/null; then
    # Check if kubectl can connect to a cluster
    if kubectl cluster-info &>/dev/null; then
        for manifest in "${PROJECT_ROOT}"/monitoring/k8s/*.yaml; do
            if kubectl apply --dry-run=client -f "${manifest}" &>/dev/null; then
                echo -e "${GREEN}✓ $(basename "${manifest}") is valid${NC}"
            else
                echo -e "${RED}✗ $(basename "${manifest}") has errors${NC}"
                ((ERRORS++))
            fi
        done
    else
        echo -e "${YELLOW}⚠ kubectl installed but no cluster available, skipping K8s validation${NC}"
        # Basic YAML syntax check
        if command -v python3 &> /dev/null; then
            if python3 -c "import yaml" 2>/dev/null; then
                for manifest in "${PROJECT_ROOT}"/monitoring/k8s/*.yaml; do
                    if python3 -c "import yaml; list(yaml.safe_load_all(open('${manifest}')))" 2>/dev/null; then
                        echo -e "${GREEN}✓ $(basename "${manifest}") has valid YAML syntax${NC}"
                    else
                        echo -e "${RED}✗ $(basename "${manifest}") has YAML syntax errors${NC}"
                        ((ERRORS++))
                    fi
                done
            else
                echo -e "${YELLOW}⚠ PyYAML not installed, skipping YAML syntax validation${NC}"
                echo "  Install with: pip3 install pyyaml"
            fi
        fi
    fi
else
    echo -e "${YELLOW}⚠ kubectl not installed, skipping K8s validation${NC}"
fi
echo ""

# Validate Python module
echo "Validating Prometheus metrics module..."
cd "${PROJECT_ROOT}"

# Check if prometheus_client is installed
if python3 -c "import prometheus_client" 2>/dev/null; then
    if python3 -c "from src.signal_harvester.prometheus_metrics import PrometheusMiddleware, get_prometheus_metrics" 2>/dev/null; then
        echo -e "${GREEN}✓ prometheus_metrics.py imports successfully${NC}"
    else
        echo -e "${RED}✗ prometheus_metrics.py has import errors${NC}"
        ((ERRORS++))
    fi
else
    echo -e "${YELLOW}⚠ prometheus_client not installed, checking syntax only${NC}"
    # Basic syntax check
    if python3 -m py_compile src/signal_harvester/prometheus_metrics.py 2>/dev/null; then
        echo -e "${GREEN}✓ prometheus_metrics.py has valid Python syntax${NC}"
    else
        echo -e "${RED}✗ prometheus_metrics.py has syntax errors${NC}"
        ((ERRORS++))
    fi
fi
echo ""

# Check file structure
echo "Checking file structure..."
REQUIRED_FILES=(
    "monitoring/prometheus/prometheus.yml"
    "monitoring/prometheus/alerts.yml"
    "monitoring/grafana/api-performance-dashboard.json"
    "monitoring/grafana/discovery-pipeline-dashboard.json"
    "monitoring/grafana/llm-usage-dashboard.json"
    "monitoring/grafana/system-resources-dashboard.json"
    "monitoring/k8s/prometheus.yaml"
    "monitoring/k8s/grafana.yaml"
    "src/signal_harvester/prometheus_metrics.py"
    "scripts/deploy-monitoring.sh"
    "docs/MONITORING.md"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "${PROJECT_ROOT}/${file}" ]; then
        echo -e "${GREEN}✓ ${file}${NC}"
    else
        echo -e "${RED}✗ ${file} not found${NC}"
        ((ERRORS++))
    fi
done
echo ""

# Summary
if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}✓ All validation checks passed!${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    exit 0
else
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${RED}✗ Validation failed with ${ERRORS} error(s)${NC}"
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    exit 1
fi
