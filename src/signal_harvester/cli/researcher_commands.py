"""Phase 2.3 Researcher Profile Analytics CLI commands."""

from __future__ import annotations

import json
from typing import Optional

import typer

from ..config import load_settings
from ..db import connect
from ..logger import get_logger
from ..researcher_profile import ResearcherProfileAnalytics, run_researcher_analytics_pipeline
from .core import app, console, get_config_path

log = get_logger(__name__)
researcher_app = typer.Typer(help="Researcher profile analytics commands")
app.add_typer(researcher_app, name="researcher")


@researcher_app.command("profile")
def compute_profile(
    entity_id: int = typer.Argument(..., help="Entity ID to compute profile for"),
    config_path: Optional[str] = typer.Option(None, "--config", help="Path to config file"),
) -> None:
    """Compute and display researcher profile for a specific entity."""
    config_file = config_path or get_config_path()
    settings = load_settings(config_file)
    db_path = settings.app.database_path
    
    try:
        analytics = ResearcherProfileAnalytics(db_path, settings)
        profile = analytics.compute_full_profile(entity_id)
        
        console.print(f"[bold blue]Researcher Profile: {profile['name']}[/bold blue]")
        console.print(f"Type: {profile['type']}")
        console.print(f"Influence Score: [bold]{profile['influence_score']:.2f}[/bold]/100")
        console.print(f"Last Activity: {profile['last_activity_date']}")
        
        console.print("\n[bold]Impact Metrics:[/bold]")
        impact = profile["impact_metrics"]
        console.print(f"  Total Artifacts: {impact['total_artifacts']}")
        console.print(f"  Avg Discovery Score: {impact['avg_discovery_score']:.2f}")
        console.print(f"  H-index Proxy: {impact['h_index_proxy']}")
        console.print(f"  Total Impact: {impact['total_impact']:.2f}")
        console.print(f"  Recent Impact: {impact['recent_impact']:.2f}")
        
        console.print("\n[bold]Collaboration Network:[/bold]")
        network = profile["collaboration_network"]
        console.print(f"  Total Collaborators: {network['total_collaborators']}")
        console.print(f"  Network Density: {network['network_density']:.2f}")
        console.print(f"  Centrality: {network['centrality']:.2f}")
        
        if network["collaborators"][:5]:
            console.print("  Top Collaborators:")
            for collab in network["collaborators"][:5]:
                console.print(f"    - {collab['name']} ({collab['type']}): {collab['collaboration_count']} artifacts")
        
        console.print("\n[bold]Platform Activity:[/bold]")
        platform = profile["platform_activity"]
        console.print(f"  Primary Platform: {platform['primary_platform']}")
        console.print(f"  Cross-platform Score: {platform['cross_platform_score']:.2f}")
        console.print(f"  Active Platforms: {', '.join(platform['active_platforms'])}")
        
        console.print("\n[bold]Expertise Areas:[/bold]")
        expertise = profile["expertise_areas"]
        console.print(f"  Expertise Score: {expertise['expertise_score']:.2f}")
        console.print(f"  Topic Diversity: {expertise['topic_diversity']:.2f}")
        
        if expertise["primary_expertise"]:
            console.print("  Primary Expertise:")
            for exp in expertise["primary_expertise"][:3]:
                console.print(
                    "    - {topic}: {count} artifacts (score: {score:.2f})".format(
                        topic=exp["topic_name"],
                        count=exp["artifact_count"],
                        score=exp["expertise_score"],
                    )
                )
        
        console.print("\n[bold]Current Research Focus:[/bold]")
        trajectory = profile["research_trajectory"]
        if trajectory["current_focus"]:
            for focus in trajectory["current_focus"][:3]:
                console.print(f"  - {focus['topic_name']}: {focus['recent_activity']:.2f} recent impact")
        
        console.print("\n[green]Profile computed successfully![/green]")
        
    except Exception as e:
        log.error(f"Error computing profile for entity {entity_id}: {e}")
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@researcher_app.command("update")
def update_profiles(
    entity_id: Optional[int] = typer.Option(
        None,
        "--entity-id",
        help="Specific entity ID to update (default: all persons)",
    ),
    batch_size: int = typer.Option(
        100,
        "--batch-size",
        help="Batch size for processing",
    ),
    config_path: Optional[str] = typer.Option(
        None,
        "--config",
        help="Path to config file",
    ),
) -> None:
    """Update researcher profiles (impact metrics, networks, trajectories, influence scores)."""
    config_file = config_path or get_config_path()
    settings = load_settings(config_file)
    db_path = settings.app.database_path
    
    try:
        console.print("[bold blue]Updating Researcher Profiles...[/bold blue]")
        
        results = run_researcher_analytics_pipeline(
            db_path=db_path,
            settings=settings,
            entity_id=entity_id,
            batch_size=batch_size
        )
        
        console.print("\n[bold]Results:[/bold]")
        console.print(f"  Processed: {results['processed']}")
        console.print(f"  Successful: [green]{results['successful']}[/green]")
        console.print(f"  Failed: [red]{results['failed']}[/red]")
        
        if entity_id:
            console.print(f"\n[green]Profile for entity {entity_id} updated successfully![/green]")
        else:
            console.print("\n[green]All researcher profiles updated successfully![/green]")
        
    except Exception as e:
        log.error(f"Error updating researcher profiles: {e}")
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@researcher_app.command("list")
def list_researchers(
    min_influence: float = typer.Option(0, "--min-influence", help="Minimum influence score"),
    limit: int = typer.Option(50, "--limit", help="Maximum number of researchers to show"),
    config_path: Optional[str] = typer.Option(None, "--config", help="Path to config file"),
) -> None:
    """List researchers sorted by influence score."""
    config_file = config_path or get_config_path()
    settings = load_settings(config_file)
    db_path = settings.app.database_path
    
    try:
        conn = connect(db_path)
        cur = conn.execute("""
            SELECT 
                id, 
                name, 
                type, 
                influence_score, 
                last_activity_date,
                impact_metrics,
                platform_activity
            FROM entities
            WHERE type = 'person' AND influence_score >= ?
            ORDER BY influence_score DESC
            LIMIT ?
        """, (min_influence, limit))
        
        researchers = [dict(row) for row in cur.fetchall()]
        conn.close()
        
        if not researchers:
            console.print("[yellow]No researchers found matching criteria[/yellow]")
            return
        
        console.print(f"[bold blue]Top Researchers (Influence Score >= {min_influence})[/bold blue]\n")
        
        for i, researcher in enumerate(researchers, 1):
            influence = researcher["influence_score"] or 0
            last_activity = researcher["last_activity_date"] or "Unknown"
            
            # Parse impact metrics
            impact_data = json.loads(researcher["impact_metrics"] or "{}")
            total_artifacts = impact_data.get("total_artifacts", 0)
            
            # Parse platform activity
            platform_data = json.loads(researcher["platform_activity"] or "{}")
            active_platforms = len(platform_data.get("active_platforms", []))
            
            console.print(f"{i}. [bold]{researcher['name']}[/bold]")
            console.print(f"   Influence Score: [bold]{influence:.2f}[/bold]/100")
            console.print(
                "   Artifacts: {artifacts} | Platforms: {platforms} | Last Activity: {last_activity}".format(
                    artifacts=total_artifacts,
                    platforms=active_platforms,
                    last_activity=last_activity,
                )
            )
            console.print()
        
        console.print(f"[green]Found {len(researchers)} researchers[/green]")
        
    except Exception as e:
        log.error(f"Error listing researchers: {e}")
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@researcher_app.command("top-expertise")
def top_expertise_areas(
    limit: int = typer.Option(20, "--limit", help="Number of top expertise areas to show"),
    config_path: Optional[str] = typer.Option(None, "--config", help="Path to config file"),
) -> None:
    """Show top expertise areas across all researchers."""
    config_file = config_path or get_config_path()
    settings = load_settings(config_file)
    db_path = settings.app.database_path
    
    try:
        conn = connect(db_path)
        
        # Aggregate expertise areas across all researchers
        cur = conn.execute("""
            SELECT 
                ea.topic_name,
                ea.topic_id,
                COUNT(DISTINCT e.id) as researcher_count,
                AVG(e.influence_score) as avg_influence,
                SUM(ea.artifact_count) as total_artifacts
            FROM entities e
            CROSS JOIN json_each(e.expertise_areas, '$.primary_expertise') ea
            WHERE e.type = 'person' AND ea.topic_name IS NOT NULL
            GROUP BY ea.topic_name, ea.topic_id
            ORDER BY researcher_count DESC, avg_influence DESC
            LIMIT ?
        """)
        
        expertise_areas = [dict(row) for row in cur.fetchall()]
        conn.close()
        
        if not expertise_areas:
            console.print("[yellow]No expertise areas found[/yellow]")
            return
        
        console.print("[bold blue]Top Expertise Areas Across All Researchers[/bold blue]\n")
        
        for i, area in enumerate(expertise_areas, 1):
            console.print(f"{i}. [bold]{area['topic_name']}[/bold]")
            console.print(f"   Researchers: {area['researcher_count']}")
            console.print(f"   Avg Influence: {area['avg_influence']:.2f}")
            console.print(f"   Total Artifacts: {area['total_artifacts']}")
            console.print()
        
        console.print(f"[green]Found {len(expertise_areas)} expertise areas[/green]")
        
    except Exception as e:
        log.error(f"Error fetching expertise areas: {e}")
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@researcher_app.command("network")
def show_collaboration_network(
    entity_id: int = typer.Argument(..., help="Entity ID to show network for"),
    max_collaborators: int = typer.Option(10, "--max", help="Maximum collaborators to show"),
    config_path: Optional[str] = typer.Option(None, "--config", help="Path to config file"),
) -> None:
    """Show collaboration network for a specific researcher."""
    config_file = config_path or get_config_path()
    settings = load_settings(config_file)
    db_path = settings.app.database_path
    
    try:
        analytics = ResearcherProfileAnalytics(db_path, settings)
        network = analytics.compute_collaboration_network(entity_id)
        
        # Get researcher name
        conn = connect(db_path)
        cur = conn.execute("SELECT name FROM entities WHERE id = ?", (entity_id,))
        entity_row = cur.fetchone()
        conn.close()
        
        if not entity_row:
            console.print(f"[red]Entity {entity_id} not found[/red]")
            raise typer.Exit(1)
        
        console.print(f"[bold blue]Collaboration Network: {entity_row['name']}[/bold blue]\n")
        
        console.print("[bold]Network Statistics:[/bold]")
        console.print(f"  Total Collaborators: {network['total_collaborators']}")
        console.print(f"  Total Collaborations: {network['total_collaborations']}")
        console.print(f"  Network Density: {network['network_density']:.3f}")
        console.print(f"  Centrality: {network['centrality']:.3f}")
        
        if network['collaborators']:
            console.print(f"\n[bold]Top {min(max_collaborators, len(network['collaborators']))} Collaborators:[/bold]")
            
            for i, collab in enumerate(network['collaborators'][:max_collaborators], 1):
                console.print(f"{i}. {collab['name']} ({collab['type']})")
                console.print(f"   Collaborations: {collab['collaboration_count']} artifacts")
                console.print(f"   Total Strength: {collab['total_strength']:.2f}")
                console.print(f"   Avg Strength: {collab['avg_strength']:.2f}")
                console.print()
        
        console.print("[green]Network analysis complete![/green]")
        
    except Exception as e:
        log.error(f"Error computing collaboration network: {e}")
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@researcher_app.command("trajectory")
def show_research_trajectory(
    entity_id: int = typer.Argument(..., help="Entity ID to show trajectory for"),
    months: int = typer.Option(12, "--months", help="Number of months to show"),
    config_path: Optional[str] = typer.Option(None, "--config", help="Path to config file"),
) -> None:
    """Show research trajectory for a specific researcher."""
    config_file = config_path or get_config_path()
    settings = load_settings(config_file)
    db_path = settings.app.database_path
    
    try:
        analytics = ResearcherProfileAnalytics(db_path, settings)
        trajectory = analytics.compute_research_trajectory(entity_id)
        
        # Get researcher name
        conn = connect(db_path)
        cur = conn.execute("SELECT name FROM entities WHERE id = ?", (entity_id,))
        entity_row = cur.fetchone()
        conn.close()
        
        if not entity_row:
            console.print(f"[red]Entity {entity_id} not found[/red]")
            raise typer.Exit(1)
        
        console.print(f"[bold blue]Research Trajectory: {entity_row['name']}[/bold blue]\n")
        
        console.print(f"[bold]Productivity Trend (Last {months} Months):[/bold]")
        for trend in trajectory['productivity_trend'][-months:]:
            console.print(f"  {trend['month']}: {trend['count']} artifacts")
        
        console.print(f"\n[bold]Impact Trend (Last {months} Months):[/bold]")
        for trend in trajectory['impact_trend'][-months:]:
            console.print(f"  {trend['month']}: {trend['total_impact']:.2f} total impact")
        
        if trajectory['emerging_topics']:
            console.print("\n[bold]Emerging Topics:[/bold]")
            for topic in trajectory['emerging_topics'][:5]:
                console.print(f"  - {topic['topic_name']}: {topic['recent_activity']:.2f} recent impact")
        
        if trajectory['current_focus']:
            console.print("\n[bold]Current Research Focus:[/bold]")
            for focus in trajectory['current_focus'][:5]:
                console.print(f"  - {focus['topic_name']}: {focus['total_artifacts']} artifacts")
        
        console.print("\n[green]Trajectory analysis complete![/green]")
        
    except Exception as e:
        log.error(f"Error computing research trajectory: {e}")
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
