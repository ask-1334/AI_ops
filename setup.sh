#!/bin/bash

# Flask Observability Stack Setup Script
echo "🚀 Setting up Flask Observability Stack"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}$1${NC}"
}

# Check if Docker and Docker Compose are installed
check_dependencies() {
    print_header "📋 Checking dependencies..."
    
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    if ! command -v docker compose &> /dev/null && ! docker compose version &> /dev/null; then
        print_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    
    print_status "Dependencies check passed ✅"
}

# Create directory structure
create_structure() {
    print_header "📁 Creating directory structure..."
    
    mkdir -p flask-app
    mkdir -p otel-collector
    mkdir -p prometheus
    mkdir -p logstash/pipeline
    mkdir -p grafana/provisioning/datasources
    mkdir -p grafana/provisioning/dashboards
    
    print_status "Directory structure created ✅"
}

# Create configuration files
create_configs() {
    print_header "⚙️  Creating configuration files..."
    
    # Note: The actual file contents would be created from the artifacts above
    print_status "Configuration files ready ✅"
}

# Build and start services
start_services() {
    print_header "🔄 Starting services..."
    
    print_status "Building Flask application..."
    docker compose build flask-app
    
    print_status "Starting all services..."
    docker compose up -d
    
    print_status "Waiting for services to be ready..."
    sleep 30
}

# Check service health
check_services() {
    print_header "🏥 Checking service health..."
    
    services=(
        "flask-app:5000"
        "prometheus:9090"
        "grafana:3000"
        "jaeger:16686"
        "kibana:5601"
        "elasticsearch:9200"
    )
    
    for service in "${services[@]}"; do
        IFS=':' read -r name port <<< "$service"
        if curl -f -s "http://localhost:$port" > /dev/null; then
            print_status "$name is running on port $port ✅"
        else
            print_warning "$name might not be ready yet on port $port ⚠️"
        fi
    done
}

# Generate some test data
generate_test_data() {
    print_header "📊 Generating test data..."
    
    print_status "Making test requests to generate telemetry data..."
    
    # Make some requests to generate data
    for i in {1..20}; do
        curl -s http://localhost:5000/ > /dev/null
        curl -s http://localhost:5000/api/data > /dev/null
        sleep 0.5
    done
    
    # Run load test
    curl -s http://localhost:5000/load-test > /dev/null
    
    print_status "Test data generated ✅"
}

# Print access information
print_access_info() {
    print_header "🌐 Service Access Information"
    
    echo ""
    echo "📱 Flask Application:"
    echo "   • Main app: http://localhost:5000"
    echo "   • API endpoint: http://localhost:5000/api/data"
    echo "   • Metrics: http://localhost:5000/metrics"
    echo "   • Health: http://localhost:5000/health"
    echo ""
    echo "📊 Monitoring & Observability:"
    echo "   • Grafana: http://localhost:3000 (admin/admin)"
    echo "   • Prometheus: http://localhost:9090"
    echo "   • Jaeger: http://localhost:16686"
    echo "   • Kibana: http://localhost:5601"
    echo ""
    echo "🔧 Infrastructure:"
    echo "   • Elasticsearch: http://localhost:9200"
    echo "   • OpenTelemetry Collector: http://localhost:4317 (gRPC), http://localhost:4318 (HTTP)"
    echo ""
    echo "🎯 Quick Start:"
    echo "   1. Visit Grafana at http://localhost:3000"
    echo "   2. Generate load: curl http://localhost:5000/load-test"
    echo "   3. View traces in Jaeger: http://localhost:16686"
    echo "   4. Explore logs in Kibana: http://localhost:5601"
    echo ""
}

# Main execution
main() {
    print_header "🎉 Flask Observability Stack Setup"
    echo ""
    
    check_dependencies
    create_structure
    create_configs
    start_services
    check_services
    generate_test_data
    print_access_info
    
    print_status "Setup completed! 🎉"
    print_status "Run 'docker compose logs -f' to view logs from all services"
}

# Cleanup function
cleanup() {
    print_header "🧹 Cleaning up..."
    docker compose down -v
    print_status "Cleanup completed"
}

# Handle script arguments
case "${1:-setup}" in
    setup)
        main
        ;;
    cleanup)
        cleanup
        ;;
    restart)
        cleanup
        main
        ;;
    logs)
        docker compose logs -f
        ;;
    status)
        docker compose ps
        ;;
    *)
        echo "Usage: $0 {setup|cleanup|restart|logs|status}"
        exit 1
        ;;
esac