"""Phase One Deep Tech Discovery CLI commands."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Any

import typer

from .. import arxiv_client, facebook_client, github_client
from ..config import load_settings
from ..db import (
    init_db,
    link_artifact_topic,
    list_artifacts_for_analysis,
    list_top_discoveries,
    run_migrations,
    update_discovery_scores,
    upsert_artifact,
    upsert_artifact_classification,
    upsert_entity,
    upsert_topic,
)
from ..discovery_scoring import run_discovery_scoring
from ..identity_resolution import run_identity_resolution
from ..llm_client import get_async_llm_client
from ..research_classifier import ResearchClassifier
from ..slack import format_discovery_slack_message, get_slack_webhook, post_to_slack
from .core import app, console, get_config_path


def store_classification_results(db_path: str, artifact_id: int, classification: dict[str, Any]) -> None:
    """Store classification results including entities and topics."""
    from ..logger import get_logger

    log = get_logger(__name__)

    try:
        # Persist full classification payload
        try:
            upsert_artifact_classification(db_path, artifact_id, classification)
        except Exception as e:
            log.warning("Error storing artifact classification for %s: %s", artifact_id, e)

        entity_ids = []

        # Process entities
        entities = classification.get("entities", {})

        # Process people
        for person in entities.get("people", []):
            try:
                entity_id = upsert_entity(db_path, "person", person)
                entity_ids.append(entity_id)
            except Exception as e:
                log.warning(f"Error storing person entity '{person}': {e}")

        # Process labs
        for lab in entities.get("labs", []):
            try:
                entity_id = upsert_entity(db_path, "lab", lab)
                entity_ids.append(entity_id)
            except Exception as e:
                log.warning(f"Error storing lab entity '{lab}': {e}")

        # Process orgs
        for org in entities.get("orgs", []):
            try:
                entity_id = upsert_entity(db_path, "org", org)
                entity_ids.append(entity_id)
            except Exception as e:
                log.warning(f"Error storing org entity '{org}': {e}")

        # Update artifact with entity IDs if we have any
        if entity_ids:
            import json
            import sqlite3

            from ..utils import utc_now_iso

            conn = None
            try:
                conn = sqlite3.connect(db_path)
                with conn:
                    conn.execute(
                        "UPDATE artifacts SET author_entity_ids = ?, updated_at = ? WHERE id = ?",
                        (json.dumps(entity_ids), utc_now_iso(), artifact_id),
                    )
            except Exception as e:
                log.warning(f"Error updating artifact with entity IDs: {e}")
            finally:
                if conn is not None:
                    conn.close()

        # Process topics
        for topic_path in classification.get("topics", []):
            try:
                # Extract topic name from path (last component)
                topic_name = topic_path.split("/")[-1] if "/" in topic_path else topic_path
                topic_id = upsert_topic(db_path, topic_name, taxonomy_path=topic_path)
                link_artifact_topic(db_path, artifact_id, topic_id, confidence=0.8)
            except Exception as e:
                log.warning(f"Error storing topic '{topic_path}': {e}")

        log.debug(f"Stored classification results for artifact {artifact_id}")

    except Exception as e:
        log.error(f"Error storing classification results: {e}")


@app.command("fetch")
def fetch_discovery(
    ctx: typer.Context,
    sources: str = typer.Option(
        "x,arxiv,github,facebook,linkedin",
        "--sources",
        "-s",
        help="Comma-separated list of sources to fetch",
    ),
    max_results: int = typer.Option(50, "--max-results", "-n", help="Max results per source"),
) -> None:
    """Fetch artifacts from multiple sources (X, arXiv, GitHub, Facebook, LinkedIn)."""
    config_path = get_config_path(ctx)
    s = load_settings(config_path)

    source_list = [src.strip() for src in sources.split(",")]
    stats: dict[str, Any] = {"sources": {}}

    async def fetch_from_source(source: str):
        try:
            if source == "x":
                # Use existing X fetch
                from ..pipeline import fetch_once

                x_stats = fetch_once(s)
                stats["sources"]["x"] = x_stats
                console.print(f"✓ Fetched from X: {x_stats}")

            elif source == "arxiv":
                # Fetch arXiv papers
                papers = await arxiv_client.fetch_arxiv_papers(s.model_dump())
                inserted = 0

                for paper in papers:
                    artifact_id = upsert_artifact(
                        db_path=s.app.database_path,
                        artifact_type="preprint",
                        source="arxiv",
                        source_id=paper["source_id"],
                        title=paper["title"],
                        text=paper["text"],
                        url=paper["url"],
                        published_at=paper["published_at"],
                        raw_json=json.dumps(paper),
                    )
                    if artifact_id:
                        inserted += 1

                stats["sources"]["arxiv"] = {"inserted": inserted, "seen": len(papers)}
                console.print(f"✓ Fetched from arXiv: {inserted} papers inserted")

            elif source == "github":
                # Fetch GitHub repos and releases
                repo_artifacts, release_artifacts = await github_client.fetch_github_artifacts(s.model_dump())

                repos_inserted = 0
                for repo in repo_artifacts:
                    artifact_id = upsert_artifact(
                        db_path=s.app.database_path,
                        artifact_type="repo",
                        source="github",
                        source_id=repo["source_id"],
                        title=repo["title"],
                        text=repo["text"],
                        url=repo["url"],
                        published_at=repo["published_at"],
                        raw_json=json.dumps(repo),
                    )
                    if artifact_id:
                        repos_inserted += 1

                releases_inserted = 0
                for release in release_artifacts:
                    artifact_id = upsert_artifact(
                        db_path=s.app.database_path,
                        artifact_type="release",
                        source="github",
                        source_id=release["source_id"],
                        title=release["title"],
                        text=release["text"],
                        url=release["url"],
                        published_at=release["published_at"],
                        raw_json=json.dumps(release),
                    )
                    if artifact_id:
                        releases_inserted += 1

                stats["sources"]["github"] = {"repos": repos_inserted, "releases": releases_inserted}
                console.print(f"✓ Fetched from GitHub: {repos_inserted} repos, {releases_inserted} releases")

            elif source == "facebook":
                # Fetch Facebook posts from pages and groups
                fb_artifacts = await facebook_client.fetch_facebook_artifacts(s)

                inserted = 0
                for artifact in fb_artifacts:
                    artifact_id = upsert_artifact(
                        db_path=s.app.database_path,
                        artifact_type="post",
                        source="facebook",
                        source_id=artifact["source_id"],
                        title=artifact["title"],
                        text=artifact["text"],
                        url=artifact["url"],
                        published_at=artifact["published_at"],
                        raw_json=artifact["raw_json"],
                    )
                    if artifact_id:
                        inserted += 1

                stats["sources"]["facebook"] = {"inserted": inserted, "seen": len(fb_artifacts)}
                console.print(f"✓ Fetched from Facebook: {inserted} posts inserted")

            else:
                console.print(f"✗ Unknown source: {source}")

        except Exception as e:
            console.print(f"✗ Error fetching from {source}: {e}")
            stats["sources"][source] = {"error": str(e)}

    # Run all fetches concurrently
    async def fetch_all():
        await asyncio.gather(*[fetch_from_source(source) for source in source_list])

    asyncio.run(fetch_all())
    console.print(f"[green]Fetch complete: {json.dumps(stats, indent=2)}[/green]")


@app.command("seed-discovery-data")
def seed_discovery_data(
    ctx: typer.Context,
    force: bool = typer.Option(False, "--force", "-f", help="Re-populate even when data already exists"),
) -> None:
    """Seed discovery tables with curated artifacts/topics for UI testing."""

    config_path = get_config_path(ctx)
    s = load_settings(config_path)
    init_db(s.app.database_path)
    run_migrations(s.app.database_path)

    existing = list_top_discoveries(s.app.database_path, min_score=0.0, limit=1)
    if existing and not force:
        console.print("[yellow]Discovery tables already contain data; use --force to reseed[/yellow]")
        return

    topic_definitions = [
        {
            "name": "Quantum Networking",
            "taxonomy_path": "physics/quantum/networking",
            "description": "Low-latency entanglement routers for satellite meshes.",
        },
        {
            "name": "Autonomous Soft Robotics",
            "taxonomy_path": "robotics/soft/mobile",
            "description": "Compliant, tactile limbs for delicate manipulation.",
        },
        {
            "name": "Biomimetic Energy Harvesting",
            "taxonomy_path": "energy/biomimicry/harvesting",
            "description": "Photosynthesis-inspired membranes for power.",
        },
    ]

    topic_ids: dict[str, int] = {}
    for topic in topic_definitions:
        topic_id = upsert_topic(
            s.app.database_path,
            topic["name"],
            taxonomy_path=topic["taxonomy_path"],
            description=topic["description"],
        )
        topic_ids[topic["name"]] = topic_id

    artifact_definitions = [
        {
            "title": "Quantum packet switches for entangled networks",
            "text": "Demonstrates low-error switching of Bell pairs across 10 nodes.",
            "source": "arxiv",
            "source_id": "arxiv-qnet-001",
            "artifact_type": "preprint",
            "url": "https://arxiv.org/abs/2025.00123",
            "topic": "Quantum Networking",
            "novelty": 0.92,
            "emergence": 0.88,
            "obscurity": 0.74,
            "score": 0.91,
        },
        {
            "title": "Soft robotic grippers that feel tissue stiffness",
            "text": "Capacitive skin gives soft limbs surgical precision.",
            "source": "github",
            "source_id": "gh-soft-robots-001",
            "artifact_type": "repo",
            "url": "https://github.com/deeptech/soft-grip",
            "topic": "Autonomous Soft Robotics",
            "novelty": 0.85,
            "emergence": 0.81,
            "obscurity": 0.67,
            "score": 0.83,
        },
        {
            "title": "Photosynthetic micro-membranes for energy capture",
            "text": "Bio-inspired membranes mimic algae to generate electricity.",
            "source": "semantic",
            "source_id": "semantic-bio-123",
            "artifact_type": "preprint",
            "url": "https://semantic.scholar.org/paper/virtual",
            "topic": "Biomimetic Energy Harvesting",
            "novelty": 0.88,
            "emergence": 0.75,
            "obscurity": 0.69,
            "score": 0.80,
        },
    ]

    inserted = 0
    now = datetime.now(tz=timezone.utc)
    for idx, artifact in enumerate(artifact_definitions):
        published_at = (now - timedelta(days=idx * 2)).isoformat()
        artifact_id = upsert_artifact(
            db_path=s.app.database_path,
            artifact_type=str(artifact["artifact_type"]),
            source=str(artifact["source"]),
            source_id=str(artifact["source_id"]),
            title=str(artifact.get("title")),
            text=str(artifact.get("text")),
            url=str(artifact.get("url")),
            published_at=published_at,
        )

        topic_id = topic_ids.get(str(artifact["topic"]))
        if topic_id:
            link_artifact_topic(s.app.database_path, artifact_id, topic_id, confidence=0.9)

        update_discovery_scores(
            s.app.database_path,
            artifact_id,
            float(artifact["novelty"]),
            float(artifact["emergence"]),
            float(artifact["obscurity"]),
            float(artifact["score"]),
        )
        inserted += 1

    console.print(f"[green]Seeded {inserted} discovery artifacts across {len(topic_ids)} topics[/green]")


@app.command("backtest")
def backtest_discoveries(
    ctx: typer.Context,
    days: int = typer.Option(3, "--days", "-d", help="How many days of history to replay"),
    min_score: float = typer.Option(80.0, "--min-score", "-s", help="Minimum discovery score to include"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max discoveries per window"),
    experiment_name: str | None = typer.Option(None, "--experiment", "-e", help="Create experiment with this name"),
    compare_baseline: int | None = typer.Option(None, "--compare", "-c", help="Compare with baseline experiment ID"),
    show_metrics: bool = typer.Option(False, "--metrics/--no-metrics", help="Show precision/recall metrics"),
) -> None:
    """
    Replay discovery windows over the past N days for validation.
    
    Optionally creates an experiment run with precision/recall metrics if ground truth labels exist.
    """

    config_path = get_config_path(ctx)
    s = load_settings(config_path)
    init_db(s.app.database_path)
    run_migrations(s.app.database_path)
    
    from ..experiment import (
        ExperimentConfig,
        calculate_metrics,
        compare_experiments,
        create_experiment,
        create_experiment_run,
        get_labeled_artifacts,
    )

    console.print("[blue]Running discovery backtest[/blue]")
    
    # Get labeled artifacts for ground truth
    labeled_artifacts = {}
    if show_metrics or experiment_name:
        labels = get_labeled_artifacts(s.app.database_path)
        labeled_artifacts = {label["artifactId"]: label["label"] for label in labels}
        console.print(f"Found {len(labeled_artifacts)} labeled artifacts for validation")
    
    summary_lines = []
    total_tp = 0
    total_fp = 0
    total_tn = 0
    total_fn = 0
    
    for day in range(days):
        hours = (day + 1) * 24
        discoveries = list_top_discoveries(
            s.app.database_path,
            min_score=min_score,
            limit=limit,
            hours=hours,
        )
        scores = [float(d.get("discovery_score") or 0.0) for d in discoveries]
        avg_score = mean(scores) if scores else 0.0
        
        # Calculate metrics if we have labels
        day_tp = day_fp = day_tn = day_fn = 0
        if labeled_artifacts:
            for disc in discoveries:
                artifact_id = disc.get("id")
                if artifact_id in labeled_artifacts:
                    label = labeled_artifacts[artifact_id]
                    score = float(disc.get("discovery_score") or 0.0)
                    
                    # Predict: positive if score >= min_score
                    predicted_positive = score >= min_score
                    actual_positive = label in ("true_positive", "relevant", "positive")
                    
                    if predicted_positive and actual_positive:
                        day_tp += 1
                    elif predicted_positive and not actual_positive:
                        day_fp += 1
                    elif not predicted_positive and not actual_positive:
                        day_tn += 1
                    elif not predicted_positive and actual_positive:
                        day_fn += 1
        
        total_tp += day_tp
        total_fp += day_fp
        total_tn += day_tn
        total_fn += day_fn
        
        summary_lines.append((day + 1, len(discoveries), avg_score, day_tp, day_fp, day_fn))

    console.print(f"\n[green]Backtest summary (last {days} days):[/green]")
    for day_num, count, avg, tp, fp, fn in summary_lines:
        if show_metrics and (tp > 0 or fp > 0 or fn > 0):
            console.print(f"  • Day {day_num}: {count} discoveries, avg score {avg:.2f} | TP={tp} FP={fp} FN={fn}")
        else:
            console.print(f"  • Day {day_num}: {count} discoveries, avg score {avg:.2f}")
    
    # Calculate overall metrics if we have labels
    if show_metrics and (total_tp > 0 or total_fp > 0):
        metrics = calculate_metrics(total_tp, total_fp, total_tn, total_fn)
        console.print("\n[cyan]Overall Metrics:[/cyan]")
        console.print(f"  Precision: {metrics.precision:.3f}")
        console.print(f"  Recall:    {metrics.recall:.3f}")
        console.print(f"  F1 Score:  {metrics.f1_score:.3f}")
        console.print(f"  Accuracy:  {metrics.accuracy:.3f}")
        
        # Create experiment run if name provided
        if experiment_name:
            # Extract discovery weights from current settings
            scoring_weights = {
                "novelty": s.app.weights.discovery.novelty,
                "emergence": s.app.weights.discovery.emergence,
                "obscurity": s.app.weights.discovery.obscurity,
                "cross_source": s.app.weights.discovery.cross_source,
                "expert_signal": s.app.weights.discovery.expert_signal,
                "recency_half_life_hours": s.app.weights.discovery.recency_half_life_hours,
            }
            config = ExperimentConfig(
                scoring_weights=scoring_weights,
                min_score_threshold=min_score,
                lookback_days=days,
                description=f"Backtest of last {days} days with min_score={min_score}",
            )
            
            try:
                exp_id = create_experiment(s.app.database_path, experiment_name, config)
                run_id = create_experiment_run(
                    s.app.database_path,
                    exp_id,
                    metrics,
                    metadata={"backtest_days": days, "min_score": min_score},
                )
                console.print(
                    f"\n[green]✓ Created experiment '{experiment_name}' "
                    f"(ID: {exp_id}, Run: {run_id})[/green]"
                )
                
                # Compare with baseline if requested
                if compare_baseline:
                    comparison = compare_experiments(s.app.database_path, compare_baseline, exp_id)
                    if "error" in comparison:
                        console.print(f"[yellow]⚠ {comparison['error']}[/yellow]")
                    else:
                        console.print(f"\n[cyan]Comparison with baseline experiment {compare_baseline}:[/cyan]")
                        console.print(f"  F1 Score delta: {comparison['deltas']['f1Score']:+.3f}")
                        console.print(f"  Precision delta: {comparison['deltas']['precision']:+.3f}")
                        console.print(f"  Recall delta: {comparison['deltas']['recall']:+.3f}")
                        console.print(f"  Winner: {comparison['winner']}")
                        
            except ValueError as e:
                console.print(f"[yellow]⚠ {e}[/yellow]")
    elif experiment_name:
        console.print("[yellow]⚠ Cannot create experiment: no labeled artifacts found[/yellow]")
        console.print("  Use 'harvest annotate' to label some artifacts first")



@app.command("analyze")
def analyze_discovery(
    ctx: typer.Context,
    mode: str = typer.Option("research", "--mode", "-m", help="Analysis mode: research or signal"),
    limit: int = typer.Option(200, "--limit", "-n", help="Max artifacts to analyze"),
) -> None:
    """Analyze artifacts using LLM classification."""
    config_path = get_config_path(ctx)
    s = load_settings(config_path)

    if mode == "research":
        # Use research classifier
        llm_client = get_async_llm_client(s.app.llm.provider, s.app.llm.model, s.app.llm.temperature)
        classifier = ResearchClassifier(llm_client)

        # Get artifacts that need analysis
        artifacts = list_artifacts_for_analysis(s.app.database_path, limit)
        console.print(f"Found {len(artifacts)} artifacts to analyze")

        async def analyze_all():
            analyzed = 0
            for artifact in artifacts:
                try:
                    classification = await classifier.classify(artifact)
                    if classification:
                        # Store classification results
                        store_classification_results(
                            db_path=s.app.database_path, artifact_id=artifact["id"], classification=classification
                        )
                        console.print(f"✓ Analyzed {artifact['source_id']}: {classification['category']}")
                        analyzed += 1
                except Exception as e:
                    console.print(f"✗ Error analyzing {artifact['source_id']}: {e}")
                    continue
            return analyzed

        analyzed = asyncio.run(analyze_all())
        console.print(f"[green]Analyzed {analyzed} artifacts[/green]")

    elif mode == "signal":
        # Use existing signal analysis
        from ..pipeline import analyze_unanalyzed

        count = analyze_unanalyzed(s, limit=limit)
        console.print(f"[green]Analyzed {count} tweets[/green]")
    else:
        console.print(f"[red]Unknown mode: {mode}[/red]")
        raise typer.Exit(1)


@app.command("score")
def score_discovery(
    ctx: typer.Context,
    score_type: str = typer.Option("discovery", "--type", "-t", help="Score type: discovery or salience"),
    limit: int = typer.Option(500, "--limit", "-n", help="Max artifacts to score"),
) -> None:
    """Score artifacts using discovery or salience algorithms."""
    config_path = get_config_path(ctx)
    s = load_settings(config_path)

    if score_type == "discovery":
        # Run discovery scoring
        import asyncio

        count = asyncio.run(
            run_discovery_scoring(
                s.app.database_path,
                s.model_dump(),
                limit,
            )
        )
        console.print(f"[green]Discovery scoring complete: {count} artifacts scored[/green]")

    elif score_type == "salience":
        # Use existing salience scoring
        from ..pipeline import score_unscored

        count = score_unscored(s, limit=limit)
        console.print(f"[green]Salience scoring complete: {count} tweets scored[/green]")
    else:
        console.print(f"[red]Unknown score type: {score_type}[/red]")
        raise typer.Exit(1)


@app.command("discoveries")
def list_discoveries(
    ctx: typer.Context,
    min_score: float = typer.Option(80.0, "--min-score", "-s", help="Minimum discovery score"),
    limit: int = typer.Option(50, "--limit", "-n", help="Max discoveries to show"),
    hours: int = typer.Option(168, "--hours", "-h", help="Time window in hours (default: 1 week)"),
    output: str = typer.Option(
        "table",
        "--output",
        "-o",
        help="Output format: table or json",
        show_choices=True,
        case_sensitive=False,
    ),
) -> None:
    """List top discoveries by discovery score."""
    config_path = get_config_path(ctx)
    s = load_settings(config_path)

    discoveries = list_top_discoveries(s.app.database_path, min_score=min_score, limit=limit, hours=hours)

    if not discoveries:
        console.print("[yellow]No discoveries found matching criteria[/yellow]")
        return

    if output.lower() == "json":
        console.print_json(data=discoveries)
        return

    console.print(f"[green]Found {len(discoveries)} discoveries:[/green]\n")

    for i, discovery in enumerate(discoveries, 1):
        console.print(f"{i}. [bold]{discovery.get('title') or '(untitled)'}[/bold]")
        console.print(
            "   Source: {source} | Score: {score:.1f} (N {novelty:.1f}, E {emergence:.1f}, O {obscurity:.1f})".format(
                source=discovery.get("source", "unknown"),
                score=discovery.get("discovery_score", 0.0),
                novelty=discovery.get("novelty", 0.0),
                emergence=discovery.get("emergence", 0.0),
                obscurity=discovery.get("obscurity", 0.0),
            )
        )
        if discovery.get("category") or discovery.get("sentiment"):
            console.print(
                "   Classification: {classification} | Sentiment: {sentiment} | Urgency: {urgency}".format(
                    classification=discovery.get("category") or "n/a",
                    sentiment=discovery.get("sentiment") or "n/a",
                    urgency=discovery.get("urgency", "n/a"),
                )
            )
        if discovery.get("topics"):
            console.print(f"   Topics: {', '.join(discovery['topics'])}")
        if discovery.get("tags"):
            console.print(f"   Tags: {', '.join(discovery['tags'])}")
        if discovery.get("reasoning"):
            console.print(f"   Reasoning: {discovery['reasoning']}")
        console.print(f"   URL: {discovery.get('url')}")
        console.print()


@app.command("topics")
def list_topics(
    ctx: typer.Context,
    window_days: int = typer.Option(14, "--window", "-w", help="Time window in days"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max topics to show"),
) -> None:
    """List trending topics."""
    config_path = get_config_path(ctx)
    s = load_settings(config_path)

    from ..db import get_trending_topics

    topics = get_trending_topics(s.app.database_path, window_days=window_days, limit=limit)

    if not topics:
        console.print("[yellow]No trending topics found[/yellow]")
        return

    console.print(f"[green]Top {len(topics)} trending topics (last {window_days} days):[/green]\n")

    for i, topic in enumerate(topics, 1):
        console.print(f"{i}. [bold]{topic['name']}[/bold]")
        if topic.get("taxonomy_path"):
            console.print(f"   Path: {topic['taxonomy_path']}")
        console.print(f"   Artifacts: {topic['artifact_count']} | Avg Score: {topic.get('avg_discovery_score', 0):.1f}")
        console.print()


@app.command("notify")
def notify_discoveries(
    ctx: typer.Context,
    threshold: float = typer.Option(85.0, "--threshold", "-t", help="Discovery score threshold"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max notifications to send"),
) -> None:
    """Send Slack notifications for high-scoring discoveries."""
    config_path = get_config_path(ctx)
    s = load_settings(config_path)

    discoveries = list_top_discoveries(s.app.database_path, min_score=threshold, limit=limit)

    if not discoveries:
        console.print("[yellow]No discoveries to notify[/yellow]")
        return

    # Format and send notifications
    webhook = get_slack_webhook()
    if not webhook:
        console.print("[red]SLACK_WEBHOOK_URL not set[/red]")
        return

    sent = 0
    for discovery in discoveries:
        payload = format_discovery_slack_message(discovery)
        if post_to_slack(webhook, payload["text"]):
            sent += 1

    console.print(f"[green]Sent {sent} discovery notifications[/green]")


@app.command("resolve")
def resolve_identities(
    ctx: typer.Context,
    threshold: float = typer.Option(0.80, "--threshold", "-t", help="Similarity threshold for matching"),
    use_llm: bool = typer.Option(True, "--use-llm/--no-llm", help="Use LLM for confirmation"),
    batch_size: int = typer.Option(100, "--batch-size", "-b", help="Batch size for processing"),
    name_weight: float = typer.Option(0.50, "--name-weight", help="Weight for name similarity (0.0-1.0)"),
    affiliation_weight: float = typer.Option(0.30, "--affiliation-weight", help="Weight for affiliation similarity"),
    domain_weight: float = typer.Option(0.15, "--domain-weight", help="Weight for homepage domain match"),
    accounts_weight: float = typer.Option(0.05, "--accounts-weight", help="Weight for account overlap"),
) -> None:
    """Run identity resolution to merge duplicate entities.
    
    Uses multi-field weighted similarity with configurable weights to achieve >90% precision.
    Default weights: name=0.50, affiliation=0.30, domain=0.15, accounts=0.05
    """
    config_path = get_config_path(ctx)
    s = load_settings(config_path)

    # Build custom weights dict
    weights = {
        "name": name_weight,
        "affiliation": affiliation_weight,
        "domain": domain_weight,
        "accounts": accounts_weight,
    }
    
    # Normalize weights to sum to 1.0
    total = sum(weights.values())
    if total > 0:
        weights = {k: v / total for k, v in weights.items()}
    
    llm_client = None
    if use_llm:
        try:
            llm_client = get_async_llm_client(s.app.llm.provider, s.app.llm.model, s.app.llm.temperature)
            console.print("[green]LLM client initialized for confirmation[/green]")
        except Exception as e:
            console.print(f"[yellow]Warning: Could not initialize LLM client: {e}[/yellow]")
            console.print("[yellow]Falling back to similarity-only matching[/yellow]")
            use_llm = False

    console.print(f"Running identity resolution with threshold={threshold}, use_llm={use_llm}")
    console.print(f"Weights: name={weights['name']:.2f}, affiliation={weights['affiliation']:.2f}, "
                  f"domain={weights['domain']:.2f}, accounts={weights['accounts']:.2f}")

    async def run_resolution():
        result = await run_identity_resolution(
            db_path=s.app.database_path,
            llm_client=llm_client,
            similarity_threshold=threshold,
            batch_size=batch_size,
            weights=weights
        )
        return result

    result = asyncio.run(run_resolution())

    console.print("[green]Identity resolution complete:[/green]")
    console.print(f"  - Processed: {result['processed']} entities")
    console.print(f"  - Candidates found: {result['candidates_found']} potential matches")
    console.print(f"  - Merged: {result['merged']} duplicate entities")


@app.command("correlate")
def correlate_artifacts(
    ctx: typer.Context,
    artifact_id: int | None = typer.Option(None, "--artifact-id", "-a", help="Specific artifact ID to process"),
    semantic: bool = typer.Option(True, "--semantic/--no-semantic", help="Enable semantic similarity detection"),
    threshold: float = typer.Option(
        0.80, "--threshold", "-t", help="Minimum similarity threshold for semantic relationships"
    ),
    show_stats: bool = typer.Option(True, "--stats/--no-stats", help="Show relationship statistics after completion"),
) -> None:
    """Detect cross-source relationships between artifacts.
    
    Finds citations, references, and semantic relationships:
    - Extracts arXiv IDs, DOIs, GitHub URLs from text
    - Links tweets referencing papers/repos
    - Finds GitHub repos implementing arXiv papers
    - Detects semantically similar artifacts across sources
    
    Examples:
        harvest correlate                        # Process all artifacts
        harvest correlate -a 123                 # Process specific artifact
        harvest correlate --no-semantic          # Skip semantic detection
        harvest correlate -t 0.85                # Higher similarity threshold
    """
    from ..relationship_detection import get_relationship_stats, run_relationship_detection
    
    config_path = get_config_path(ctx)
    s = load_settings(config_path)
    
    console.print("[bold]Cross-Source Corroboration[/bold]")
    console.print(f"Database: {s.app.database_path}")
    if artifact_id:
        console.print(f"Processing artifact ID: {artifact_id}")
    else:
        console.print("Processing all artifacts")
    console.print(f"Semantic similarity: {'enabled' if semantic else 'disabled'}")
    if semantic:
        console.print(f"Similarity threshold: {threshold:.2f}")
    
    # Run relationship detection
    stats = run_relationship_detection(
        db_path=s.app.database_path,
        artifact_id=artifact_id,
        enable_semantic=semantic,
        semantic_threshold=threshold,
    )
    
    console.print("\n[green]Relationship detection complete:[/green]")
    console.print(f"  - Artifacts processed: {stats['processed']}")
    console.print(f"  - Relationships created: {stats['relationships_created']}")
    
    if stats.get('by_type'):
        console.print("\n[bold]By Type:[/bold]")
        for rel_type, count in sorted(stats['by_type'].items(), key=lambda x: x[1], reverse=True):
            console.print(f"  - {rel_type}: {count}")
    
    if stats.get('by_method'):
        console.print("\n[bold]By Detection Method:[/bold]")
        for method, count in sorted(stats['by_method'].items(), key=lambda x: x[1], reverse=True):
            console.print(f"  - {method}: {count}")
    
    # Show overall stats
    if show_stats:
        overall_stats = get_relationship_stats(s.app.database_path)
        console.print("\n[bold]Overall Relationship Statistics:[/bold]")
        console.print(f"  - Total relationships: {overall_stats['total_relationships']}")
        console.print(f"  - High confidence (≥0.8): {overall_stats['high_confidence_count']}")
        console.print(f"  - Artifacts with relationships: {overall_stats['artifacts_with_relationships']}")
        
        if overall_stats.get('by_type'):
            console.print("\n[bold]All Relationships by Type:[/bold]")
            for type_stat in overall_stats['by_type']:
                console.print(
                    f"  - {type_stat['relationship_type']}: {type_stat['count']} "
                    f"(avg confidence: {type_stat['avg_confidence']:.2f})"
                )


@app.command("annotate")
def annotate_discovery(
    ctx: typer.Context,
    artifact_id: int = typer.Argument(..., help="Artifact ID to label"),
    label: str = typer.Argument(..., help="Label (true_positive, false_positive, relevant, irrelevant)"),
    confidence: float = typer.Option(1.0, "--confidence", "-c", help="Confidence in label (0.0-1.0)"),
    annotator: str | None = typer.Option(None, "--annotator", "-a", help="Annotator name"),
    notes: str | None = typer.Option(None, "--notes", "-n", help="Notes about the label"),
    import_csv: str | None = typer.Option(None, "--import", "-i", help="Import labels from CSV file"),
    export_csv: str | None = typer.Option(None, "--export", "-e", help="Export labels to CSV file"),
) -> None:
    """
    Annotate artifacts with ground truth labels for experiment validation.
    
    Labels can be: true_positive, false_positive, relevant, irrelevant, positive, negative
    
    Examples:
      harvest annotate 123 true_positive --confidence 0.9
      harvest annotate 456 false_positive --notes "Not actually breakthrough"
      harvest annotate --import labels.csv
      harvest annotate --export labels.csv
    """
    
    config_path = get_config_path(ctx)
    s = load_settings(config_path)
    init_db(s.app.database_path)
    run_migrations(s.app.database_path)
    
    import csv

    from ..experiment import add_discovery_label, get_labeled_artifacts
    
    # Export labels to CSV
    if export_csv:
        labels = get_labeled_artifacts(s.app.database_path)
        with open(export_csv, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'artifactId', 'label', 'confidence', 'annotator', 'notes',
                'artifactTitle', 'artifactSource', 'createdAt', 'updatedAt'
            ])
            writer.writeheader()
            writer.writerows(labels)
        
        console.print(f"[green]✓ Exported {len(labels)} labels to {export_csv}[/green]")
        return
    
    # Import labels from CSV
    if import_csv:
        import os
        if not os.path.exists(import_csv):
            console.print(f"[red]✗ File not found: {import_csv}[/red]")
            raise typer.Exit(1)
        
        imported = 0
        with open(import_csv, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    add_discovery_label(
                        s.app.database_path,
                        int(row['artifactId']),
                        row['label'],
                        float(row.get('confidence', 1.0)),
                        row.get('annotator'),
                        row.get('notes'),
                    )
                    imported += 1
                except Exception as e:
                    console.print(f"[yellow]⚠ Skipped row {row}: {e}[/yellow]")
        
        console.print(f"[green]✓ Imported {imported} labels from {import_csv}[/green]")
        return
    
    # Add single label
    if not artifact_id or not label:
        console.print("[red]✗ artifact_id and label are required (or use --import/--export)[/red]")
        raise typer.Exit(1)
    
    valid_labels = {'true_positive', 'false_positive', 'relevant', 'irrelevant', 'positive', 'negative'}
    if label not in valid_labels:
        console.print(f"[yellow]⚠ Unusual label '{label}' (valid: {', '.join(valid_labels)})[/yellow]")
    
    if not 0.0 <= confidence <= 1.0:
        console.print("[red]✗ Confidence must be between 0.0 and 1.0[/red]")
        raise typer.Exit(1)
    
    label_id = add_discovery_label(
        s.app.database_path,
        artifact_id,
        label,
        confidence,
        annotator,
        notes,
    )
    
    console.print(f"[green]✓ Labeled artifact {artifact_id} as '{label}' (label ID: {label_id})[/green]")
    if notes:
        console.print(f"  Notes: {notes}")


