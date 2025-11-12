"""Tests for security vulnerability scanning."""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from signal_harvester.security import (
    SecurityReport,
    Severity,
    Vulnerability,
    _deduplicate_vulnerabilities,
    _parse_severity,
    display_security_report,
    generate_security_recommendations,
    run_pip_audit,
    run_safety_check,
    run_security_scan,
    save_security_report,
)


@pytest.fixture
def sample_vulnerability() -> Vulnerability:
    """Create a sample vulnerability for testing."""
    return Vulnerability(
        package="requests",
        version="2.25.0",
        vulnerability_id="CVE-2023-12345",
        severity=Severity.HIGH,
        description="Sample vulnerability description",
        fixed_version="2.31.0",
        cve_id="CVE-2023-12345",
        advisory_url="https://example.com/advisory",
    )


@pytest.fixture
def sample_report(sample_vulnerability: Vulnerability) -> SecurityReport:
    """Create a sample security report for testing."""
    return SecurityReport(
        scan_date=datetime(2025, 11, 12, 10, 0, 0),
        total_vulnerabilities=3,
        critical_count=1,
        high_count=1,
        medium_count=1,
        low_count=0,
        scanned_packages=50,
        vulnerabilities=[
            sample_vulnerability,
            Vulnerability(
                package="urllib3",
                version="1.26.0",
                vulnerability_id="CVE-2023-67890",
                severity=Severity.CRITICAL,
                description="Critical vulnerability",
                fixed_version="2.0.0",
            ),
            Vulnerability(
                package="certifi",
                version="2020.1.1",
                vulnerability_id="GHSA-abcd-1234",
                severity=Severity.MEDIUM,
                description="Medium severity issue",
                fixed_version="2023.7.22",
            ),
        ],
    )


class TestSeverityParsing:
    """Tests for severity parsing."""

    def test_parse_critical_severity(self) -> None:
        """Test parsing critical severity."""
        assert _parse_severity("critical") == Severity.CRITICAL
        assert _parse_severity("CRITICAL") == Severity.CRITICAL
        assert _parse_severity("Critical Issue") == Severity.CRITICAL

    def test_parse_high_severity(self) -> None:
        """Test parsing high severity."""
        assert _parse_severity("high") == Severity.HIGH
        assert _parse_severity("HIGH") == Severity.HIGH

    def test_parse_medium_severity(self) -> None:
        """Test parsing medium severity."""
        assert _parse_severity("medium") == Severity.MEDIUM
        assert _parse_severity("moderate") == Severity.MEDIUM

    def test_parse_low_severity(self) -> None:
        """Test parsing low severity."""
        assert _parse_severity("low") == Severity.LOW
        assert _parse_severity("LOW") == Severity.LOW

    def test_parse_unknown_severity(self) -> None:
        """Test parsing unknown severity."""
        assert _parse_severity("unknown") == Severity.UNKNOWN
        assert _parse_severity(None) == Severity.UNKNOWN
        assert _parse_severity("") == Severity.UNKNOWN


class TestVulnerabilityDeduplication:
    """Tests for vulnerability deduplication."""

    def test_deduplicate_identical_vulnerabilities(self) -> None:
        """Test deduplication of identical vulnerabilities."""
        vuln1 = Vulnerability(
            package="requests",
            version="2.25.0",
            vulnerability_id="CVE-2023-12345",
            severity=Severity.HIGH,
            description="Test",
        )
        vuln2 = Vulnerability(
            package="requests",
            version="2.25.0",
            vulnerability_id="CVE-2023-12345",
            severity=Severity.HIGH,
            description="Different description",
        )

        result = _deduplicate_vulnerabilities([vuln1, vuln2])
        assert len(result) == 1
        assert result[0].vulnerability_id == "CVE-2023-12345"

    def test_deduplicate_different_vulnerabilities(self) -> None:
        """Test that different vulnerabilities are not deduplicated."""
        vuln1 = Vulnerability(
            package="requests",
            version="2.25.0",
            vulnerability_id="CVE-2023-11111",
            severity=Severity.HIGH,
            description="Test",
        )
        vuln2 = Vulnerability(
            package="requests",
            version="2.25.0",
            vulnerability_id="CVE-2023-22222",
            severity=Severity.HIGH,
            description="Test",
        )

        result = _deduplicate_vulnerabilities([vuln1, vuln2])
        assert len(result) == 2

    def test_deduplicate_empty_list(self) -> None:
        """Test deduplication of empty list."""
        result = _deduplicate_vulnerabilities([])
        assert len(result) == 0


