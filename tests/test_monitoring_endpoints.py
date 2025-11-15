from fastapi.testclient import TestClient

from signal_harvester.api import create_app


def test_health_and_probe_endpoints_work():
    """Ensure the health endpoints return structured readiness responses."""
    client = TestClient(create_app())
    for path in ["/health", "/health/live", "/health/ready", "/health/startup"]:
        r = client.get(path)
        assert r.status_code == 200
        payload = r.json()
        assert payload["status"] in {"healthy", "degraded", "unhealthy"}
        assert "components" in payload
        assert "timestamp" in payload


def test_prometheus_metrics_endpoint_exposes_instrumentation():
    client = TestClient(create_app())
    r = client.get("/metrics/prometheus")
    assert r.status_code == 200
    assert "http_requests_total" in r.text
    assert r.headers["content-type"].startswith("text/plain")
