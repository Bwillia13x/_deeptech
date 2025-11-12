#!/bin/bash
# Kubernetes Deployment Script for Signal Harvester
# Automates deployment of API and monitoring stack to K8s cluster

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
NAMESPACE="signal-harvester"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
MONITORING_DIR="$PROJECT_ROOT/monitoring"
K8S_DIR="$PROJECT_ROOT/k8s"

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check kubectl
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl not found. Please install kubectl first."
        exit 1
    fi
    
    # Check cluster connection
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster. Please configure kubectl."
        exit 1
    fi
    
    # Check required files
    local required_files=(
        "$K8S_DIR/signal-harvester-api.yaml"
        "$MONITORING_DIR/k8s/prometheus.yaml"
        "$MONITORING_DIR/k8s/grafana.yaml"
        "$MONITORING_DIR/k8s/alertmanager.yaml"
        "$MONITORING_DIR/prometheus/prometheus.yml"
        "$MONITORING_DIR/prometheus/alerts.yml"
    )
    
    for file in "${required_files[@]}"; do
        if [ ! -f "$file" ]; then
            log_error "Required file not found: $file"
            exit 1
        fi
    done
    
    log_success "All prerequisites met"
}

# Create namespace
create_namespace() {
    log_info "Creating namespace: $NAMESPACE"
    
    if kubectl get namespace "$NAMESPACE" &> /dev/null; then
        log_warn "Namespace $NAMESPACE already exists"
    else
        kubectl create namespace "$NAMESPACE"
        log_success "Namespace created"
    fi
}

# Create ConfigMaps from files
create_configmaps() {
    log_info "Creating ConfigMaps from configuration files..."
    
    # Prometheus ConfigMap
    log_info "Creating Prometheus ConfigMap..."
    kubectl create configmap prometheus-config \
        --from-file=prometheus.yml="$MONITORING_DIR/prometheus/prometheus.yml" \
        --from-file=alerts.yml="$MONITORING_DIR/prometheus/alerts.yml" \
        --namespace="$NAMESPACE" \
        --dry-run=client -o yaml | kubectl apply -f -
    
    # Grafana Dashboards ConfigMap (if dashboard files exist)
    if [ -d "$MONITORING_DIR/grafana/dashboards" ]; then
        log_info "Creating Grafana dashboards ConfigMap..."
        local dashboard_count=$(find "$MONITORING_DIR/grafana/dashboards" -name "*.json" | wc -l)
        
        if [ "$dashboard_count" -gt 0 ]; then
            kubectl create configmap grafana-dashboards \
                --from-file="$MONITORING_DIR/grafana/dashboards/" \
                --namespace="$NAMESPACE" \
                --dry-run=client -o yaml | kubectl apply -f -
            log_success "Created ConfigMap with $dashboard_count dashboards"
        else
            log_warn "No dashboard JSON files found in $MONITORING_DIR/grafana/dashboards"
        fi
    else
        log_warn "Grafana dashboards directory not found: $MONITORING_DIR/grafana/dashboards"
    fi
    
    log_success "ConfigMaps created"
}

# Create secrets
create_secrets() {
    log_info "Creating secrets..."
    
    # Check for .env file with API keys
    if [ -f "$PROJECT_ROOT/.env" ]; then
        log_info "Loading secrets from .env file..."
        
        # Source .env file
        set -a
        source "$PROJECT_ROOT/.env"
        set +a
        
        # Create API secret
        kubectl create secret generic signal-harvester-api-keys \
            --from-literal=x-bearer-token="${X_BEARER_TOKEN:-}" \
            --from-literal=openai-api-key="${OPENAI_API_KEY:-}" \
            --from-literal=anthropic-api-key="${ANTHROPIC_API_KEY:-}" \
            --from-literal=harvest-api-key="${HARVEST_API_KEY:-}" \
            --from-literal=slack-webhook-url="${SLACK_WEBHOOK_URL:-}" \
            --from-literal=grafana-admin-password="${GRAFANA_ADMIN_PASSWORD:-admin}" \
            --namespace="$NAMESPACE" \
            --dry-run=client -o yaml | kubectl apply -f -
        
        log_success "API secrets created from .env file"
    else
        log_warn ".env file not found. Secrets must be created manually."
        log_warn "Run: kubectl create secret generic signal-harvester-api-keys \\"
        log_warn "  --from-literal=x-bearer-token=YOUR_TOKEN \\"
        log_warn "  --from-literal=openai-api-key=YOUR_KEY \\"
        log_warn "  --namespace=$NAMESPACE"
    fi
}

