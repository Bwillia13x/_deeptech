from __future__ import annotations

from fastapi.testclient import TestClient

from signal_harvester.api import create_app


def test_prometheus_metrics_endpoint_returns_text_plain(monkeypatch):
    # Ensure app can boot without special config
    app = create_app()
    client = TestClient(app)
    r = client.get("/metrics/prometheus")
    assert r.status_code == 200
    ctype = r.headers.get("content-type", "")
    # prometheus_client CONTENT_TYPE_LATEST: 'text/plain; version=0.0.4; charset=utf-8'
    assert "text/plain" in ctype
    assert "charset=utf-8" in ctype or "charset" in ctype
    assert r.text.strip() != ""
