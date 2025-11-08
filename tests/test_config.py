from __future__ import annotations

import os
from pathlib import Path

from signal_harvester.config import load_settings


def test_load_settings_default(tmp_path):
    # Copy example config to temp
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    (cfg_dir / "settings.yaml").write_text(
        """
app:
  database_path: "var/app.db"
  fetch:
    max_results: 10
    lang: "en"
  llm:
    provider: "dummy"
    model: "test-model"
    temperature: 0.2
  weights:
    likes: 1.0
    retweets: 3.0
    replies: 2.0
    quotes: 2.5
    urgency: 4.0
    sentiment_positive: 1.0
    sentiment_negative: 1.2
    sentiment_neutral: 0.9
    category_boosts:
      outage: 2.0
      security: 1.8
      bug: 1.3
      question: 1.0
      praise: 0.8
      other: 1.0
    recency_half_life_hours: 24.0
    base: 1.0
    cap: 100.0
queries: []
        """,
        encoding="utf-8",
    )
    s = load_settings(str(cfg_dir / "settings.yaml"))
    assert s.app.database_path.endswith("var/app.db")
    assert s.app.fetch.max_results == 10
    assert s.app.llm.model == "test-model"
    assert s.app.llm.provider == "dummy"
