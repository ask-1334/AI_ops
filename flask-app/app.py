
import flask
import logging
import random
import time
import requests
from pythonjsonlogger import jsonlogger

from prometheus_client import Counter, Histogram, generate_latest, REGISTRY
from prometheus_client.exposition import CONTENT_TYPE_LATEST 

from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.semconv.trace import SpanAttributes


SERVICE_NAME = "flask-app"
OTEL_EXPORTER_OTLP_ENDPOINT = "otel-collector:4317" 

logger = logging.getLogger(SERVICE_NAME)
logger.setLevel(logging.INFO)
logHandler = logging.StreamHandler()

class CustomJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super(CustomJsonFormatter, self).add_fields(log_record, record, message_dict)
        current_span = trace.get_current_span()
        if current_span != trace.INVALID_SPAN:
            log_record['trace_id'] = format(current_span.get_span_context().trace_id, 'x')
            log_record['span_id'] = format(current_span.get_span_context().span_id, 'x')
        else:
            log_record['trace_id'] = "00000000000000000000000000000000" 
            log_record['span_id'] = "0000000000000000" 

formatter = CustomJsonFormatter('%(asctime)s %(levelname)s %(name)s %(module)s %(funcName)s %(lineno)d %(message)s')
logHandler.setFormatter(formatter)
logger.addHandler(logHandler)
logger.propagate = False 

resource = Resource(attributes={
    "service.name": SERVICE_NAME
})

tracer_provider = TracerProvider(resource=resource)
otlp_span_exporter = OTLPSpanExporter(endpoint=OTEL_EXPORTER_OTLP_ENDPOINT, insecure=True)
tracer_provider.add_span_processor(BatchSpanProcessor(otlp_span_exporter))
trace.set_tracer_provider(tracer_provider)
tracer = trace.get_tracer(__name__)

metric_reader = PeriodicExportingMetricReader(
    OTLPMetricExporter(endpoint=OTEL_EXPORTER_OTLP_ENDPOINT, insecure=True)
)
meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
metrics.set_meter_provider(meter_provider)
meter = metrics.get_meter(__name__)

APP_REQUEST_LATENCY = Histogram(
    'app_request_latency_seconds',
    'Application Request Latency',
    ['method', 'endpoint']
)
APP_REQUEST_COUNT = Counter(
    'app_request_count_total',
    'Application Request Count',
    ['method', 'endpoint', 'http_status']
)


app = flask.Flask(__name__)

FlaskInstrumentor().instrument_app(app)
RequestsInstrumentor().instrument()

@app.route('/')
def home():
    with tracer.start_as_current_span("home-operation") as span:
        start_time = time.time()
        logger.info("Serving home page.")
        APP_REQUEST_COUNT.labels(method='GET', endpoint='/', http_status=200).inc()
        
        time.sleep(random.uniform(0.05, 0.15))
        duration = time.time() - start_time
        APP_REQUEST_LATENCY.labels(method='GET', endpoint='/').observe(duration)
        return "Hello from Flask AIOps App!"

@app.route('/api/data', methods=['GET', 'POST'])
def api_data():
    with tracer.start_as_current_span("data-operation", attributes={SpanAttributes.HTTP_METHOD: flask.request.method}) as span:
        start_time = time.time()
        logger.info(f"Received request for /api/data method: {flask.request.method}")

        
        with tracer.start_as_current_span("database-query") as db_span:
            db_span.set_attribute("db.system", "simulated_db")
            db_span.set_attribute("db.statement", "SELECT * FROM fake_table")
            time.sleep(random.uniform(0.05, 0.2)) 
            db_span.set_attribute("db.row_count", random.randint(1, 100))

        
        if flask.request.method == 'POST':
            if random.random() < 0.2: 
                logger.error("Simulated error in /api/data POST.")
                span.set_attribute(SpanAttributes.HTTP_STATUS_CODE, 500)
                span.record_exception(ValueError("Simulated internal server error"))
                APP_REQUEST_COUNT.labels(method='POST', endpoint='/api/data', http_status=500).inc()
                duration = time.time() - start_time
                APP_REQUEST_LATENCY.labels(method='POST', endpoint='/api/data').observe(duration)
                return flask.jsonify(error="Simulated internal server error"), 500
            else:
                logger.info("Processing POST data successfully.")
                APP_REQUEST_COUNT.labels(method='POST', endpoint='/api/data', http_status=201).inc()
                duration = time.time() - start_time
                APP_REQUEST_LATENCY.labels(method='POST', endpoint='/api/data').observe(duration)
                return flask.jsonify(message="Data processed successfully", data={"input": flask.request.json}), 201
        else: 
            
            try:
                
                response = requests.get("http://httpbin.org/delay/0.1", timeout=1)
                response.raise_for_status() 
                span.set_attribute("external.service.response_code", response.status_code)
            except requests.exceptions.RequestException as e:
                logger.error(f"Error calling external service: {e}")
                span.record_exception(e)
                span.set_attribute(SpanAttributes.HTTP_STATUS_CODE, 503) 
                APP_REQUEST_COUNT.labels(method='GET', endpoint='/api/data', http_status=503).inc()
                duration = time.time() - start_time
                APP_REQUEST_LATENCY.labels(method='GET', endpoint='/api/data').observe(duration)
                return flask.jsonify(error="Error calling external service"), 503

            logger.info("Serving data from /api/data GET.")
            APP_REQUEST_COUNT.labels(method='GET', endpoint='/api/data', http_status=200).inc()
            duration = time.time() - start_time
            APP_REQUEST_LATENCY.labels(method='GET', endpoint='/api/data').observe(duration)
            return flask.jsonify(data="Sample data", source="Flask App")

@app.route('/metrics')
def metrics_endpoint():
    """Expose Prometheus metrics."""
    return flask.Response(generate_latest(REGISTRY), mimetype=CONTENT_TYPE_LATEST)

if __name__ == '__main__':    
    logger.info("Starting Flask development server.")
    app.run(host='0.0.0.0', port=5000, debug=False) 
