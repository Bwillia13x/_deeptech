#!/usr/bin/env bash
#
# Deploy Signal Harvester Monitoring Stack (Docker Compose)
# 
# This script deploys Prometheus, Grafana, Alertmanager, and Node Exporter
# for comprehensive monitoring of the Signal Harvester API.
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    log_success "Docker is installed: $(docker --version)"
    
    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        log_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    log_success "Docker Compose is available"
    
    # Check if monitoring directory exists
    if [ ! -d "$PROJECT_ROOT/monitoring" ]; then
        log_error "Monitoring directory not found at $PROJECT_ROOT/monitoring"
        exit 1
    fi
    log_success "Monitoring configuration directory found"
}

# Create necessary directories
create_directories() {
    log_info "Creating necessary directories..."
    
    mkdir -p "$PROJECT_ROOT/monitoring/grafana/provisioning/dashboards"
    mkdir -p "$PROJECT_ROOT/monitoring/grafana/provisioning/datasources"
    mkdir -p "$PROJECT_ROOT/logs"
    
    log_success "Directories created"
}

# Build Signal Harvester image if needed
build_api_image() {
    log_info "Checking Signal Harvester API image..."
    
    if ! docker images | grep -q signal-harvester; then
        log_warning "Signal Harvester image not found. Building..."
        cd "$PROJECT_ROOT"
        docker build -t signal-harvester:latest .
        log_success "Signal Harvester image built"
    else
        log_success "Signal Harvester image exists"
    fi
}

# Deploy monitoring stack
deploy_monitoring() {
    log_info "Deploying monitoring stack..."
    
    cd "$PROJECT_ROOT"
    
    # Stop any existing monitoring services
    log_info "Stopping existing monitoring services..."
    docker-compose -f docker-compose.monitoring.yml down || true
    
    # Start monitoring stack
    log_info "Starting monitoring services..."
    docker-compose -f docker-compose.monitoring.yml up -d
    
    log_success "Monitoring stack deployed"
}

# Wait for services to be healthy
wait_for_services() {
    log_info "Waiting for services to become healthy..."
    
    local max_attempts=30
    local attempt=0
    
    # Wait for Prometheus
    log_info "Waiting for Prometheus..."
    while [ $attempt -lt $max_attempts ]; do
        if curl -sf http://localhost:9090/-/healthy > /dev/null 2>&1; then
            log_success "Prometheus is healthy"
            break
        fi
        attempt=$((attempt + 1))
        sleep 2
    done
    
    if [ $attempt -eq $max_attempts ]; then
        log_error "Prometheus failed to become healthy"
        return 1
    fi
    
    # Wait for Grafana
    log_info "Waiting for Grafana..."
    attempt=0
    while [ $attempt -lt $max_attempts ]; do
        if curl -sf http://localhost:3000/api/health > /dev/null 2>&1; then
            log_success "Grafana is healthy"
            break
        fi
        attempt=$((attempt + 1))
        sleep 2
    done
    
    if [ $attempt -eq $max_attempts ]; then
        log_error "Grafana failed to become healthy"
        return 1
    fi
    
    # Wait for Alertmanager
    log_info "Waiting for Alertmanager..."
    attempt=0
    while [ $attempt -lt $max_attempts ]; do
        if curl -sf http://localhost:9093/-/healthy > /dev/null 2>&1; then
            log_success "Alertmanager is healthy"
            break
        fi
        attempt=$((attempt + 1))
        sleep 2
    done
    
    if [ $attempt -eq $max_attempts ]; then
        log_error "Alertmanager failed to become healthy"
        return 1
    fi
    
    # Wait for Signal Harvester API
    log_info "Waiting for Signal Harvester API..."
    attempt=0
    while [ $attempt -lt $max_attempts ]; do
        if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
            log_success "Signal Harvester API is healthy"
            break
        fi
        attempt=$((attempt + 1))
        sleep 2
    done
    
    if [ $attempt -eq $max_attempts ]; then
        log_error "Signal Harvester API failed to become healthy"
        return 1
    fi
    
    log_success "All services are healthy"
}

# Display service URLs
display_urls() {
    echo ""
    log_success "==================================="
    log_success "Monitoring Stack Deployment Complete!"
    log_success "==================================="
    echo ""
    log_info "Service URLs:"
    echo ""
    echo "  📊 Grafana:        http://localhost:3000"
    echo "     Username:       admin"
    echo "     Password:       admin (change on first login)"
    echo ""
    echo "  📈 Prometheus:     http://localhost:9090"
    echo ""
    echo "  🔔 Alertmanager:   http://localhost:9093"
    echo ""
    echo "  🚀 API:            http://localhost:8000"
    echo "     Metrics:        http://localhost:8000/metrics/prometheus"
    echo "     Health:         http://localhost:8000/health"
    echo ""
    echo "  🖥️  Node Exporter:  http://localhost:9100/metrics"
    echo ""
    log_info "To view logs:"
    echo "  docker-compose -f docker-compose.monitoring.yml logs -f"
    echo ""
    log_info "To stop monitoring stack:"
    echo "  docker-compose -f docker-compose.monitoring.yml down"
    echo ""
    log_info "To view baseline load test results:"
    echo "  cat results/LOAD_TEST_BASELINE_REPORT.md"
    echo ""
}

# Main execution
main() {
    log_info "Starting Signal Harvester Monitoring Stack Deployment"
    echo ""
    
    check_prerequisites
    create_directories
    build_api_image
    deploy_monitoring
    wait_for_services
    display_urls
    
    log_success "Deployment completed successfully!"
}

# Run main function
main "$@"
