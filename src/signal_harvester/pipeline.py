from __future__ import annotations

import json
from typing import Dict, Optional

from .config import Settings
from .db import (
    get_cursor,
    list_for_notification,
    list_unanalyzed,
    list_unscored,
    mark_notified,
    set_cursor,
    update_analysis,
    update_salience,
    upsert_tweet,
)
from .llm_client import Analysis, get_llm_client
from .logger import get_logger
from .scoring import compute_salience
from .slack import format_slack_message, get_slack_webhook, post_to_slack
from .x_client import XClient

log = get_logger(__name__)


def fetch_once(settings: Settings) -> Dict[str, int]:
    app = settings.app
    client = XClient()
    total_inserted = 0
    total_seen = 0
    per_query: Dict[str, int] = {}
    for q in settings.queries:
        if not q.enabled:
            continue
        since = get_cursor(app.database_path, q.name)
        tweets, newest = client.search_recent(
            query=q.query,
            since_id=since,
            max_results=app.fetch.max_results,
            lang=app.fetch.lang,
        )
        seen = len(tweets)
        inserted = 0
        for t in tweets:
            if upsert_tweet(app.database_path, t, query_name=q.name):
                inserted += 1
        if newest:
            set_cursor(app.database_path, q.name, newest)
        per_query[q.name] = inserted
        total_inserted += inserted
        total_seen += seen
        log.info("Fetch '%s': seen=%d inserted=%d", q.name, seen, inserted)
    return {"seen": total_seen, "inserted": total_inserted, **{f"q:{k}": v for k, v in per_query.items()}}


def analyze_unanalyzed(settings: Settings, limit: int = 200) -> int:
    app = settings.app
    analyzer = get_llm_client(app.llm.provider, app.llm.model, app.llm.temperature)
    rows = list_unanalyzed(app.database_path, limit=limit)
    count = 0
    for r in rows:
        analysis = analyzer.analyze_text(str(r.get("text") or ""))
        tags_json = json.dumps(analysis.tags or [], ensure_ascii=False)
        update_analysis(
            app.database_path,
            tweet_id=str(r["tweet_id"]),
            category=analysis.category,
            sentiment=analysis.sentiment,
            urgency=int(analysis.urgency or 0),
            tags_json=tags_json,
            reasoning=analysis.reasoning or "",
        )
        count += 1
    if count:
        log.info("Analyzed %d items", count)
    return count


def score_unscored(settings: Settings, limit: int = 500) -> int:
    app = settings.app
    rows = list_unscored(app.database_path, limit=limit)
    count = 0
    for r in rows:
        try:
            tags: list[str] = []
            try:
                if r.get("tags"):
                    tags = json.loads(r["tags"]) or []
            except Exception:
                tags = []
            analysis = Analysis(
                category=r.get("category") or "other",
                sentiment=r.get("sentiment") or "neutral",
                urgency=int(r.get("urgency") or 0),
                tags=tags,
                reasoning=r.get("reasoning") or "",
            )
            sal = compute_salience(r, analysis, settings.app.weights.model_dump())
        except Exception as e:
            log.error("Salience compute failed for %s: %s", r.get("tweet_id"), e)
            continue
        update_salience(app.database_path, tweet_id=str(r["tweet_id"]), salience=float(sal))
        count += 1
    if count:
        log.info("Scored %d items", count)
    return count


def notify_high_salience(
    settings: Settings,
    threshold: float = 80.0,
    limit: int = 10,
    hours: Optional[int] = None
) -> int:
    app = settings.app
    webhook = get_slack_webhook()
    if not webhook:
        log.warning("SLACK_WEBHOOK_URL not set; skipping notifications")
        return 0
    rows = list_for_notification(app.database_path, threshold=threshold, limit=limit, hours=hours)
    sent = 0
    for r in rows:
        msg = format_slack_message(r)
        if post_to_slack(webhook, msg):
            mark_notified(app.database_path, tweet_id=str(r["tweet_id"]))
            sent += 1
    if sent:
        log.info("Sent %d Slack notifications", sent)
    return sent


def run_pipeline(
    settings: Settings,
    notify_threshold: Optional[float] = None,
    notify_limit: int = 10,
    notify_hours: Optional[int] = None,
) -> Dict[str, int]:
    stats = {"fetched": 0, "analyzed": 0, "scored": 0, "notified": 0}
    f = fetch_once(settings)
    stats["fetched"] = f.get("inserted", 0)
    a = analyze_unanalyzed(settings, limit=300)
    s = score_unscored(settings, limit=600)
    stats["analyzed"] = a
    stats["scored"] = s
    if notify_threshold is not None:
        n = notify_high_salience(settings, threshold=float(notify_threshold), limit=notify_limit, hours=notify_hours)
        stats["notified"] = n
    return stats
