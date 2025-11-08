from __future__ import annotations

from fastapi.testclient import TestClient

from signal_harvester.api import create_app


def test_security_headers_present():
    app = create_app()
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    # Security headers from middleware
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("x-frame-options") == "DENY"
    assert r.headers.get("referrer-policy") == "no-referrer"
    # HSTS may be set regardless of HTTP
    assert "max-age" in (r.headers.get("strict-transport-security") or "")


def test_cors_preflight_allows_origin():
    app = create_app()
    client = TestClient(app)
    r = client.options(
        "/health",
        headers={
            "Origin": "http://example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.status_code in (200, 204)
    # CORS should allow all origins by default or echo origin
    allow_origin = r.headers.get("access-control-allow-origin")
    assert allow_origin in ("*", "http://example.com")
