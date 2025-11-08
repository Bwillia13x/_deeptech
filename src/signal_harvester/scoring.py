from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Mapping

from .llm_client import Analysis
from .logger import get_logger

log = get_logger(__name__)


def _parse_iso8601_z(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        # Expecting 2024-01-01T12:34:56Z or ...+00:00
        if s.endswith("Z"):
            return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        # Fallback: fromisoformat handles +00:00
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def compute_salience(row: Mapping[str, Any], analysis: Analysis, weights: Mapping[str, Any]) -> float:
    # Weights
    wl = float(weights.get("likes", 1.0))
    wr = float(weights.get("retweets", 3.0))
    wrepl = float(weights.get("replies", 2.0))
    wq = float(weights.get("quotes", 2.5))
    wurg = float(weights.get("urgency", 4.0))
    base = float(weights.get("base", 1.0))
    cap = float(weights.get("cap", 100.0))
    half_life = float(weights.get("recency_half_life_hours", 24.0))
    cat_boosts: dict[str, float] = dict(weights.get("category_boosts", {}))

    sent_mult_map = {
        "positive": float(weights.get("sentiment_positive", 1.0)),
        "neutral": float(weights.get("sentiment_neutral", 0.9)),
        "negative": float(weights.get("sentiment_negative", 1.2)),
    }

    likes = int(row.get("like_count") or 0)
    rts = int(row.get("retweet_count") or 0)
    repl = int(row.get("reply_count") or 0)
    quotes = int(row.get("quote_count") or 0)

    raw_metrics = likes * wl + rts * wr + repl * wrepl + quotes * wq
    metrics_score = 10.0 * math.log1p(max(0.0, raw_metrics))  # 0.. ~60

    urgency_score = max(0, int(analysis.urgency or 0)) * wurg
    category_boost = float(cat_boosts.get((analysis.category or "other").lower(), 1.0))
    sentiment_mult = float(sent_mult_map.get((analysis.sentiment or "neutral").lower(), 1.0))

    # Recency attenuation
    created_at = _parse_iso8601_z(row.get("created_at"))
    if created_at:
        age_hours = max(0.0, (datetime.now(tz=timezone.utc) - created_at).total_seconds() / 3600.0)
        recency_factor = 0.5 ** (age_hours / max(0.1, half_life))
    else:
        recency_factor = 1.0

    score = (base + metrics_score + urgency_score) * category_boost * sentiment_mult * recency_factor
    score = max(0.0, min(cap, score))
    return float(round(score, 3))
