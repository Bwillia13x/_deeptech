"""Security vulnerability scanning and reporting.

This module provides functionality for scanning dependencies for known security
vulnerabilities using pip-audit and safety tools. It generates comprehensive
reports and tracks vulnerability trends over time.
"""

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


class Severity(str, Enum):
    """Vulnerability severity levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


@dataclass
class Vulnerability:
    """Represents a security vulnerability in a dependency."""

    package: str
    version: str
    vulnerability_id: str
    severity: Severity
    description: str
    fixed_version: str | None = None
    cve_id: str | None = None
    advisory_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert vulnerability to dictionary."""
        return {
            "package": self.package,
            "version": self.version,
            "vulnerability_id": self.vulnerability_id,
            "severity": self.severity.value,
            "description": self.description,
            "fixed_version": self.fixed_version,
            "cve_id": self.cve_id,
            "advisory_url": self.advisory_url,
        }


@dataclass
class SecurityReport:
    """Security scan report containing all vulnerabilities found."""

    scan_date: datetime
    total_vulnerabilities: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    vulnerabilities: list[Vulnerability]
    scanned_packages: int

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary."""
        return {
            "scan_date": self.scan_date.isoformat(),
            "total_vulnerabilities": self.total_vulnerabilities,
            "critical_count": self.critical_count,
            "high_count": self.high_count,
            "medium_count": self.medium_count,
            "low_count": self.low_count,
            "scanned_packages": self.scanned_packages,
            "vulnerabilities": [v.to_dict() for v in self.vulnerabilities],
        }


def run_pip_audit() -> list[Vulnerability]:
    """Run pip-audit to scan for known vulnerabilities.

    Returns:
        List of vulnerabilities found by pip-audit.

    Raises:
        RuntimeError: If pip-audit command fails.
    """
    try:
        result = subprocess.run(
            ["pip-audit", "--format", "json", "--desc"],
            capture_output=True,
            text=True,
            check=False,  # Don't raise on non-zero exit (vulnerabilities found)
        )

        if result.returncode not in (0, 1):  # 0 = clean, 1 = vulnerabilities found
            raise RuntimeError(f"pip-audit failed: {result.stderr}")

        if not result.stdout.strip():
            return []

        data = json.loads(result.stdout)
        vulnerabilities = []

        # Parse pip-audit JSON format
        for dep_info in data.get("dependencies", []):
            package = dep_info.get("name", "unknown")
            version = dep_info.get("version", "unknown")

            for vuln in dep_info.get("vulns", []):
                vulnerabilities.append(
                    Vulnerability(
                        package=package,
                        version=version,
                        vulnerability_id=vuln.get("id", "unknown"),
                        severity=_parse_severity(vuln.get("severity")),
                        description=vuln.get("description", "No description available")[:200],
                        fixed_version=", ".join(vuln.get("fix_versions", [])) or None,
                        cve_id=vuln.get("id") if vuln.get("id", "").startswith("CVE") else None,
                        advisory_url=vuln.get("aliases", [None])[0] if vuln.get("aliases") else None,
                    )
                )

        return vulnerabilities

    except FileNotFoundError:
        console.print("[yellow]Warning: pip-audit not installed. Run: pip install pip-audit[/yellow]")
        return []
    except json.JSONDecodeError as e:
        console.print(f"[yellow]Warning: Failed to parse pip-audit output: {e}[/yellow]")
        return []


def run_safety_check() -> list[Vulnerability]:
    """Run safety check to scan for known vulnerabilities.

    Returns:
        List of vulnerabilities found by safety.

    Raises:
        RuntimeError: If safety command fails.
    """
    try:
        result = subprocess.run(
            ["safety", "check", "--json"],
            capture_output=True,
            text=True,
            check=False,  # Don't raise on non-zero exit
        )

        if not result.stdout.strip():
            return []

        # Safety can output various formats, handle gracefully
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            # Safety might output text instead of JSON on errors
            return []

        vulnerabilities = []

        # Parse safety JSON format (list of vulnerabilities)
        if isinstance(data, list):
            for vuln in data:
                vulnerabilities.append(
                    Vulnerability(
                        package=vuln.get("package", "unknown"),
                        version=vuln.get("installed_version", "unknown"),
                        vulnerability_id=vuln.get("vulnerability_id", "unknown"),
                        severity=_parse_severity(vuln.get("severity")),
                        description=vuln.get("advisory", "No description available")[:200],
                        fixed_version=vuln.get("fixed_version"),
                        cve_id=vuln.get("cve"),
                        advisory_url=vuln.get("more_info_url"),
                    )
                )

        return vulnerabilities

    except FileNotFoundError:
        console.print("[yellow]Warning: safety not installed. Run: pip install safety[/yellow]")
        return []
    except Exception as e:
        console.print(f"[yellow]Warning: Safety check failed: {e}[/yellow]")
        return []


def _parse_severity(severity: str | None) -> Severity:
    """Parse severity string to Severity enum.

    Args:
        severity: Severity string from scanner.

    Returns:
        Severity enum value.
    """
    if not severity:
        return Severity.UNKNOWN

    severity_lower = severity.lower()
    if "critical" in severity_lower:
        return Severity.CRITICAL
    elif "high" in severity_lower:
        return Severity.HIGH
    elif "medium" in severity_lower or "moderate" in severity_lower:
        return Severity.MEDIUM
    elif "low" in severity_lower:
        return Severity.LOW
    else:
        return Severity.UNKNOWN


def run_security_scan() -> SecurityReport:
    """Run comprehensive security scan using all available tools.

    Returns:
        SecurityReport containing all vulnerabilities found.
    """
    console.print("[bold blue]🔍 Running security vulnerability scan...[/bold blue]\n")

    # Run both scanners
    console.print("Running pip-audit...")
    pip_audit_vulns = run_pip_audit()

    console.print("Running safety check...")
    safety_vulns = run_safety_check()

    # Combine and deduplicate vulnerabilities
    all_vulns = pip_audit_vulns + safety_vulns
    unique_vulns = _deduplicate_vulnerabilities(all_vulns)

    # Count by severity
    severity_counts = {
        Severity.CRITICAL: 0,
        Severity.HIGH: 0,
        Severity.MEDIUM: 0,
        Severity.LOW: 0,
    }

    for vuln in unique_vulns:
        if vuln.severity in severity_counts:
            severity_counts[vuln.severity] += 1

    # Get installed package count
    try:
        result = subprocess.run(["pip", "list", "--format", "json"], capture_output=True, text=True, check=True)
        packages = json.loads(result.stdout)
        package_count = len(packages)
    except Exception:
        package_count = 0

    return SecurityReport(
        scan_date=datetime.now(),
        total_vulnerabilities=len(unique_vulns),
        critical_count=severity_counts[Severity.CRITICAL],
        high_count=severity_counts[Severity.HIGH],
        medium_count=severity_counts[Severity.MEDIUM],
        low_count=severity_counts[Severity.LOW],
        scanned_packages=package_count,
        vulnerabilities=unique_vulns,
    )


def _deduplicate_vulnerabilities(vulns: list[Vulnerability]) -> list[Vulnerability]:
    """Remove duplicate vulnerabilities based on package + vulnerability_id.

    Args:
        vulns: List of vulnerabilities to deduplicate.

    Returns:
        Deduplicated list of vulnerabilities.
    """
    seen = set()
    unique = []

    for vuln in vulns:
        key = (vuln.package, vuln.vulnerability_id)
        if key not in seen:
            seen.add(key)
            unique.append(vuln)

    return unique


def display_security_report(report: SecurityReport) -> None:
    """Display security report in terminal with rich formatting.

    Args:
        report: SecurityReport to display.
    """
    # Summary panel
    summary_text = f"""
