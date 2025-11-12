"""CLI commands for analytics and reporting.

Provides commands for:
- Source analytics and breakdowns
- Temporal trend analysis
- Cross-source correlation analysis
- System health monitoring
- Report generation
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.table import Table

from .. import analytics
from ..config import load_settings
from .core import app, console

# Create analytics subcommand
analytics_app = typer.Typer(help="Analytics and reporting commands")
app.add_typer(analytics_app, name="analytics")


@analytics_app.command("sources")
def analyze_sources(
    hours: Optional[int] = typer.Option(None, help="Time window in hours (None for all time)"),
    output: Optional[Path] = typer.Option(None, help="Output file path (JSON or YAML)"),
    format: str = typer.Option("table", help="Output format: table, json, yaml"),
) -> None:
    """Analyze artifact distribution across sources."""
    settings = load_settings()
    
    try:
        console.print("[blue]Analyzing source distribution...[/blue]")
        data = analytics.get_source_distribution(settings.app.database_path, hours=hours)
        
        if format == "table":
            console.print(f"\n[yellow]Source Distribution ({data['time_window']})[/yellow]")
            console.print(f"Total artifacts: {data['total_artifacts']}\n")
            
            # Create table
            table_data = []
            for source in data["sources"]:
                table_data.append([
                    source["source"],
                    str(source["count"]),
                    f"{source['percentage']}%",
                    f"{source['avg_discovery_score']}",
                    f"{source['avg_novelty']}",
                    f"{source['avg_emergence']}",
                    f"{source['avg_obscurity']}"
                ])
            
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Source")
            table.add_column("Count", justify="right")
            table.add_column("%", justify="right")
            table.add_column("Avg Score", justify="right")
            table.add_column("Novelty", justify="right")
            table.add_column("Emergence", justify="right")
            table.add_column("Obscurity", justify="right")
            for row in table_data:
                table.add_row(*row)
            console.print(table)
            
        elif format == "json":
            if output:
                with open(output, "w") as f:
                    json.dump(data, f, indent=2)
                console.print(f"[green]Results saved to {output}[/green]")
            else:
                console.print_json(data=data)
                
        elif format == "yaml":
            if output:
                with open(output, "w") as f:
                    yaml.dump(data, f, default_flow_style=False)
                console.print(f"[green]Results saved to {output}[/green]")
            else:
                console.print(yaml.dump(data, default_flow_style=False))
        
        console.print("[green]✓ Analysis complete[/green]")
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@analytics_app.command("trends")
def analyze_trends(
    days: int = typer.Option(30, help="Number of days to analyze"),
    output: Optional[Path] = typer.Option(None, help="Output file path (JSON or YAML)"),
    format: str = typer.Option("table", help="Output format: summary, json, yaml"),
) -> None:
    """Analyze temporal trends in artifact publication and scores."""
    settings = load_settings()
    
    try:
        console.print(f"[blue]Analyzing temporal trends for {days} days...[/blue]")
        data = analytics.get_temporal_trends(settings.app.database_path, days=days)
        
        if format == "summary":
            console.print(f"\n[yellow]Temporal Trends ({data['days']} days)[/yellow]")
            console.print(f"Total artifacts: {data['summary']['total_artifacts']}")
            console.print(f"Avg daily artifacts: {data['summary']['avg_daily_artifacts']}")
            
            # Show recent days
            recent_days = sorted(data["daily_trends"].items())[-7:]  # Last 7 days
            console.print("\n[blue]Recent Activity:[/blue]")
            
            for date, day_data in recent_days:
                console.print(f"  {date}: {day_data['totals']['count']} artifacts")
                for source, source_data in day_data["sources"].items():
                    avg_score = source_data['avg_discovery_score']
                    console.print(f"    {source}: {source_data['count']} (avg score: {avg_score})")
            
        elif format == "table":
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Date")
            table.add_column("Total", justify="right")
            table.add_column("Avg Score", justify="right")
            table.add_column("Sources", justify="right")
            # Show last 14 days sorted chronologically
            recent_days = sorted(data["daily_trends"].items())[-14:]
            for date, day_data in recent_days:
                total = day_data["totals"]["count"]
                avg_score = day_data["totals"].get("avg_score", 0.0)
                source_count = len(day_data["sources"])
                table.add_row(
                    date,
                    str(total),
                    f"{avg_score:.2f}",
                    str(source_count),
                )
            console.print(table)
            
        elif format == "json":
            if output:
                with open(output, "w") as f:
                    json.dump(data, f, indent=2)
                console.print(f"[green]Results saved to {output}[/green]")
            else:
                console.print_json(data=data)
                
        elif format == "yaml":
            if output:
                with open(output, "w") as f:
                    yaml.dump(data, f, default_flow_style=False)
                console.print(f"[green]Results saved to {output}[/green]")
            else:
                console.print(yaml.dump(data, default_flow_style=False))
        
        console.print("[green]✓ Trend analysis complete[/green]")
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@analytics_app.command("correlations")
def analyze_correlations(
    hours: int = typer.Option(168, help="Time window in hours (default: 7 days)"),
    min_sources: int = typer.Option(2, help="Minimum number of sources for correlation"),
    output: Optional[Path] = typer.Option(None, help="Output file path (JSON or YAML)"),
    format: str = typer.Option("table", help="Output format: table, json, yaml"),
) -> None:
    """Analyze cross-source correlations for topics."""
    settings = load_settings()
    
    try:
        console.print("[blue]Analyzing cross-source correlations...[/blue]")
        data = analytics.get_cross_source_correlations(settings.app.database_path, hours=hours)
        
        # Filter by min_sources
        correlations = [c for c in data["correlations"] if c["source_count"] >= min_sources]
        
        if format == "table":
            console.print(f"\n[yellow]Cross-Source Correlations ({data['time_window']})[/yellow]")
            console.print(f"Min sources: {min_sources}")
            console.print(f"Total correlated topics: {len(correlations)}\n")
            
            if correlations:
                table_data = []
                for corr in correlations[:20]:  # Top 20
                    sources_str = ", ".join([f"{s}({corr['sources'][s]['count']})" for s in corr["sources"]])
                    table_data.append([
                        corr["topic"],
                        str(corr["source_count"]),
                        str(corr["total_artifacts"]),
                        sources_str
                    ])
                
                table = Table(show_header=True, header_style="bold magenta")
                table.add_column("Topic")
                table.add_column("Sources", justify="right")
                table.add_column("Total Artifacts", justify="right")
                table.add_column("Source Breakdown")
                for row in table_data:
                    table.add_row(*row)
                console.print(table)
                
                if len(correlations) > 20:
                    console.print(f"\n... and {len(correlations) - 20} more topics")
            else:
                console.print("No correlations found matching criteria")
                
        elif format == "json":
            output_data = {**data, "correlations": correlations}
            if output:
                with open(output, "w") as f:
                    json.dump(output_data, f, indent=2)
                console.print(f"[green]Results saved to {output}[/green]")
            else:
                console.print_json(data=output_data)
                
        elif format == "yaml":
            output_data = {**data, "correlations": correlations}
            if output:
                with open(output, "w") as f:
                    yaml.dump(output_data, f, default_flow_style=False)
                console.print(f"[green]Results saved to {output}[/green]")
            else:
                console.print(yaml.dump(output_data, default_flow_style=False))
        
        console.print("[green]✓ Correlation analysis complete[/green]")
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@analytics_app.command("health")
def check_health(
    detailed: bool = typer.Option(False, help="Show detailed health information"),
    output: Optional[Path] = typer.Option(None, help="Output file path (JSON or YAML)"),
    format: str = typer.Option("summary", help="Output format: summary, json, yaml"),
) -> None:
    """Check system health and performance metrics."""
    settings = load_settings()
    
    try:
        console.print("[blue]Checking system health...[/blue]")
        data = analytics.get_system_health(settings.app.database_path, settings)
        
        if format == "summary":
            console.print(f"\n[yellow]System Health Status: {data['status'].upper()}[/yellow]")
            console.print(f"Checked at: {data['timestamp']}\n")
            
            for component, status_data in data["components"].items():
                status = status_data["status"]
                status_color = "green" if status == "healthy" else "yellow" if status == "warning" else "red"
                console.print(f"[{status_color}]{component}: {status}[/{status_color}]")
                
                if detailed and status_data.get("status") != "error":
                    for key, value in status_data.items():
                        if key != "status":
                            console.print(f"  {key}: {value}")
                    console.print()
                    
        elif format == "json":
            if output:
                with open(output, "w") as f:
                    json.dump(data, f, indent=2)
                console.print(f"[green]Results saved to {output}[/green]")
            else:
                console.print_json(data=data)
                
        elif format == "yaml":
            if output:
                with open(output, "w") as f:
                    yaml.dump(data, f, default_flow_style=False)
                console.print(f"[green]Results saved to {output}[/green]")
            else:
                console.print(yaml.dump(data, default_flow_style=False))
        
        # Exit with error code if unhealthy
        if data["status"] == "unhealthy":
            raise typer.Exit(2)
        elif data["status"] == "warning":
            raise typer.Exit(1)
        else:
            console.print("[green]✓ Health check complete[/green]")
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@analytics_app.command("distributions")
def analyze_distributions(
    output: Optional[Path] = typer.Option(None, help="Output file path (JSON or YAML)"),
    format: str = typer.Option("summary", help="Output format: summary, json, yaml"),
) -> None:
    """Analyze discovery score distributions."""
    settings = load_settings()
    
    try:
        console.print("[blue]Analyzing score distributions...[/blue]")
        data = analytics.get_score_distributions(settings.app.database_path)
        
        if format == "summary":
            console.print("\n[yellow]Score Distributions[/yellow]\n")
            
            summary = data["summary"]
            console.print(f"Total scored artifacts: {summary['total_scored']}")
            console.print(f"Average discovery score: {summary['avg_discovery_score']}")
            console.print(f"Score range: {summary['min_discovery_score']} - {summary['max_discovery_score']}")
            console.print(f"Average novelty: {summary['avg_novelty']}")
            console.print(f"Average emergence: {summary['avg_emergence']}")
            console.print(f"Average obscurity: {summary['avg_obscurity']}")
            
            console.print("\n[blue]Percentiles:[/blue]")
            for p, value in data["percentiles"].items():
                console.print(f"  {p}: {value}")
            
            console.print("\n[blue]Source Breakdown:[/blue]")
            for source in data["source_breakdown"]:
                src_name = source['source']
                count = source['count']
                avg_score = source['avg_discovery_score']
                console.print(f"  {src_name}: {count} artifacts, avg score {avg_score}")
                
        elif format == "json":
            if output:
                with open(output, "w") as f:
                    json.dump(data, f, indent=2)
                console.print(f"[green]Results saved to {output}[/green]")
            else:
                console.print_json(data=data)
                
        elif format == "yaml":
            if output:
                with open(output, "w") as f:
                    yaml.dump(data, f, default_flow_style=False)
                console.print(f"[green]Results saved to {output}[/green]")
            else:
                console.print(yaml.dump(data, default_flow_style=False))
        
        console.print("[green]✓ Distribution analysis complete[/green]")
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@analytics_app.command("report")
def generate_report(
    days: int = typer.Option(7, help="Number of days to analyze"),
    output: Path = typer.Option(..., help="Output file path (JSON or YAML)"),
    format: str = typer.Option("json", help="Output format: json, yaml"),
) -> None:
    """Generate comprehensive analytics report."""
    settings = load_settings()
    
    try:
        console.print(f"[blue]Generating comprehensive analytics report for {days} days...[/blue]")
        
        with console.status("Generating report..."):
            data = analytics.generate_analytics_report(settings.app.database_path, settings, days=days)
        
        if format == "json":
            with open(output, "w") as f:
                json.dump(data, f, indent=2)
        elif format == "yaml":
            with open(output, "w") as f:
                yaml.dump(data, f, default_flow_style=False)
        
        console.print(f"[green]✓ Report generated: {output}[/green]")
        console.print(f"Generation time: {data['generation_time_seconds']}s")
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@analytics_app.command("dashboard-data")
def get_dashboard_data(
    days: int = typer.Option(30, help="Number of days for trends"),
    output: Optional[Path] = typer.Option(None, help="Output file path"),
) -> None:
    """Get all dashboard data in a single call (for frontend)."""
    settings = load_settings()
    
    try:
        console.print("[blue]Collecting dashboard data...[/blue]")
        
        with console.status("Collecting data..."):
            # Gather all dashboard data
            dashboard_data = {
                "source_distribution": analytics.get_source_distribution(
                    settings.app.database_path, hours=days*24
                ),
                "temporal_trends": analytics.get_temporal_trends(
                    settings.app.database_path, days=days
                ),
                "cross_source_correlations": analytics.get_cross_source_correlations(
                    settings.app.database_path, hours=days*24
                ),
                "score_distributions": analytics.get_score_distributions(
                    settings.app.database_path
                ),
                "system_health": analytics.get_system_health(
                    settings.app.database_path, settings
                )
            }
        
        if output:
            with open(output, "w") as f:
                json.dump(dashboard_data, f, indent=2)
            console.print(f"[green]Dashboard data saved to {output}[/green]")
        else:
            console.print_json(data=dashboard_data)
        
        console.print("[green]✓ Dashboard data collection complete[/green]")
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