# Apply Kubernetes manifests
apply_manifests() {
    log_info "Applying Kubernetes manifests..."
    
    # Order matters: namespace → configmaps → secrets → pvcs → deployments → services → ingress
    
    # Apply API manifests
    log_info "Deploying Signal Harvester API..."
    kubectl apply -f "$K8S_DIR/signal-harvester-api.yaml" --namespace="$NAMESPACE"
    
    # Apply monitoring manifests
    log_info "Deploying Prometheus..."
    kubectl apply -f "$MONITORING_DIR/k8s/prometheus.yaml" --namespace="$NAMESPACE"
    
    log_info "Deploying Grafana..."
    kubectl apply -f "$MONITORING_DIR/k8s/grafana.yaml" --namespace="$NAMESPACE"
    
    log_info "Deploying Alertmanager..."
    kubectl apply -f "$MONITORING_DIR/k8s/alertmanager.yaml" --namespace="$NAMESPACE"
    
    log_success "All manifests applied"
}

# Wait for deployments to be ready
wait_for_deployments() {
    log_info "Waiting for deployments to be ready..."
    
    local deployments=(
        "signal-harvester-api"
        "prometheus"
        "grafana"
        "alertmanager"
    )
    
    for deployment in "${deployments[@]}"; do
        log_info "Waiting for $deployment..."
        
        if kubectl rollout status deployment/"$deployment" --namespace="$NAMESPACE" --timeout=300s; then
            log_success "$deployment is ready"
        else
            log_error "$deployment failed to become ready"
            kubectl get pods --namespace="$NAMESPACE" -l app="$deployment"
            return 1
        fi
    done
    
    log_success "All deployments are ready"
}

# Health checks
health_checks() {
    log_info "Running health checks..."
    
    # Check pod status
    log_info "Pod status:"
    kubectl get pods --namespace="$NAMESPACE" -o wide
    
    # Check services
    log_info "Service endpoints:"
    kubectl get services --namespace="$NAMESPACE"
    
    # Check PVCs
    log_info "Persistent Volume Claims:"
    kubectl get pvc --namespace="$NAMESPACE"
    
    # Check HPA status
    log_info "HorizontalPodAutoscaler status:"
    kubectl get hpa --namespace="$NAMESPACE"
    
    # Test API health endpoint (if accessible)
    log_info "Testing API health endpoint..."
    local api_pod=$(kubectl get pods --namespace="$NAMESPACE" -l app=signal-harvester-api -o jsonpath='{.items[0].metadata.name}')
    
    if [ -n "$api_pod" ]; then
        if kubectl exec "$api_pod" --namespace="$NAMESPACE" -- curl -s http://localhost:8000/health > /dev/null; then
            log_success "API health check passed"
        else
            log_warn "API health check failed (pod may still be starting)"
        fi
    fi
    
    log_success "Health checks complete"
}