class TestSecurityReport:
    """Tests for SecurityReport functionality."""

    def test_report_to_dict(self, sample_report: SecurityReport) -> None:
        """Test converting report to dictionary."""
        report_dict = sample_report.to_dict()

        assert report_dict["total_vulnerabilities"] == 3
        assert report_dict["critical_count"] == 1
        assert report_dict["high_count"] == 1
        assert report_dict["medium_count"] == 1
        assert report_dict["low_count"] == 0
        assert report_dict["scanned_packages"] == 50
        assert len(report_dict["vulnerabilities"]) == 3

    def test_vulnerability_to_dict(self, sample_vulnerability: Vulnerability) -> None:
        """Test converting vulnerability to dictionary."""
        vuln_dict = sample_vulnerability.to_dict()

        assert vuln_dict["package"] == "requests"
        assert vuln_dict["version"] == "2.25.0"
        assert vuln_dict["vulnerability_id"] == "CVE-2023-12345"
        assert vuln_dict["severity"] == "high"
        assert vuln_dict["fixed_version"] == "2.31.0"

    def test_save_security_report(self, sample_report: SecurityReport, tmp_path: Path) -> None:
        """Test saving security report to file."""
        output_file = tmp_path / "security-report.json"
        save_security_report(sample_report, output_file)

        assert output_file.exists()

        with open(output_file) as f:
            data = json.load(f)

        assert data["total_vulnerabilities"] == 3
        assert len(data["vulnerabilities"]) == 3


class TestSecurityRecommendations:
    """Tests for security recommendations."""

    def test_recommendations_with_critical(self, sample_report: SecurityReport) -> None:
        """Test recommendations when critical vulnerabilities exist."""
        recommendations = generate_security_recommendations(sample_report)

        assert any("CRITICAL" in rec for rec in recommendations)
        assert any("critical vulnerabilities immediately" in rec.lower() for rec in recommendations)

    def test_recommendations_with_high(self, sample_report: SecurityReport) -> None:
        """Test recommendations when high vulnerabilities exist."""
        recommendations = generate_security_recommendations(sample_report)

        assert any("HIGH" in rec for rec in recommendations)

    def test_recommendations_with_no_vulnerabilities(self) -> None:
        """Test recommendations when no vulnerabilities found."""
        clean_report = SecurityReport(
            scan_date=datetime.now(),
            total_vulnerabilities=0,
            critical_count=0,
            high_count=0,
            medium_count=0,
            low_count=0,
            scanned_packages=50,
            vulnerabilities=[],
        )

        recommendations = generate_security_recommendations(clean_report)

        assert any("secure" in rec.lower() for rec in recommendations)
        assert len(recommendations) > 0

    def test_recommendations_include_upgrade_commands(self, sample_report: SecurityReport) -> None:
        """Test that recommendations include upgrade commands."""
        recommendations = generate_security_recommendations(sample_report)

        upgrade_recs = [r for r in recommendations if "pip install --upgrade" in r]
        assert len(upgrade_recs) > 0


class TestPipAudit:
    """Tests for pip-audit integration."""

    @patch("signal_harvester.security.subprocess.run")
    def test_pip_audit_no_vulnerabilities(self, mock_run: MagicMock) -> None:
        """Test pip-audit with no vulnerabilities."""
        mock_run.return_value = MagicMock(returncode=0, stdout='{"dependencies": []}', stderr="")

        result = run_pip_audit()

        assert len(result) == 0

    @patch("signal_harvester.security.subprocess.run")
    def test_pip_audit_with_vulnerabilities(self, mock_run: MagicMock) -> None:
        """Test pip-audit with vulnerabilities found."""
        mock_output = {
            "dependencies": [
                {
                    "name": "requests",
                    "version": "2.25.0",
                    "vulns": [
                        {
                            "id": "CVE-2023-12345",
                            "severity": "high",
                            "description": "Security vulnerability in requests",
                            "fix_versions": ["2.31.0"],
                        }
                    ],
                }
            ]
        }

        mock_run.return_value = MagicMock(returncode=1, stdout=json.dumps(mock_output), stderr="")

        result = run_pip_audit()

        assert len(result) == 1
        assert result[0].package == "requests"
        assert result[0].vulnerability_id == "CVE-2023-12345"

    @patch("signal_harvester.security.subprocess.run")
    def test_pip_audit_command_failure(self, mock_run: MagicMock) -> None:
        """Test handling of pip-audit command failure."""
        mock_run.return_value = MagicMock(returncode=2, stdout="", stderr="Error running pip-audit")

        with pytest.raises(RuntimeError):
            run_pip_audit()


