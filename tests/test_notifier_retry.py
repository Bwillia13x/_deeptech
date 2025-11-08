from __future__ import annotations

import httpx

from signal_harvester.notifier import SlackNotifier


def test_slack_notifier_retries_and_succeeds(monkeypatch):
    calls = {"count": 0}

    class FakeResponse:
        def __init__(self, status_code: int):
            self.status_code = status_code
            self.headers = {}

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPError(f"status {self.status_code}")

    class FakeClient:
        def __init__(self, timeout: float | None = None):
            self.timeout = timeout

        def post(self, url: str, json=None):
            calls["count"] += 1
            if calls["count"] == 1:
                return FakeResponse(500)
            return FakeResponse(200)

    monkeypatch.setattr(httpx, "Client", FakeClient)

    n = SlackNotifier(webhook_url="https://example.com/webhook")
    ok = n.send_text("hello world")

    assert ok is True
    assert calls["count"] == 2
