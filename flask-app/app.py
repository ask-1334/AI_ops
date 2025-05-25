import logging
import random
import time
from flask import Flask, jsonify, request
import requests
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

# OpenTelemetry imports
from opentelemetry import trace, metrics
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.trace.status import Status, StatusCode
import os

# Configure logging with trace correlation
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [trace_id=%(otelTraceID)s span_id=%(otelSpanID)s] - %(message)s'
)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)

# Prometheus metrics
REQUEST_COUNT = Counter('flask_requests_total', 'Total Flask requests', ['method', 'endpoint', 'status'])
REQUEST_DURATION = Histogram('flask_request_duration_seconds', 'Flask request duration', ['method', 'endpoint'])

# OpenTelemetry setup
def setup_telemetry():
    # Resource identifies your service
    resource = Resource.create({
        "service.name": os.getenv("OTEL_SERVICE_NAME", "flask-app"),
        "service.version": os.getenv("OTEL_SERVICE_VERSION", "1.0.0"),
    })
    
    # Trace setup
    trace.set_tracer_provider(TracerProvider(resource=resource))
    tracer_provider = trace.get_tracer_provider()
    
    otlp_exporter = OTLPSpanExporter(
        endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"),
        insecure=True
    )
    
    span_processor = BatchSpanProcessor(otlp_exporter)
    tracer_provider.add_span_processor(span_processor)
    
    # Metrics setup
    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(
            endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"),
            insecure=True
        ),
        export_interval_millis=5000
    )
    
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[metric_reader]))
    
    # Auto-instrument Flask and requests
    FlaskInstrumentor().instrument_app(app)
    RequestsInstrumentor().instrument()

# Custom logging filter to add trace context
class TraceContextFilter(logging.Filter):
    def filter(self, record):
        span = trace.get_current_span()
        if span != trace.INVALID_SPAN:
            span_context = span.get_span_context()
            record.otelTraceID = format(span_context.trace_id, '032x')
            record.otelSpanID = format(span_context.span_id, '016x')
        else:
            record.otelTraceID = '0'
            record.otelSpanID = '0'
        return True

# Add filter to logger
logger.addFilter(TraceContextFilter())

# Setup telemetry
setup_telemetry()
tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__)

# OpenTelemetry metrics
otel_request_counter = meter.create_counter(
    name="http_requests_total",
    description="Total number of HTTP requests",
    unit="1"
)

otel_request_duration = meter.create_histogram(
    name="http_request_duration",
    description="HTTP request duration",
    unit="ms"
)

@app.before_request
def before_request():
    request.start_time = time.time()

@app.after_request
def after_request(response):
    duration = time.time() - request.start_time
    
    # Prometheus metrics
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=request.endpoint or 'unknown',
        status=response.status_code
    ).inc()
    
    REQUEST_DURATION.labels(
        method=request.method,
        endpoint=request.endpoint or 'unknown'
    ).observe(duration)
    
    # OpenTelemetry metrics
    otel_request_counter.add(
        1,
        {
            "method": request.method,
            "endpoint": request.endpoint or 'unknown',
            "status_code": str(response.status_code)
        }
    )
    
    otel_request_duration.record(
        duration * 1000,  # Convert to milliseconds
        {
            "method": request.method,
            "endpoint": request.endpoint or 'unknown'
        }
    )
    
    return response

@app.route('/')
def home():
    with tracer.start_as_current_span("home-operation") as span:
        logger.info("Processing home page request")
        
        span.set_attribute("custom.operation", "home")
        span.set_attribute("user.ip", request.remote_addr)
        
        # Simulate some processing
        processing_time = random.uniform(0.01, 0.1)
        time.sleep(processing_time)
        
        span.set_attribute("processing.duration_ms", processing_time * 1000)
        
        logger.info(f"Home page processed in {processing_time:.3f}s")
        
        return jsonify({
            "message": "Welcome to the Observability Demo!",
            "service": "flask-app",
            "version": "1.0.0",
            "endpoints": ["/", "/api/data", "/metrics", "/health"]
        })

@app.route('/api/data')
def get_data():
    with tracer.start_as_current_span("data-operation") as span:
        logger.info("Processing data API request")
        
        span.set_attribute("custom.operation", "data")
        
        # Simulate potential errors (10% chance)
        if random.random() < 0.1:
            span.set_status(Status(StatusCode.ERROR, "Simulated error"))
            span.record_exception(Exception("Random error occurred"))
            logger.error("Simulated error in data processing")
            return jsonify({"error": "Internal server error"}), 500
        
        # Simulate database query
        db_result = simulate_database_query()
        
        # Simulate API processing time
        processing_time = random.uniform(0.05, 0.3)
        time.sleep(processing_time)
        
        span.set_attribute("processing.duration_ms", processing_time * 1000)
        span.set_attribute("database.query_time_ms", db_result["query_time_ms"])
        span.set_attribute("data.records_returned", db_result["record_count"])
        
        logger.info(f"Data API processed in {processing_time:.3f}s, returned {db_result['record_count']} records")
        
        return jsonify({
            "data": [
                {"id": i, "name": f"Item {i}", "value": random.randint(1, 100)}
                for i in range(db_result["record_count"])
            ],
            "metadata": {
                "processing_time_ms": processing_time * 1000,
                "database_query_time_ms": db_result["query_time_ms"],
                "record_count": db_result["record_count"]
            }
        })

def simulate_database_query():
    """Simulate a database query with its own span"""
    with tracer.start_as_current_span("database-query") as span:
        logger.info("Executing database query")
        
        span.set_attribute("db.operation", "SELECT")
        span.set_attribute("db.table", "items")
        
        # Simulate query time
        query_time = random.uniform(0.01, 0.15)
        time.sleep(query_time)
        
        record_count = random.randint(5, 50)
        
        span.set_attribute("db.query_time_ms", query_time * 1000)
        span.set_attribute("db.records_returned", record_count)
        
        # Simulate occasional slow queries (5% chance)
        if random.random() < 0.05:
            additional_time = random.uniform(0.5, 1.0)
            time.sleep(additional_time)
            query_time += additional_time
            span.add_event("slow_query_detected", {"additional_time_ms": additional_time * 1000})
            logger.warning(f"Slow database query detected: {query_time:.3f}s")
        
        logger.info(f"Database query completed in {query_time:.3f}s, returned {record_count} records")
        
        return {
            "query_time_ms": query_time * 1000,
            "record_count": record_count
        }

@app.route('/health')
def health():
    with tracer.start_as_current_span("health-check") as span:
        span.set_attribute("health.status", "healthy")
        logger.info("Health check requested")
        return jsonify({"status": "healthy", "service": "flask-app"})

@app.route('/metrics')
def metrics():
    """Prometheus metrics endpoint"""
    return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}

@app.route('/load-test')
def load_test():
    """Generate some load for testing"""
    with tracer.start_as_current_span("load-test") as span:
        logger.info("Starting load test")
        
        results = []
        for i in range(10):
            # Make internal API calls
            try:
                response = requests.get('http://localhost:5000/api/data', timeout=5)
                results.append({
                    "request": i + 1,
                    "status": response.status_code,
                    "response_time_ms": response.elapsed.total_seconds() * 1000
                })
            except Exception as e:
                logger.error(f"Load test request {i+1} failed: {str(e)}")
                results.append({
                    "request": i + 1,
                    "status": "error",
                    "error": str(e)
                })
        
        logger.info(f"Load test completed with {len(results)} requests")
        return jsonify({"results": results})

if __name__ == '__main__':
    logger.info("Starting Flask application with observability")
    app.run(host='0.0.0.0', port=5000, debug=True)