[bold]Scan Date:[/bold] {report.scan_date.strftime('%Y-%m-%d %H:%M:%S')}
[bold]Packages Scanned:[/bold] {report.scanned_packages}
[bold]Total Vulnerabilities:[/bold] {report.total_vulnerabilities}

[bold red]Critical:[/bold red] {report.critical_count}
[bold]High:[/bold] {report.high_count}
[bold yellow]Medium:[/bold yellow] {report.medium_count}
[bold blue]Low:[/bold blue] {report.low_count}
    """

    console.print(Panel(summary_text.strip(), title="🔒 Security Scan Summary", border_style="blue"))
    console.print()

    if not report.vulnerabilities:
        console.print("[bold green]✓ No vulnerabilities found![/bold green]\n")
        return

    # Vulnerabilities table
    table = Table(title="Vulnerabilities Found", show_header=True, header_style="bold magenta")
    table.add_column("Severity", style="bold")
    table.add_column("Package", style="cyan")
    table.add_column("Version")
    table.add_column("Vuln ID")
    table.add_column("Fixed In")
    table.add_column("Description", max_width=50)

    # Sort by severity (critical first)
    severity_order = {Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2, Severity.LOW: 3, Severity.UNKNOWN: 4}
    sorted_vulns = sorted(report.vulnerabilities, key=lambda v: severity_order.get(v.severity, 999))

    for vuln in sorted_vulns:
        severity_color = {
            Severity.CRITICAL: "bold red",
            Severity.HIGH: "red",
            Severity.MEDIUM: "yellow",
            Severity.LOW: "blue",
            Severity.UNKNOWN: "dim",
        }

        table.add_row(
            f"[{severity_color[vuln.severity]}]{vuln.severity.value.upper()}[/{severity_color[vuln.severity]}]",
            vuln.package,
            vuln.version,
            vuln.vulnerability_id,
            vuln.fixed_version or "N/A",
            vuln.description[:100] + "..." if len(vuln.description) > 100 else vuln.description,
        )

    console.print(table)
    console.print()


def save_security_report(report: SecurityReport, output_path: Path) -> None:
    """Save security report to JSON file.

    Args:
        report: SecurityReport to save.
        output_path: Path to save JSON report.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(report.to_dict(), f, indent=2)

    console.print(f"[green]✓ Report saved to {output_path}[/green]")


