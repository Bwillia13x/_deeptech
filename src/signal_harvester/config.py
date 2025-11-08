from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import BaseModel, Field, ValidationError

from .logger import get_logger

log = get_logger(__name__)


class QueryConfig(BaseModel):
    name: str
    query: str
    enabled: bool = True


class FetchConfig(BaseModel):
    max_results: int = 50
    lang: Optional[str] = None


class LLMConfig(BaseModel):
    provider: str = "dummy"  # dummy, openai, anthropic, ollama
    model: Optional[str] = None
    temperature: float = 0.0


class Weights(BaseModel):
    likes: float = 1.0
    retweets: float = 3.0
    replies: float = 2.0
    quotes: float = 2.5
    urgency: float = 4.0

    sentiment_positive: float = 1.0
    sentiment_negative: float = 1.2
    sentiment_neutral: float = 0.9

    category_boosts: dict[str, float] = Field(
        default_factory=lambda: {
            "outage": 2.0,
            "security": 1.8,
            "bug": 1.3,
            "question": 1.0,
            "praise": 0.8,
            "other": 1.0,
        }
    )

    recency_half_life_hours: float = 24.0
    base: float = 1.0
    cap: float = 100.0


class AppConfig(BaseModel):
    database_path: str = "data/harvest.db"
    fetch: FetchConfig = FetchConfig()
    llm: LLMConfig = LLMConfig()
    weights: Weights = Weights()


class Settings(BaseModel):
    app: AppConfig = AppConfig()
    queries: List[QueryConfig] = Field(default_factory=list)


def _find_settings_path(explicit: Optional[str]) -> Optional[Path]:
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    env = os.getenv("HARVEST_CONFIG")
    if env:
        candidates.append(Path(env))
    candidates.extend([
        Path("settings.yaml"),
        Path("settings.yml"),
        Path("config/settings.yaml"),
        Path("examples/settings.example.yaml")
    ])
    for p in candidates:
        if p and p.exists() and p.is_file():
            return p
    return None


def load_settings(path: Optional[str] = None) -> Settings:
    p = _find_settings_path(path)
    if not p:
        log.warning("No settings file found; using defaults")
        s = Settings()
        # Small env overrides
        db_env = os.getenv("HARVEST_DB_PATH")
        if db_env:
            s.app.database_path = db_env
        lang_env = os.getenv("HARVEST_FETCH_LANG")
        if lang_env:
            s.app.fetch.lang = lang_env
        return s

    with open(p, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    try:
        s = Settings(**raw)
    except ValidationError as e:
        log.error("Settings validation failed: %s", e)
        raise
    # Env overrides
    if db_path := os.getenv("HARVEST_DB_PATH"):
        s.app.database_path = db_path
    if fetch_lang := os.getenv("HARVEST_FETCH_LANG"):
        s.app.fetch.lang = fetch_lang
    if llm_provider := os.getenv("HARVEST_LLM_PROVIDER"):
        s.app.llm.provider = llm_provider
    if llm_model := os.getenv("HARVEST_LLM_MODEL"):
        s.app.llm.model = llm_model
    return s
    