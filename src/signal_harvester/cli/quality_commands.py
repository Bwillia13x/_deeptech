"""CLI commands for Quality Assurance System (Phase 2.4)."""

from __future__ import annotations

import json
import sqlite3
from typing import Optional

import typer

from ..config import Settings, load_settings
from ..logger import get_logger
from ..quality_assurance import create_quality_engine

log = get_logger(__name__)

app = typer.Typer(help="Quality assurance commands")


def get_db_path(settings: Settings | None = None) -> str:
    """Get database path from settings."""
    if settings is None:
        settings = load_settings()
    return settings.app.database_path


@app.command("run-validation")
def run_validation(
    check_type: str = typer.Argument(..., help="Type to validate: artifact, entity, topic, score, or all"),
    target_id: Optional[int] = typer.Option(None, "--target-id", help="Specific target ID to validate"),
    db_path: Optional[str] = typer.Option(None, "--db", help="Database path"),
) -> None:
    """Run validation rules for a specific type or all types."""
    settings = load_settings()
    db = db_path or get_db_path(settings)
    
    engine = create_quality_engine(db, settings)
    
    types_to_check = ["artifact", "entity", "topic", "score"] if check_type == "all" else [check_type]
    
    total_issues = 0
    for ctype in types_to_check:
        typer.echo(f"Running validation for {ctype}...")
        issues = engine.run_validation(ctype, target_id)
        
        if issues:
            typer.echo(f"  Found {len(issues)} issues:")
            for issue in issues[:10]:  # Show first 10
                typer.echo(
                    f"    - {issue['rule_name']} ({issue['severity']}): {issue['description']} "
                    f"[target: {issue['target_type']}:{issue['target_id']}]"
                )
            if len(issues) > 10:
                typer.echo(f"    ... and {len(issues) - 10} more")
        else:
            typer.echo("  No issues found ✓")
        
        total_issues += len(issues)
    
    typer.echo(f"\nTotal issues found: {total_issues}")


@app.command("compute-score")
def compute_quality_score(
    target_type: str = typer.Argument(..., help="Target type: artifact, entity, or topic"),
    target_id: int = typer.Argument(..., help="Target ID"),
    db_path: Optional[str] = typer.Option(None, "--db", help="Database path"),
) -> None:
    """Compute quality score for a specific target."""
    settings = load_settings()
    db = db_path or get_db_path(settings)
    
    engine = create_quality_engine(db, settings)
    
    typer.echo(f"Computing quality score for {target_type}:{target_id}...")
    score = engine.compute_quality_score(target_type, target_id)
    
    typer.echo(f"\nQuality Score: {score.overall_score:.2f}/100")
    typer.echo("\nComponent Scores:")
    for component, value in score.component_scores.items():
        typer.echo(f"  {component}: {value:.2f}")
    
    if score.validation_issues:
        typer.echo(f"\nOpen Validation Issues: {len(score.validation_issues)}")
    
    if score.last_reviewed_at:
        typer.echo(f"\nLast Reviewed: {score.last_reviewed_at} by {score.reviewer}")


@app.command("full-check")
def run_full_quality_check(
    db_path: Optional[str] = typer.Option(None, "--db", help="Database path"),
    generate_reviews: bool = typer.Option(
        True,
        "--generate-reviews/--no-generate-reviews",
        help="Generate review queue items",
    ),
) -> None:
    """Run complete quality check across all data."""
    settings = load_settings()
    db = db_path or get_db_path(settings)
    
    engine = create_quality_engine(db, settings)
    
    typer.echo("Starting full quality check...")
    results = engine.run_full_quality_check()
    
    typer.echo("\n" + "="*60)
    typer.echo("QUALITY CHECK RESULTS")
    typer.echo("="*60)
    
    for key, value in results.items():
        if key == "data_quality_metrics":
            typer.echo("\nData Quality Metrics:")
            typer.echo(json.dumps(value, indent=2))
        else:
            typer.echo(f"{key}: {value}")
    
    typer.echo("\n✓ Full quality check completed")


@app.command("review-queue")
def get_review_queue(
    status: str = typer.Option("pending", "--status", help="Review status: pending, approved, rejected, escalated"),
    assigned_to: Optional[str] = typer.Option(None, "--assigned-to", help="Filter by assignee"),
    limit: int = typer.Option(50, "--limit", help="Maximum number of items to show"),
    db_path: Optional[str] = typer.Option(None, "--db", help="Database path"),
) -> None:
    """Show review queue items."""
    settings = load_settings()
    db = db_path or get_db_path(settings)
    
    engine = create_quality_engine(db, settings)
    
    items = engine.get_review_queue(status=status, assigned_to=assigned_to, limit=limit)
    
    if not items:
        typer.echo(f"No items found with status '{status}'")
        return
    
    typer.echo(f"\nReview Queue ({status}): {len(items)} items")
    typer.echo("="*80)
    
    for item in items:
        typer.echo(f"\nID: {item['id']} | Type: {item['item_type']}:{item['item_id']}")
        typer.echo(f"Review Type: {item['review_type']} | Priority: {item['priority']}")
        if item['assigned_to']:
            typer.echo(f"Assigned To: {item['assigned_to']}")
        if item.get('quality_score'):
            typer.echo(f"Quality Score: {item['quality_score']:.2f}")
        if item.get('validation_issue_count', 0) > 0:
            typer.echo(f"Validation Issues: {item['validation_issue_count']}")
        typer.echo(f"Created: {item['created_at']}")
        if item.get('due_at'):
            typer.echo(f"Due: {item['due_at']}")