# Display access information
display_access_info() {
    log_info "Deployment complete! Access information:"
    echo ""
    
    # Get ingress hosts
    local api_host=$(kubectl get ingress signal-harvester-api --namespace="$NAMESPACE" -o jsonpath='{.spec.rules[0].host}' 2>/dev/null || echo "Not configured")
    local prometheus_host=$(kubectl get ingress prometheus --namespace="$NAMESPACE" -o jsonpath='{.spec.rules[0].host}' 2>/dev/null || echo "Not configured")
    local grafana_host=$(kubectl get ingress grafana --namespace="$NAMESPACE" -o jsonpath='{.spec.rules[0].host}' 2>/dev/null || echo "Not configured")
    local alertmanager_host=$(kubectl get ingress alertmanager --namespace="$NAMESPACE" -o jsonpath='{.spec.rules[0].host}' 2>/dev/null || echo "Not configured")
    
    echo -e "${GREEN}Signal Harvester API:${NC}"
    echo "  Ingress: https://$api_host"
    echo "  Port Forward: kubectl port-forward -n $NAMESPACE svc/signal-harvester-api 8000:8000"
    echo "  Health: https://$api_host/health"
    echo ""
    
    echo -e "${GREEN}Prometheus:${NC}"
    echo "  Ingress: https://$prometheus_host"
    echo "  Port Forward: kubectl port-forward -n $NAMESPACE svc/prometheus 9090:9090"
    echo "  Targets: https://$prometheus_host/targets"
    echo ""
    
    echo -e "${GREEN}Grafana:${NC}"
    echo "  Ingress: https://$grafana_host"
    echo "  Port Forward: kubectl port-forward -n $NAMESPACE svc/grafana 3000:3000"
    echo "  Username: admin"
    echo "  Password: (from secret grafana-admin-password)"
    echo ""
    
    echo -e "${GREEN}Alertmanager:${NC}"
    echo "  Ingress: https://$alertmanager_host"
    echo "  Port Forward: kubectl port-forward -n $NAMESPACE svc/alertmanager 9093:9093"
    echo ""
    
    echo -e "${YELLOW}Next Steps:${NC}"
    echo "  1. Configure DNS to point ingress hosts to your cluster"
    echo "  2. Update Slack webhook URLs in alertmanager-slack-urls secret"
    echo "  3. Import Grafana dashboards from monitoring/grafana/dashboards/"
    echo "  4. Configure TLS certificates (cert-manager should handle this automatically)"
    echo "  5. Monitor scaling behavior: kubectl get hpa -n $NAMESPACE --watch"
    echo ""
    
    echo -e "${BLUE}Useful Commands:${NC}"
    echo "  View logs: kubectl logs -n $NAMESPACE -l app=signal-harvester-api -f"
    echo "  Scale manually: kubectl scale deployment signal-harvester-api -n $NAMESPACE --replicas=5"
    echo "  Restart deployment: kubectl rollout restart deployment/signal-harvester-api -n $NAMESPACE"
    echo "  Debug pod: kubectl exec -it -n $NAMESPACE POD_NAME -- /bin/sh"
    echo ""
}

# Cleanup function
cleanup() {
    log_info "Starting cleanup..."
    
    read -p "This will delete all resources in namespace $NAMESPACE. Continue? (y/N) " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "Deleting all resources..."
        kubectl delete namespace "$NAMESPACE" --wait=true
        log_success "Cleanup complete"
    else
        log_info "Cleanup cancelled"
    fi
}

# Rollback function
rollback() {
    log_info "Rolling back deployments..."
    
    local deployments=(
        "signal-harvester-api"
        "prometheus"
        "grafana"
        "alertmanager"
    )
    
    for deployment in "${deployments[@]}"; do
        log_info "Rolling back $deployment..."
        kubectl rollout undo deployment/"$deployment" --namespace="$NAMESPACE"
    done
    
    log_success "Rollback complete"
}

# Main function
main() {
    echo -e "${BLUE}╔══════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║  Signal Harvester - Kubernetes Deployment Script   ║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════════════════════╝${NC}"
    echo ""
    
    # Parse command line arguments
    case "${1:-}" in
        cleanup)
            cleanup
            exit 0
            ;;
        rollback)
            rollback
            exit 0
            ;;
        "")
            # Normal deployment
            ;;
        *)
            log_error "Unknown command: $1"
            echo "Usage: $0 [cleanup|rollback]"
            exit 1
            ;;
    esac
    
    # Execute deployment steps
    check_prerequisites
    create_namespace
    create_configmaps
    create_secrets
    apply_manifests
    wait_for_deployments
    health_checks
    display_access_info
    
    log_success "Deployment completed successfully! 🚀"
}

# Run main function
main "$@"
