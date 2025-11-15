"""Enhanced pipeline with discovery support for Phase 1 Deep Tech upgrade."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from .config import Settings
from .db import (
    get_cursor,
    list_artifacts_for_analysis,
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
from .pipeline_identity import run_identity_resolution_pipeline
from .scoring import compute_salience
from .slack import (
    format_discovery_slack_message,
    format_slack_message,
    get_slack_webhook,
    post_to_slack,
)
from .topic_evolution import run_topic_evolution_pipeline
from .x_client import XClient

log = get_logger(__name__)


def fetch_once(settings: Settings) -> Dict[str, int]:
    """Fetch tweets from X (original functionality)."""
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


async def fetch_artifacts(settings: Settings) -> Dict[str, Any]:
    """Fetch artifacts from all configured sources."""
    app = settings.app
    stats: dict[str, Any] = {"sources": {}}

    sources_cfg = getattr(app, "sources", None)
    if not sources_cfg:
        log.warning("No sources configuration found; skipping artifact fetch")
        return stats

    if isinstance(sources_cfg, dict):
        explicit_fields = {k for k, v in sources_cfg.items() if v is not None}
    else:
        explicit_fields = set(getattr(sources_cfg, "model_fields_set", set()))

    # Import discovery clients lazily to avoid circular deps
    from . import arxiv_client, github_client, hackernews_client, reddit_client

    def _get_source_attr(cfg: Any, name: str) -> Any:
        if isinstance(cfg, dict):
            return cfg.get(name)
        return getattr(cfg, name, None)

    def _is_enabled(name: str, cfg: Any, default_enabled: bool = True) -> bool:
        if cfg is None:
            return False

        enabled_value: Any
        enabled_explicit = False
        if isinstance(cfg, dict):
            enabled_value = cfg.get("enabled")
            enabled_explicit = "enabled" in cfg
        else:
            enabled_value = getattr(cfg, "enabled", None)
            enabled_explicit = "enabled" in getattr(cfg, "model_fields_set", set())

        if enabled_explicit:
            return bool(enabled_value)

        if explicit_fields and name not in explicit_fields:
            return False

        if enabled_value is not None:
            return bool(enabled_value)

        return default_enabled

    # Fetch from arXiv if enabled
    arxiv_cfg = _get_source_attr(sources_cfg, "arxiv")
    if _is_enabled("arxiv", arxiv_cfg, default_enabled=True):
        try:
            papers = await arxiv_client.fetch_arxiv_papers(settings.model_dump())
            inserted = 0

            for paper in papers:
                from .db import upsert_artifact
                artifact_id = upsert_artifact(
                    db_path=app.database_path,
                    artifact_type="preprint",
                    source="arxiv",
                    source_id=paper["source_id"],
                    title=paper["title"],
                    text=paper["text"],
                    url=paper["url"],
                    published_at=paper["published_at"],
                    raw_json=json.dumps(paper)
                )
                if artifact_id:
                    inserted += 1

            stats["sources"]["arxiv"] = {"inserted": inserted, "seen": len(papers)}
            log.info("Fetch arXiv: seen=%d inserted=%d", len(papers), inserted)
        except Exception as e:
            log.error("Error fetching from arXiv: %s", e)
            stats["sources"]["arxiv"] = {"error": str(e)}

    # Fetch from GitHub if enabled
    github_cfg = _get_source_attr(sources_cfg, "github")
    if _is_enabled("github", github_cfg, default_enabled=True):
        try:
            repo_artifacts, release_artifacts = await github_client.fetch_github_artifacts(settings.model_dump())

            repos_inserted = 0
            for repo in repo_artifacts:
                from .db import upsert_artifact
                artifact_id = upsert_artifact(
                    db_path=app.database_path,
                    artifact_type="repo",
                    source="github",
                    source_id=repo["source_id"],
                    title=repo["title"],
                    text=repo["text"],
                    url=repo["url"],
                    published_at=repo["published_at"],
                    raw_json=json.dumps(repo)
                )
                if artifact_id:
                    repos_inserted += 1

            releases_inserted = 0
            for release in release_artifacts:
                from .db import upsert_artifact
                artifact_id = upsert_artifact(
                    db_path=app.database_path,
                    artifact_type="release",
                    source="github",
                    source_id=release["source_id"],
                    title=release["title"],
                    text=release["text"],
                    url=release["url"],
                    published_at=release["published_at"],
                    raw_json=json.dumps(release)
                )
                if artifact_id:
                    releases_inserted += 1

            stats["sources"]["github"] = {
                "repos": repos_inserted,
                "releases": releases_inserted
            }
            log.info("Fetch GitHub: repos=%d releases=%d", repos_inserted, releases_inserted)
        except Exception as e:
            log.error("Error fetching from GitHub: %s", e)
            stats["sources"]["github"] = {"error": str(e)}

    # Fetch from Facebook if enabled
    facebook_cfg = _get_source_attr(sources_cfg, "facebook")
    if _is_enabled("facebook", facebook_cfg, default_enabled=True):
        try:
            from . import facebook_client
            
            facebook_artifacts = await facebook_client.fetch_facebook_artifacts(settings)
            
            facebook_inserted = 0
            for artifact in facebook_artifacts:
                from .db import upsert_artifact
                artifact_id = upsert_artifact(
                    db_path=app.database_path,
                    artifact_type=artifact["type"],
                    source="facebook",
                    source_id=artifact["source_id"],
                    title=artifact["title"],
                    text=artifact["text"],
                    url=artifact["url"],
                    published_at=artifact["published_at"],
                    raw_json=json.dumps(artifact)
                )
                if artifact_id:
                    facebook_inserted += 1
            
            stats["sources"]["facebook"] = {"inserted": facebook_inserted, "seen": len(facebook_artifacts)}
            log.info("Fetch Facebook: seen=%d inserted=%d", len(facebook_artifacts), facebook_inserted)
        except Exception as e:
            log.error("Error fetching from Facebook: %s", e)
            stats["sources"]["facebook"] = {"error": str(e)}

    # Fetch from LinkedIn if enabled
    linkedin_cfg = _get_source_attr(sources_cfg, "linkedin")
    if _is_enabled("linkedin", linkedin_cfg, default_enabled=True):
        try:
            from . import linkedin_client
           
            linkedin_artifacts = await linkedin_client.fetch_linkedin_artifacts(settings)
           
            linkedin_inserted = 0
            for artifact in linkedin_artifacts:
                from .db import upsert_artifact
                artifact_id = upsert_artifact(
                    db_path=app.database_path,
                    artifact_type=artifact["type"],
                    source="linkedin",
                    source_id=artifact["source_id"],
                    title=artifact["title"],
                    text=artifact["text"],
                    url=artifact["url"],
                    published_at=artifact["published_at"],
                    raw_json=json.dumps(artifact)
                )
                if artifact_id:
                    linkedin_inserted += 1
           
            stats["sources"]["linkedin"] = {"inserted": linkedin_inserted, "seen": len(linkedin_artifacts)}
            log.info("Fetch LinkedIn: seen=%d inserted=%d", len(linkedin_artifacts), linkedin_inserted)
        except Exception as e:
            log.error("Error fetching from LinkedIn: %s", e)
            stats["sources"]["linkedin"] = {"error": str(e)}

    # Fetch from Reddit if enabled
    reddit_cfg = _get_source_attr(sources_cfg, "reddit")
    if _is_enabled("reddit", reddit_cfg, default_enabled=False):
        try:
            reddit_artifacts = await reddit_client.fetch_reddit_artifacts(settings)

            reddit_inserted = 0
            for artifact in reddit_artifacts:
                from .db import upsert_artifact
                artifact_id = upsert_artifact(
                    db_path=app.database_path,
                    artifact_type=artifact["type"],
                    source="reddit",
                    source_id=artifact["source_id"],
                    title=artifact.get("title"),
                    text=artifact.get("text"),
                    url=artifact.get("url"),
                    published_at=artifact.get("published_at"),
                    raw_json=artifact.get("raw_json"),
                )
                if artifact_id:
                    reddit_inserted += 1

            stats["sources"]["reddit"] = {
                "inserted": reddit_inserted,
                "seen": len(reddit_artifacts),
            }
            log.info("Fetch Reddit: seen=%d inserted=%d", len(reddit_artifacts), reddit_inserted)
        except Exception as e:
            log.error("Error fetching from Reddit: %s", e)
            stats["sources"]["reddit"] = {"error": str(e)}

    # Fetch from Hacker News if enabled
    hn_cfg = _get_source_attr(sources_cfg, "hacker_news")
    if _is_enabled("hacker_news", hn_cfg, default_enabled=False):
        try:
            hn_artifacts = await hackernews_client.fetch_hackernews_artifacts(settings)

            hn_inserted = 0
            for artifact in hn_artifacts:
                from .db import upsert_artifact
                artifact_id = upsert_artifact(
                    db_path=app.database_path,
                    artifact_type=artifact["type"],
                    source="hackernews",
                    source_id=artifact["source_id"],
                    title=artifact.get("title"),
                    text=artifact.get("text"),
                    url=artifact.get("url"),
                    published_at=artifact.get("published_at"),
                    raw_json=artifact.get("raw_json"),
                )
                if artifact_id:
                    hn_inserted += 1

            stats["sources"]["hacker_news"] = {
                "inserted": hn_inserted,
                "seen": len(hn_artifacts),
            }
            log.info("Fetch Hacker News: seen=%d inserted=%d", len(hn_artifacts), hn_inserted)
        except Exception as e:
            log.error("Error fetching from Hacker News: %s", e)
            stats["sources"]["hacker_news"] = {"error": str(e)}

    return stats


def analyze_unanalyzed(settings: Settings, limit: int = 200) -> int:
    """Analyze tweets using original signal analysis."""
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
        log.info("Analyzed %d tweets", count)
    return count


async def analyze_artifacts(settings: Settings, limit: int = 200) -> int:
    """Analyze artifacts using research classifier."""
    app = settings.app
    
    # Import research classifier
    from .llm_client import get_async_llm_client
    from .research_classifier import ResearchClassifier
    
    llm_client = get_async_llm_client(app.llm.provider, app.llm.model, app.llm.temperature)
    classifier = ResearchClassifier(llm_client)
    
    # Get artifacts that need analysis (no topics yet)
    artifacts = list_artifacts_for_analysis(app.database_path, limit)
    log.info("Found %d artifacts to analyze", len(artifacts))
    
    analyzed = 0
    for artifact in artifacts:
        try:
            classification = await classifier.classify(artifact)
            if classification:
                # Store classification results
                from .cli.discovery_commands import store_classification_results
                store_classification_results(
                    db_path=app.database_path,
                    artifact_id=artifact['id'],
                    classification=classification
                )
                analyzed += 1
                log.debug("Analyzed artifact %s: %s", artifact.get("source_id"), classification["category"])
        except Exception as e:
            log.error("Error analyzing artifact %s: %s", artifact.get("source_id"), e)
            continue
    
    log.info("Analyzed %d artifacts", analyzed)
    return analyzed


def score_unscored(settings: Settings, limit: int = 500) -> int:
    """Score tweets using original salience scoring."""
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
        log.info("Scored %d tweets", count)
    return count


def notify_high_salience(
    settings: Settings,
    threshold: float = 80.0,
    limit: int = 10,
    hours: Optional[int] = None
) -> int:
    """Send notifications for high salience tweets."""
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


async def notify_high_discovery(
    settings: Settings,
    threshold: float = 85.0,
    limit: int = 10
) -> int:
    """Send notifications for high discovery score artifacts."""
    from .db import list_top_discoveries
    
    app = settings.app
    webhook = get_slack_webhook()
    if not webhook:
        log.warning("SLACK_WEBHOOK_URL not set; skipping notifications")
        return 0
    
    discoveries = list_top_discoveries(app.database_path, min_score=threshold, limit=limit)
    sent = 0
    for discovery in discoveries:
        payload = format_discovery_slack_message(discovery)
        if post_to_slack(webhook, payload["text"]):
            sent += 1
    if sent:
        log.info("Sent %d discovery notifications", sent)
    return sent


def run_pipeline(
    settings: Settings,
    notify_threshold: Optional[float] = None,
    notify_limit: int = 10,
    notify_hours: Optional[int] = None,
    discovery_mode: bool = True
) -> Dict[str, int]:
    """Run the complete pipeline with optional discovery mode."""
    stats = {"fetched": 0, "analyzed": 0, "scored": 0, "notified": 0}
    
    # Fetch tweets (original functionality)
    f = fetch_once(settings)
    stats["fetched"] = f.get("inserted", 0)
    
    # Fetch artifacts if discovery mode is enabled
    if discovery_mode:
        async def fetch_and_log():  # type: ignore[no-untyped-def]
            artifact_stats = await fetch_artifacts(settings)
            log.info("Artifact fetch stats: %s", artifact_stats)
            return artifact_stats
        
        # Run async fetch
        import asyncio
        artifact_stats = asyncio.run(fetch_and_log())
        stats["artifact_fetch"] = artifact_stats
    
    # Analyze tweets
    a = analyze_unanalyzed(settings, limit=300)
    stats["analyzed"] = a
    
    # Analyze artifacts if discovery mode
    if discovery_mode:
        async def analyze_and_log():  # type: ignore[no-untyped-def]
            analyzed = await analyze_artifacts(settings, limit=300)
            return analyzed
        
        artifact_analyzed = asyncio.run(analyze_and_log())
        stats["artifact_analyzed"] = artifact_analyzed
    
    # Run identity resolution if enabled (Phase 2)
    if discovery_mode and settings.app.identity_resolution.enabled:
        async def resolve_and_log():  # type: ignore[no-untyped-def]
            identity_stats = await run_identity_resolution_pipeline(
                db_path=settings.app.database_path,
                settings=settings,
                batch_size=100
            )
            return identity_stats
        
        identity_results = asyncio.run(resolve_and_log())
        stats["identity_resolution"] = identity_results
        log.info("Identity resolution completed: %s", identity_results)
    
    # Run topic evolution analysis if enabled (Phase 2)
    if discovery_mode and settings.app.topic_evolution.enabled:
        async def evolve_and_log():  # type: ignore[no-untyped-def]
            evolution_stats = await run_topic_evolution_pipeline(
                db_path=settings.app.database_path,
                settings=settings,
                window_days=30
            )
            return evolution_stats
        
        evolution_results = asyncio.run(evolve_and_log())
        stats["topic_evolution"] = evolution_results
        log.info("Topic evolution analysis completed: %s", evolution_results)
    
    # Score tweets
    s = score_unscored(settings, limit=600)
    stats["scored"] = s
    
    # Score artifacts if discovery mode
    if discovery_mode:
        from .discovery_scoring import run_discovery_scoring

        async def score_and_log() -> int:
            return await run_discovery_scoring(
                settings.app.database_path,
                settings.model_dump(),
                limit=600,
            )

        discovery_scored = asyncio.run(score_and_log())
        stats["discovery_scored"] = discovery_scored
    
    # Send notifications
    if notify_threshold is not None:
        n = notify_high_salience(settings, threshold=float(notify_threshold), limit=notify_limit, hours=notify_hours)
        stats["notified"] = n
        
        # Also send discovery notifications if in discovery mode
        if discovery_mode:
            async def notify_and_log():
                d_notified = await notify_high_discovery(settings, threshold=85.0, limit=notify_limit)
                return d_notified
            
            discovery_notified = asyncio.run(notify_and_log())
            stats["discovery_notified"] = discovery_notified
    
    return stats