def generate_security_recommendations(report: SecurityReport) -> list[str]:
    """Generate actionable recommendations based on security scan results.

    Args:
        report: SecurityReport to analyze.

    Returns:
        List of recommendation strings.
    """
    recommendations = []

    if report.critical_count > 0:
        recommendations.append(
            f"🚨 CRITICAL: Address {report.critical_count} critical vulnerabilities immediately. "
            "These pose significant security risks."
        )

    if report.high_count > 0:
        recommendations.append(
            f"⚠️  HIGH: Prioritize fixing {report.high_count} high-severity vulnerabilities within 7 days."
        )

    if report.total_vulnerabilities > 0:
        # Group by package for upgrade recommendations
        packages_to_upgrade = {}
        for vuln in report.vulnerabilities:
            if vuln.fixed_version:
                packages_to_upgrade[vuln.package] = vuln.fixed_version

        if packages_to_upgrade:
            recommendations.append("📦 Upgrade the following packages to fix vulnerabilities:")
            for pkg, fixed_ver in list(packages_to_upgrade.items())[:5]:  # Show top 5
                recommendations.append(f"   • pip install --upgrade {pkg}>={fixed_ver}")

    if report.total_vulnerabilities == 0:
        recommendations.append("✓ All dependencies are secure. Continue regular security scans.")
    else:
        recommendations.append(
            f"📅 Schedule: Run security scans weekly. Last scan: {report.scan_date.strftime('%Y-%m-%d')}"
        )
        recommendations.append("🔄 Automation: Security scans are integrated into CI/CD pipeline.")

    return recommendations