@app.command("process-review")
def process_review(
    review_id: int = typer.Argument(..., help="Review ID"),
    decision: str = typer.Argument(..., help="Decision: approve, reject, escalate"),
    reviewer: str = typer.Option(..., "--reviewer", help="Reviewer name/ID"),
    notes: Optional[str] = typer.Option(None, "--notes", help="Review notes"),
    db_path: Optional[str] = typer.Option(None, "--db", help="Database path"),
) -> None:
    """Process a review decision."""
    settings = load_settings()
    db = db_path or get_db_path(settings)
    
    engine = create_quality_engine(db, settings)
    
    typer.echo(f"Processing review {review_id}...")
    
    try:
        engine.process_review(review_id, reviewer, decision, notes)
        typer.echo(f"✓ Review {review_id} processed: {decision}")
    except ValueError as e:
        typer.echo(f"✗ Error: {e}", err=True)
        raise typer.Exit(1)


@app.command("add-review")
def add_review_item(
    item_type: str = typer.Argument(..., help="Item type: artifact, entity, topic"),
    item_id: int = typer.Argument(..., help="Item ID"),
    review_type: str = typer.Argument(..., help="Review type: quality_review, linking_review, merge_review"),
    priority: int = typer.Option(50, "--priority", help="Priority 0-100"),
    assigned_to: Optional[str] = typer.Option(None, "--assigned-to", help="Assign to user"),
    due_hours: int = typer.Option(72, "--due-hours", help="Hours until due"),
    db_path: Optional[str] = typer.Option(None, "--db", help="Database path"),
) -> None:
    """Add an item to the review queue."""
    settings = load_settings()
    db = db_path or get_db_path(settings)
    
    engine = create_quality_engine(db, settings)
    
    typer.echo(f"Adding {item_type}:{item_id} to review queue...")
    
    review_id = engine.add_to_review_queue(
        item_type=item_type,
        item_id=item_id,
        review_type=review_type,
        priority=priority,
        assigned_to=assigned_to,
        due_hours=due_hours,
    )
    
    typer.echo(f"✓ Review item added (ID: {review_id})")


@app.command("audit-log")
def get_audit_log(
    entity_type: Optional[str] = typer.Option(None, "--entity-type", help="Filter by entity type"),
    entity_id: Optional[int] = typer.Option(None, "--entity-id", help="Filter by entity ID"),
    event_type: Optional[str] = typer.Option(None, "--event-type", help="Filter by event type"),
    limit: int = typer.Option(50, "--limit", help="Maximum number of events"),
    db_path: Optional[str] = typer.Option(None, "--db", help="Database path"),
) -> None:
    """Show audit log events."""
    settings = load_settings()
    db = db_path or get_db_path(settings)
    
    conn = sqlite3.connect(db, timeout=10.0)
    try:
        query = "SELECT * FROM audit_trail WHERE 1=1"
        params: list[object] = []
        
        if entity_type:
            query += " AND entity_type = ?"
            params.append(entity_type)
        
        if entity_id:
            query += " AND entity_id = ?"
            params.append(entity_id)
        
        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        cur = conn.execute(query, params)
        events = [dict(row) for row in cur.fetchall()]
        
        if not events:
            typer.echo("No audit events found")
            return
        
        typer.echo(f"\nAudit Log: {len(events)} events")
        typer.echo("="*80)
        
        for event in events:
            typer.echo(f"\nID: {event['id']} | {event['timestamp']}")
            typer.echo(f"Event: {event['event_type']} | Entity: {event['entity_type']}:{event['entity_id']}")
            if event['user_id']:
                typer.echo(f"User: {event['user_id']}")
            if event['new_values']:
                typer.echo(f"New Values: {event['new_values'][:100]}...")
    finally:
        conn.close()


@app.command("metrics")
def get_quality_metrics(
    db_path: Optional[str] = typer.Option(None, "--db", help="Database path"),
) -> None:
    """Show data quality metrics."""
    settings = load_settings()
    db = db_path or get_db_path(settings)
    
    engine = create_quality_engine(db, settings)
    
    typer.echo("Computing data quality metrics...")
    metrics = engine.get_data_quality_metrics()
    
    typer.echo("\n" + "="*60)
    typer.echo("DATA QUALITY METRICS")
    typer.echo("="*60)
    
    typer.echo(json.dumps(metrics, indent=2))


@app.command("initialize")
def initialize_quality_system(
    db_path: Optional[str] = typer.Option(None, "--db", help="Database path"),
) -> None:
    """Initialize the quality assurance system."""
    settings = load_settings()
    db = db_path or get_db_path(settings)
    
    typer.echo("Initializing quality assurance system...")
    
    create_quality_engine(db, settings)
    
    typer.echo("✓ Database tables created")
    typer.echo("✓ Default validation rules registered")
    typer.echo("\nQuality assurance system ready!")
    typer.echo("\nNext steps:")
    typer.echo("  1. Run 'harvest quality run-validation all' to check existing data")
    typer.echo("  2. Run 'harvest quality full-check' for comprehensive analysis")
    typer.echo("  3. Check 'harvest quality review-queue' for items needing review")


if __name__ == "__main__":
    app()
