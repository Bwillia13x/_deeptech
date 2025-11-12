"""CLI commands for security scanning and vulnerability management."""

from pathlib import Path

import typer
from rich.console import Console

from signal_harvester.security import (
    display_security_report,
    generate_security_recommendations,
    run_security_scan,
    save_security_report,
)

from .core import app

console = Console()

security_app = typer.Typer(help="Security scanning and vulnerability management commands")
app.add_typer(security_app, name="security")


@security_app.command("scan")
def scan_vulnerabilities(
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Save report to JSON file",
    ),
    fail_on_critical: bool = typer.Option(
        False,
        "--fail-on-critical",
        help="Exit with non-zero status if critical vulnerabilities found",
    ),
    fail_on_high: bool = typer.Option(
        False,
        "--fail-on-high",
        help="Exit with non-zero status if high or critical vulnerabilities found",
    ),
) -> None:
    """Run comprehensive security vulnerability scan.

    Scans all installed dependencies using pip-audit and safety tools.
    Generates a detailed report of known vulnerabilities with severity ratings.

    Examples:
        harvest security scan
        harvest security scan --output security-report.json
        harvest security scan --fail-on-critical  # Exit 1 if critical found
    """
    try:
        # Run security scan
        report = run_security_scan()

        # Display report
        display_security_report(report)

        # Show recommendations
        console.print("[bold cyan]Recommendations:[/bold cyan]\n")
        recommendations = generate_security_recommendations(report)
        for rec in recommendations:
            console.print(f"  {rec}")
        console.print()

        # Save report if requested
        if output:
            save_security_report(report, output)

        # Fail if requested and vulnerabilities found
        if fail_on_critical and report.critical_count > 0:
            console.print("[bold red]❌ Critical vulnerabilities found. Exiting with error.[/bold red]")
            raise typer.Exit(code=1)

        if fail_on_high and (report.critical_count > 0 or report.high_count > 0):
            console.print("[bold red]❌ High or critical vulnerabilities found. Exiting with error.[/bold red]")
            raise typer.Exit(code=1)

        # Summary status
        if report.total_vulnerabilities == 0:
            console.print("[bold green]✓ Security scan complete. No vulnerabilities found.[/bold green]")
        else:
            console.print(f"[yellow]⚠  Security scan complete. {report.total_vulnerabilities} vulnerabilities found.[/yellow]")

    except Exception as e:
        console.print(f"[bold red]Error running security scan: {e}[/bold red]")
        raise typer.Exit(code=1)


@security_app.command("check-deps")
def check_dependencies() -> None:
    """Quick check of installed security scanning tools.

    Verifies that pip-audit and safety are installed and accessible.
    """
    import subprocess

    console.print("[bold blue]Checking security scanning tools...[/bold blue]\n")

    tools = [
        ("pip-audit", ["pip-audit", "--version"]),
        ("safety", ["safety", "--version"]),
    ]

    all_installed = True

    for tool_name, cmd in tools:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            version = result.stdout.strip() or result.stderr.strip()
            console.print(f"[green]✓ {tool_name}[/green] installed: {version}")
        except FileNotFoundError:
            console.print(f"[red]✗ {tool_name}[/red] not installed")
            all_installed = False
        except Exception as e:
            console.print(f"[yellow]? {tool_name}[/yellow] error: {e}")
            all_installed = False

    console.print()

    if all_installed:
        console.print("[bold green]✓ All security scanning tools are installed.[/bold green]")
    else:
        console.print("[bold yellow]⚠  Some tools are missing. Install with:[/bold yellow]")
        console.print("  pip install pip-audit safety")


@security_app.command("recommendations")
def show_recommendations() -> None:
    """Show security recommendations and best practices.

    Displays general security guidelines for the Signal Harvester project.
    """
    console.print("[bold cyan]🔒 Security Best Practices & Recommendations[/bold cyan]\n")

    recommendations = [
        ("🔄 Regular Scans", "Run `harvest security scan` weekly or before deployments"),
        ("🚨 Critical Response", "Address critical vulnerabilities within 24 hours"),
        ("⚠️  High Priority", "Fix high-severity issues within 7 days"),
        ("📦 Keep Updated", "Update dependencies regularly: `pip install --upgrade -r requirements.txt`"),
        ("🔐 API Keys", "Rotate API keys every 90 days (X, OpenAI, Anthropic)"),
        ("🗝️  Environment", "Never commit .env files or secrets to version control"),
        ("🔍 CI/CD", "Security scans run automatically in GitHub Actions on every push"),
        ("📊 Monitor", "Review security-reports artifacts in GitHub Actions runs"),
        ("🛡️  Dependencies", "Pin dependency versions to avoid unexpected updates"),
        ("📝 Audit Logs", "Enable and review audit logs in production environments"),
    ]

    for title, description in recommendations:
        console.print(f"[bold]{title}:[/bold] {description}")

    console.print("\n[bold blue]Compliance Checklist:[/bold blue]\n")

    checklist = [
        "[ ] Weekly security scans completed",
        "[ ] No critical or high vulnerabilities in production",
        "[ ] API keys rotated within last 90 days",
        "[ ] All secrets stored in environment variables",
        "[ ] Dependencies pinned in pyproject.toml",
        "[ ] CI/CD security checks passing",
        "[ ] Audit logs enabled and monitored",
        "[ ] Backup and recovery procedures tested",
    ]

    for item in checklist:
        console.print(f"  {item}")

    console.print()
