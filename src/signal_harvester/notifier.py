from __future__ import annotations

import os
import time
from typing import Dict, Iterable, Optional

import httpx

from .logger import get_logger

log = get_logger(__name__)


def tweet_url(author_username: Optional[str], tweet_id: str) -> str:
    if author_username:
        return f"https://x.com/{author_username}/status/{tweet_id}"
    return f"https://x.com/i/web/status/{tweet_id}"


class SlackNotifier:
    def __init__(self, webhook_url: Optional[str] = None, timeout: float = 10.0) -> None:
        self.webhook_url = webhook_url or os.getenv("SLACK_WEBHOOK_URL")
        self._client = httpx.Client(timeout=timeout)

    @property
    def enabled(self) -> bool:
        return bool(self.webhook_url)

    def send_text(self, text: str) -> bool:
        if not self.enabled:
            log.warning("Slack webhook not configured; skipping notification")
            return False
        if self.webhook_url is None:
            log.error("Slack webhook URL is None")
            return False
        max_attempts = 3
        backoff = 1.0
        for attempt in range(1, max_attempts + 1):
            try:
                resp = self._client.post(self.webhook_url, json={"text": text})
                if resp.status_code == 429 or 500 <= resp.status_code < 600:
                    if attempt < max_attempts:
                        time.sleep(backoff)
                        backoff *= 2
                        continue
                resp.raise_for_status()
                return True
            except Exception as e:
                log.error("Failed to send Slack notification (attempt %d): %s", attempt, e)
                if attempt < max_attempts:
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                return False
        return False  # Should never reach here, but satisfies mypy

    @staticmethod
    def format_message(row: Dict[str, object]) -> str:
        salience = row.get("salience", 0)
        author = row.get("author_username") or "unknown"
        created_at = row.get("created_at") or ""
        category = row.get("category") or "other"
        sentiment = row.get("sentiment") or "neutral"
        text = str(row.get("text") or "").strip()
        url = tweet_url(str(row.get("author_username") or ""), str(row.get("tweet_id")))
        counts = f"❤ {row.get('like_count', 0)} 🔁 {row.get('retweet_count', 0)} 💬 {row.get('reply_count', 0)}"
        return (
            f"New high-salience post ({salience:.1f}) [{category}/{sentiment}] by @{author} at {created_at}\n"
            f"{text}\n{counts}\n{url}"
        )

    def notify_rows(self, rows: Iterable[Dict[str, object]]) -> int:
        from .db import mark_notified
        
        sent = 0
        for row in rows:
            ok = self.send_text(self.format_message(row))
            if ok:
                mark_notified("data/harvest.db", str(row["tweet_id"]))
                sent += 1
        return sent


def notify_high_salience(threshold: float = 75.0, limit: int = 20) -> int:
    from .db import list_for_notification
    
    rows = list_for_notification("data/harvest.db", threshold=threshold, limit=limit)
    if not rows:
        return 0
    notifier = SlackNotifier()
    return notifier.notify_rows(rows)
