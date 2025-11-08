from __future__ import annotations

import httpx

from signal_harvester.x_client import XClient


def test_x_client_retries_and_succeeds(monkeypatch):
    calls = {"count": 0}

    class FakeResponse:
        def __init__(self, status_code: int, json_data: dict | None = None, headers: dict | None = None):
            self.status_code = status_code
            self._json = json_data or {}
            self.headers = headers or {}

        def json(self):
            return self._json

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPError(f"status {self.status_code}")

    class FakeClient:
        def __init__(self, timeout: float | None = None):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url: str, params=None, headers=None):
            calls["count"] += 1
            if calls["count"] == 1:
                # First attempt: simulate 500 to trigger retry
                return FakeResponse(500)
            # Second attempt: success with minimal valid payload
            data = {
                "data": [
                    {
                        "id": "1",
                        "text": "hello",
                        "author_id": "u1",
                        "created_at": "2024-01-01T00:00:00Z",
                        "lang": "en",
                        "public_metrics": {"like_count": 1, "retweet_count": 0, "reply_count": 0, "quote_count": 0},
                    }
                ],
                "includes": {"users": [{"id": "u1", "username": "user1"}]},
                "meta": {"newest_id": "1"},
            }
            return FakeResponse(200, data)

    monkeypatch.setattr(httpx, "Client", FakeClient)

    client = XClient(bearer_token="token")
    rows, newest = client.search_recent("test query", since_id=None, max_results=10, lang="en")

    assert calls["count"] == 2
    assert newest == "1"
    assert len(rows) == 1
    assert rows[0]["author_username"] == "user1"
