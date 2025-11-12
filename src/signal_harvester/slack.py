from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx

from .logger import get_logger
from .utils import truncate

log = get_logger(__name__)


def get_slack_webhook() -> Optional[str]:
    return os.getenv("SLACK_WEBHOOK_URL") or os.getenv("SLACK_WEBHOOK")


def format_slack_message(item: Dict[str, object]) -> str:
    sal = item.get("salience")
    cat = item.get("category") or "other"
    sent = item.get("sentiment") or "neutral"
    urg = item.get("urgency") or 0
    user = item.get("author_username") or item.get("author_id") or "unknown"
    tid = item.get("tweet_id")
    url = f"https://x.com/i/web/status/{tid}"
    if user and user != "unknown":
        url = f"https://x.com/{user}/status/{tid}"
    metrics = (
        f"❤ {item.get('like_count', 0)}  "
        f"🔁 {item.get('retweet_count', 0)}  "
        f"💬 {item.get('reply_count', 0)}  "
        f"❝ {item.get('quote_count', 0)}"
    )
    text = truncate(str(item.get("text") or ""), 260)
    return f"[{sal}] {cat} | {sent} | urgency={urg} — @{user}\n{text}\n{metrics}\n{url}"


def format_discovery_slack_message(discovery: Dict[str, Any]) -> Dict[str, Any]:
    """Format a discovery artifact for Slack notification payload."""
    title = discovery.get("title", "Untitled")
    source = discovery.get("source", "unknown")
    score = discovery.get("discovery_score", 0)
    url = discovery.get("url", "")

    text = f"🚀 *Discovery Score: {score:.1f}* | Source: {source.upper()}\n"
    text += f"*{title}*\n"
    text += f"{url}"

    return {
        "text": text,
        "unfurl_links": True,
        "unfurl_media": True,
    }


def post_to_slack(webhook_url: str, text: str, timeout: float = 8.0) -> bool:
    try:
        resp = httpx.post(webhook_url, json={"text": text}, timeout=timeout)
        if resp.status_code >= 200 and resp.status_code < 300:
            return True
        log.error("Slack webhook failed: %s %s", resp.status_code, resp.text)
        return False
    except Exception as e:
        log.error("Slack webhook error: %s", e)
        return False
