from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx

from .logger import get_logger

log = get_logger(__name__)


class XClient:
    """
    Minimal client for X (Twitter) v2 recent search API.
    """

    def __init__(self, bearer_token: str | None = None, base_url: str = "https://api.twitter.com"):
        self.bearer_token = (
            bearer_token or
            os.getenv("X_BEARER_TOKEN") or
            os.getenv("TWITTER_BEARER_TOKEN") or
            os.getenv("BEARER_TOKEN")
        )
        self.base_url = base_url.rstrip("/")
        if not self.bearer_token:
            log.warning("X/Twitter bearer token not set (X_BEARER_TOKEN); fetch will be a no-op")

    def search_recent(
        self,
        query: str,
        since_id: str | None = None,
        max_results: int = 50,
        lang: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """
        Returns (rows, newest_id)
        """
        if not self.bearer_token:
            return [], None

        q = (query or "").strip()
        if lang and " lang:" not in q and "lang:" not in q:
            q = f"({q}) lang:{lang}"
        max_results = max(10, min(100, int(max_results or 50)))

        params: dict[str, str | int] = {
            "query": q,
            "max_results": max_results,
            "tweet.fields": "id,text,author_id,created_at,lang,public_metrics",
            "expansions": "author_id",
            "user.fields": "id,username,name,verified,public_metrics",
        }
        if since_id:
            params["since_id"] = since_id

        headers = {"Authorization": f"Bearer {self.bearer_token}"}
        url = f"{self.base_url}/2/tweets/search/recent"
        data: dict[str, Any] = {}
        max_attempts = 3
        backoff = 1.0
        for attempt in range(1, max_attempts + 1):
            try:
                with httpx.Client(timeout=15.0) as client:
                    resp = client.get(url, params=params, headers=headers)
                # Handle rate limit and transient server errors with retry
                if resp.status_code == 429:
                    log.warning(
                        "X API rate limited (429). Attempt %d/%d.", attempt, max_attempts
                    )
                    if attempt < max_attempts:
                        # Respect Retry-After if present
                        retry_after = resp.headers.get("retry-after")
                        sleep_s = float(retry_after) if retry_after and retry_after.isdigit() else backoff
                        time.sleep(sleep_s)
                        backoff *= 2
                        continue
                    return [], None
                if 500 <= resp.status_code < 600:
                    log.warning(
                        "X API server error %d. Attempt %d/%d.", resp.status_code, attempt, max_attempts
                    )
                    if attempt < max_attempts:
                        time.sleep(backoff)
                        backoff *= 2
                        continue
                    return [], None
                resp.raise_for_status()
                data = resp.json()
                break
            except httpx.HTTPError as e:
                log.error("X search HTTP error (attempt %d/%d): %s", attempt, max_attempts, e)
                if attempt < max_attempts:
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                return [], None
            except json.JSONDecodeError as e:
                log.error("X API returned invalid JSON: %s", e)
                return [], None
            except Exception as e:
                log.error("X search unexpected error: %s", e)
                return [], None

        users = {u["id"]: u for u in (data.get("includes", {}).get("users") or [])}
        rows: list[dict[str, Any]] = []
        for t in data.get("data") or []:
            pm = t.get("public_metrics") or {}
            author = users.get(t.get("author_id")) or {}
            row = {
                "tweet_id": t.get("id"),
                "text": t.get("text"),
                "author_id": t.get("author_id"),
                "author_username": author.get("username"),
                "created_at": t.get("created_at"),
                "lang": t.get("lang"),
                "like_count": int(pm.get("like_count") or 0),
                "retweet_count": int(pm.get("retweet_count") or 0),
                "reply_count": int(pm.get("reply_count") or 0),
                "quote_count": int(pm.get("quote_count") or 0),
                "raw_json": json.dumps(t, ensure_ascii=False),
            }
            rows.append(row)

        newest = (data.get("meta") or {}).get("newest_id")
        return rows, newest