class TestSafetyCheck:
    """Tests for safety check integration."""

    @patch("signal_harvester.security.subprocess.run")
    def test_safety_no_vulnerabilities(self, mock_run: MagicMock) -> None:
        """Test safety with no vulnerabilities."""
        mock_run.return_value = MagicMock(returncode=0, stdout="[]", stderr="")

        result = run_safety_check()

        assert len(result) == 0

    @patch("signal_harvester.security.subprocess.run")
    def test_safety_with_vulnerabilities(self, mock_run: MagicMock) -> None:
        """Test safety with vulnerabilities found."""
        mock_output = [
            {
                "package": "django",
                "installed_version": "3.0.0",
                "vulnerability_id": "PYSEC-2023-123",
                "severity": "high",
                "advisory": "SQL injection vulnerability",
                "fixed_version": "3.2.0",
                "cve": "CVE-2023-99999",
                "more_info_url": "https://example.com",
            }
        ]

        mock_run.return_value = MagicMock(returncode=1, stdout=json.dumps(mock_output), stderr="")

        result = run_safety_check()

        assert len(result) == 1
        assert result[0].package == "django"
        assert result[0].vulnerability_id == "PYSEC-2023-123"


class TestSecurityScan:
    """Tests for full security scan."""

    @patch("signal_harvester.security.run_pip_audit")
    @patch("signal_harvester.security.run_safety_check")
    @patch("signal_harvester.security.subprocess.run")
    def test_full_security_scan(
        self, mock_subprocess: MagicMock, mock_safety: MagicMock, mock_pip_audit: MagicMock
    ) -> None:
        """Test running full security scan."""
        # Mock pip-audit results
        mock_pip_audit.return_value = [
            Vulnerability(
                package="requests",
                version="2.25.0",
                vulnerability_id="CVE-2023-12345",
                severity=Severity.HIGH,
                description="Test vulnerability",
            )
        ]

        # Mock safety results
        mock_safety.return_value = [
            Vulnerability(
                package="django",
                version="3.0.0",
                vulnerability_id="PYSEC-2023-123",
                severity=Severity.CRITICAL,
                description="Critical vulnerability",
            )
        ]

        # Mock pip list for package count
        mock_subprocess.return_value = MagicMock(returncode=0, stdout='[{"name": "pkg1"}, {"name": "pkg2"}]', stderr="")

        report = run_security_scan()

        assert report.total_vulnerabilities == 2
        assert report.critical_count == 1
        assert report.high_count == 1
        assert report.scanned_packages == 2

    @patch("signal_harvester.security.run_pip_audit")
    @patch("signal_harvester.security.run_safety_check")
    def test_security_scan_deduplication(self, mock_safety: MagicMock, mock_pip_audit: MagicMock) -> None:
        """Test that security scan deduplicates vulnerabilities."""
        # Both tools return the same vulnerability
        vuln = Vulnerability(
            package="requests",
            version="2.25.0",
            vulnerability_id="CVE-2023-12345",
            severity=Severity.HIGH,
            description="Test",
        )

        mock_pip_audit.return_value = [vuln]
        mock_safety.return_value = [vuln]

        report = run_security_scan()

        assert report.total_vulnerabilities == 1


class TestDisplayFunctions:
    """Tests for display functions."""

    def test_display_security_report(self, sample_report: SecurityReport, capsys: pytest.CaptureFixture) -> None:
        """Test displaying security report."""
        display_security_report(sample_report)

        # Just verify it doesn't crash - actual output is rich formatting
        # which is hard to test without mocking console

    def test_display_clean_report(self, capsys: pytest.CaptureFixture) -> None:
        """Test displaying report with no vulnerabilities."""
        clean_report = SecurityReport(
            scan_date=datetime.now(),
            total_vulnerabilities=0,
            critical_count=0,
            high_count=0,
            medium_count=0,
            low_count=0,
            scanned_packages=50,
            vulnerabilities=[],
        )

        display_security_report(clean_report)
        # Verify no crash on clean report
