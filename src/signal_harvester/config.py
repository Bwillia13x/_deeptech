from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

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


class ArxivConfig(BaseModel):
    enabled: bool = True
    max_results: int = 50
    categories: List[str] = Field(default_factory=lambda: [
        "cs.LG", "cs.AI", "cs.RO", "cs.CV", "physics.optics", "quant-ph", "cs.CL", "cs.NE"
    ])
    query_terms: List[str] = Field(default_factory=lambda: ["novel", "breakthrough", "state-of-the-art"])


class GitHubConfig(BaseModel):
    enabled: bool = True
    max_results: int = 50
    token: Optional[str] = None
    topics: List[str] = Field(default_factory=lambda: [
        "quantum-computing", "photonics", "robotics", "foundation-models", "machine-learning"
    ])
    orgs: List[str] = Field(default_factory=lambda: ["openai", "google-research", "openrobotics"])
    min_stars: int = 10


class FacebookConfig(BaseModel):
    enabled: bool = True
    access_token: Optional[str] = None
    pages: List[str] = Field(default_factory=list)
    groups: List[str] = Field(default_factory=list)
    search_queries: List[str] = Field(default_factory=lambda: [
        "artificial intelligence research",
        "quantum computing",
        "robotics",
        "machine learning breakthrough"
    ])
    max_results: int = 50


class LinkedInConfig(BaseModel):
    enabled: bool = True
    access_token: Optional[str] = None
    organizations: List[str] = Field(default_factory=list)
    max_results: int = 50


class SourcesConfig(BaseModel):
    x: Dict[str, Any] = Field(default_factory=dict)
    arxiv: ArxivConfig = ArxivConfig()
    github: GitHubConfig = GitHubConfig()
    facebook: FacebookConfig = FacebookConfig()
    linkedin: LinkedInConfig = LinkedInConfig()


class DiscoveryWeights(BaseModel):
    novelty: float = 0.35
    emergence: float = 0.30
    obscurity: float = 0.20
    cross_source: float = 0.10
    expert_signal: float = 0.05
    recency_half_life_hours: float = 336.0  # 14 days


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
    discovery: DiscoveryWeights = DiscoveryWeights()


class IdentityResolutionConfig(BaseModel):
    enabled: bool = True
    similarity_threshold: float = 0.75
    auto_link_threshold: float = 0.90
    manual_review_threshold: float = 0.70
    reject_threshold: float = 0.70
    weights: Dict[str, float] = Field(
        default_factory=lambda: {
            "name": 0.40,
            "affiliation": 0.25,
            "domain": 0.15,
            "co_mention": 0.10,
            "content": 0.10
        }
    )
    common_names: List[str] = Field(default_factory=list)
    institution_blacklist: List[str] = Field(default_factory=list)


class TopicEvolutionConfig(BaseModel):
    enabled: bool = True
    similarity_threshold: float = 0.75
    merge_threshold: float = 0.85
    split_threshold: float = 0.80
    cluster_quality_threshold: float = 0.60
    update_frequency_hours: float = 24.0
    emergence_window_days: int = 30
    prediction_window_days: int = 14


class BackupScheduleConfig(BaseModel):
    """Backup schedule configuration."""
    daily_enabled: bool = True
    daily_time: str = "02:00"
    weekly_enabled: bool = True
    weekly_day: str = "sunday"
    weekly_time: str = "03:00"
    monthly_enabled: bool = True
    monthly_day: int = 1
    monthly_time: str = "04:00"


class BackupRetentionConfig(BaseModel):
    """Backup retention policy configuration."""
    daily_keep: int = 7
    weekly_keep: int = 4
    monthly_keep: int = 12


class BackupS3Config(BaseModel):
    """S3 backup configuration."""
    enabled: bool = False
    bucket: str = ""
    prefix: str = "signal-harvester/backups"
    region: str = "us-east-1"
    upload_after_backup: bool = True


class BackupGCSConfig(BaseModel):
    """Google Cloud Storage backup configuration."""
    enabled: bool = False
    bucket: str = ""
    prefix: str = "signal-harvester/backups"


class BackupAzureConfig(BaseModel):
    """Azure Blob Storage backup configuration."""
    enabled: bool = False
    container: str = ""
    account_name: str = ""
    prefix: str = "signal-harvester/backups"


class BackupVerificationConfig(BaseModel):
    """Backup verification configuration."""
    verify_after_backup: bool = True
    verify_before_restore: bool = True


class BackupConfig(BaseModel):
    """Backup and recovery configuration."""
    enabled: bool = True
    backup_dir: str = "backups"
    compression: str = "gzip"
    retention_days: int = 90
    schedule: BackupScheduleConfig = Field(default_factory=BackupScheduleConfig)
    retention: BackupRetentionConfig = Field(default_factory=BackupRetentionConfig)
    s3: BackupS3Config = Field(default_factory=BackupS3Config)
    gcs: BackupGCSConfig = Field(default_factory=BackupGCSConfig)
    azure: BackupAzureConfig = Field(default_factory=BackupAzureConfig)
    verification: BackupVerificationConfig = Field(default_factory=BackupVerificationConfig)


class ConnectionPoolConfig(BaseModel):
    """Database connection pool configuration."""
    enabled: bool = True
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: float = 30.0
    pool_recycle: int = 3600  # Recycle connections after 1 hour


class AppConfig(BaseModel):
    database_path: str = "data/harvest.db"
    fetch: FetchConfig = FetchConfig()
    llm: LLMConfig = LLMConfig()
    weights: Weights = Weights()
    sources: SourcesConfig = SourcesConfig()
    identity_resolution: IdentityResolutionConfig = IdentityResolutionConfig()
    topic_evolution: TopicEvolutionConfig = TopicEvolutionConfig()
    connection_pool: ConnectionPoolConfig = ConnectionPoolConfig()
    backup: BackupConfig = Field(default_factory=BackupConfig)
    facebook_access_token: Optional[str] = None
    linkedin_access_token: Optional[str] = None


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


def get_config(path: Optional[str] = None) -> Settings:
    """Get validated settings (convenience alias for legacy callers)."""
    return load_settings(path)
    
