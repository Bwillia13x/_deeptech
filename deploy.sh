#!/bin/bash
# Kubernetes deployment helper script for Signal Harvester

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_DIR="${SCRIPT_DIR}/k8s"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

usage() {
    cat <<EOF
Usage: $0 <command> [options]

Commands:
    validate <env>          Validate manifests for environment (staging|production)
    deploy <env>            Deploy to environment (staging|production)
    status <env>            Check deployment status
    logs <env>              Tail application logs
    rollback <env>          Rollback to previous version
    scale <env> <replicas>  Scale deployment
    exec <env>              Open shell in pod
    migrate <env>           Run database migrations
    backup <env>            Backup database
    restore <env> <file>    Restore database from backup

Examples:
    $0 validate staging
    $0 deploy production
    $0 status production
    $0 logs staging
    $0 rollback production
    $0 scale production 5
    $0 exec production
    $0 migrate production
    $0 backup production
    $0 restore production backup.db
EOF
    exit 1
}

check_prerequisites() {
    local missing=()
    
    command -v kubectl >/dev/null 2>&1 || missing+=("kubectl")
    command -v kustomize >/dev/null 2>&1 || missing+=("kustomize")
    
    if [ ${#missing[@]} -gt 0 ]; then
        echo -e "${RED}Error: Missing required tools: ${missing[*]}${NC}"
        echo "Please install missing tools and try again."
        exit 1
    fi
}

get_namespace() {
    local env=$1
    if [ "$env" = "staging" ]; then
        echo "signal-harvester-staging"
    elif [ "$env" = "production" ]; then
        echo "signal-harvester-production"
    else
        echo -e "${RED}Error: Invalid environment: $env${NC}"
        exit 1
    fi
}

get_deployment_name() {
    local env=$1
    if [ "$env" = "staging" ]; then
        echo "staging-signal-harvester"
    else
        echo "prod-signal-harvester"
    fi
}

validate() {
    local env=$1
    local namespace=$(get_namespace "$env")
    
    echo -e "${YELLOW}Validating manifests for $env environment...${NC}"
    
    if ! kubectl kustomize "${K8S_DIR}/overlays/${env}" > /dev/null; then
        echo -e "${RED}Validation failed!${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}✓ Manifests are valid${NC}"
    
    # Show preview
    echo ""
    echo -e "${YELLOW}Generated manifests preview:${NC}"
    kubectl kustomize "${K8S_DIR}/overlays/${env}" | head -50
    echo "..."
}

deploy() {
    local env=$1
    local namespace=$(get_namespace "$env")
    local deployment=$(get_deployment_name "$env")
    
    echo -e "${YELLOW}Deploying to $env environment...${NC}"
    
    # Validate first
    if ! kubectl kustomize "${K8S_DIR}/overlays/${env}" > /dev/null; then
        echo -e "${RED}Validation failed! Aborting deployment.${NC}"
        exit 1
    fi
    
    # Confirmation for production
    if [ "$env" = "production" ]; then
        echo -e "${RED}WARNING: You are about to deploy to PRODUCTION${NC}"
        read -p "Are you sure? (yes/no): " confirm
        if [ "$confirm" != "yes" ]; then
            echo "Deployment cancelled."
            exit 0
        fi
    fi
    
    # Apply manifests
    kubectl apply -k "${K8S_DIR}/overlays/${env}"
    
    # Wait for rollout
    echo ""
    echo -e "${YELLOW}Waiting for rollout to complete...${NC}"
    if kubectl rollout status deployment/${deployment} -n ${namespace} --timeout=5m; then
        echo -e "${GREEN}✓ Deployment successful!${NC}"
        
        # Show pod status
        echo ""
        echo -e "${YELLOW}Pod status:${NC}"
        kubectl get pods -n ${namespace} -l app.kubernetes.io/component=api
        
        # Show ingress
        echo ""
        echo -e "${YELLOW}Ingress:${NC}"
        kubectl get ingress -n ${namespace}
    else
        echo -e "${RED}✗ Deployment failed or timed out${NC}"
        echo ""
        echo "Recent events:"
        kubectl get events -n ${namespace} --sort-by='.lastTimestamp' | tail -20
        exit 1
    fi
}

status() {
    local env=$1
    local namespace=$(get_namespace "$env")
    local deployment=$(get_deployment_name "$env")
    
    echo -e "${YELLOW}Deployment Status for $env:${NC}"
    echo ""
    
    # Deployment status
    kubectl get deployment ${deployment} -n ${namespace}
    echo ""
    
    # Pod status
    echo -e "${YELLOW}Pods:${NC}"
    kubectl get pods -n ${namespace} -l app.kubernetes.io/component=api
    echo ""
    
    # HPA status
    echo -e "${YELLOW}Horizontal Pod Autoscaler:${NC}"
    kubectl get hpa -n ${namespace} 2>/dev/null || echo "No HPA configured"
    echo ""
    
    # Service status
    echo -e "${YELLOW}Service:${NC}"
    kubectl get svc -n ${namespace}
    echo ""
    
    # Ingress status
    echo -e "${YELLOW}Ingress:${NC}"
    kubectl get ingress -n ${namespace}
    echo ""
    
    # Recent events
    echo -e "${YELLOW}Recent Events:${NC}"
    kubectl get events -n ${namespace} --sort-by='.lastTimestamp' | tail -10
}

logs() {
    local env=$1
    local namespace=$(get_namespace "$env")
    
    echo -e "${YELLOW}Tailing logs for $env...${NC}"
    kubectl logs -n ${namespace} -l app.kubernetes.io/component=api -f --tail=100
}

rollback() {
    local env=$1
    local namespace=$(get_namespace "$env")
    local deployment=$(get_deployment_name "$env")
    
    echo -e "${YELLOW}Rolling back $env deployment...${NC}"
    
    # Show rollout history
    echo "Rollout history:"
    kubectl rollout history deployment/${deployment} -n ${namespace}
    echo ""
    
    # Confirmation
    read -p "Rollback to previous revision? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        echo "Rollback cancelled."
        exit 0
    fi
    
    # Perform rollback
    kubectl rollout undo deployment/${deployment} -n ${namespace}
    
    # Wait for rollback
    if kubectl rollout status deployment/${deployment} -n ${namespace} --timeout=5m; then
        echo -e "${GREEN}✓ Rollback successful!${NC}"
    else
        echo -e "${RED}✗ Rollback failed${NC}"
        exit 1
    fi
}

scale_deployment() {
    local env=$1
    local replicas=$2
    local namespace=$(get_namespace "$env")
    local deployment=$(get_deployment_name "$env")
    
    if [ -z "$replicas" ]; then
        echo -e "${RED}Error: Replica count required${NC}"
        usage
    fi
    
    echo -e "${YELLOW}Scaling $env deployment to $replicas replicas...${NC}"
    kubectl scale deployment/${deployment} -n ${namespace} --replicas=${replicas}
    
    echo -e "${GREEN}✓ Scaling initiated${NC}"
    kubectl get deployment ${deployment} -n ${namespace}
}

exec_pod() {
    local env=$1
    local namespace=$(get_namespace "$env")
    
    # Get first pod
    local pod=$(kubectl get pods -n ${namespace} -l app.kubernetes.io/component=api -o jsonpath='{.items[0].metadata.name}')
    
    if [ -z "$pod" ]; then
        echo -e "${RED}Error: No pods found${NC}"
        exit 1
    fi
    
    echo -e "${YELLOW}Opening shell in pod: $pod${NC}"
    kubectl exec -it -n ${namespace} ${pod} -- /bin/bash
}

migrate() {
    local env=$1
    local namespace=$(get_namespace "$env")
    
    echo -e "${YELLOW}Running database migrations for $env...${NC}"
    
    # Get first pod
    local pod=$(kubectl get pods -n ${namespace} -l app.kubernetes.io/component=api -o jsonpath='{.items[0].metadata.name}')
    
    if [ -z "$pod" ]; then
        echo -e "${RED}Error: No pods found${NC}"
        exit 1
    fi
    
    kubectl exec -n ${namespace} ${pod} -- alembic current
    kubectl exec -n ${namespace} ${pod} -- alembic upgrade head
    
    echo -e "${GREEN}✓ Migrations complete${NC}"
}

backup_db() {
    local env=$1
    local namespace=$(get_namespace "$env")
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_file="signal_harvester_${env}_${timestamp}.db"
    
    echo -e "${YELLOW}Creating database backup for $env...${NC}"
    
    # Get first pod
    local pod=$(kubectl get pods -n ${namespace} -l app.kubernetes.io/component=api -o jsonpath='{.items[0].metadata.name}')
    
    if [ -z "$pod" ]; then
        echo -e "${RED}Error: No pods found${NC}"
        exit 1
    fi
    
    # Create backup in pod
    kubectl exec -n ${namespace} ${pod} -- sqlite3 /data/signal_harvester.db ".backup '/data/backup.db'"
    
    # Copy to local
    kubectl cp ${namespace}/${pod}:/data/backup.db ./${backup_file}
    
    echo -e "${GREEN}✓ Backup saved to: ${backup_file}${NC}"
}

restore_db() {
    local env=$1
    local backup_file=$2
    local namespace=$(get_namespace "$env")
    
    if [ ! -f "$backup_file" ]; then
        echo -e "${RED}Error: Backup file not found: $backup_file${NC}"
        exit 1
    fi
    
    echo -e "${RED}WARNING: This will replace the current database!${NC}"
    read -p "Are you sure? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        echo "Restore cancelled."
        exit 0
    fi
    
    # Get first pod
    local pod=$(kubectl get pods -n ${namespace} -l app.kubernetes.io/component=api -o jsonpath='{.items[0].metadata.name}')
    
    if [ -z "$pod" ]; then
        echo -e "${RED}Error: No pods found${NC}"
        exit 1
    fi
    
    echo -e "${YELLOW}Restoring database for $env...${NC}"
    
    # Copy backup to pod
    kubectl cp ${backup_file} ${namespace}/${pod}:/data/restore.db
    
    # Restore
    kubectl exec -n ${namespace} ${pod} -- mv /data/signal_harvester.db /data/signal_harvester.db.old
    kubectl exec -n ${namespace} ${pod} -- mv /data/restore.db /data/signal_harvester.db
    
    echo -e "${GREEN}✓ Database restored${NC}"
    echo -e "${YELLOW}Note: You may need to restart pods for changes to take effect${NC}"
}

# Main script
if [ $# -lt 1 ]; then
    usage
fi

check_prerequisites

command=$1
shift

case "$command" in
    validate)
        validate "$@"
        ;;
    deploy)
        deploy "$@"
        ;;
    status)
        status "$@"
        ;;
    logs)
        logs "$@"
        ;;
    rollback)
        rollback "$@"
        ;;
    scale)
        scale_deployment "$@"
        ;;
    exec)
        exec_pod "$@"
        ;;
    migrate)
        migrate "$@"
        ;;
    backup)
        backup_db "$@"
        ;;
    restore)
        restore_db "$@"
        ;;
    *)
        echo -e "${RED}Unknown command: $command${NC}"
        usage
        ;;
esac
