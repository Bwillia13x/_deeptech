#!/usr/bin/env python3
"""
End-to-End PostgreSQL Migration Testing Script

This script performs comprehensive testing of the PostgreSQL migration,
validating data integrity, API functionality, and performance metrics.

Usage:
    # Full test suite
    python scripts/test_migration.py --sqlite var/app.db --postgres postgresql://user:pass@localhost/db

    # Quick validation only
    python scripts/test_migration.py --sqlite var/app.db --postgres postgresql://... --quick

    # Performance testing
    python scripts/test_migration.py --sqlite var/app.db --postgres postgresql://... --performance

    # Generate HTML report
    python scripts/test_migration.py --sqlite var/app.db --postgres postgresql://... --report migration_test.html
"""

import argparse
import json
import sqlite3
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

try:
    import psycopg2
    import psycopg2.extras
    POSTGRES_AVAILABLE = True
except ImportError:
    psycopg2 = None  # type: ignore
    POSTGRES_AVAILABLE = False
    print("WARNING: psycopg2 not installed. Install with: pip install psycopg2-binary")

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    requests = None  # type: ignore
    REQUESTS_AVAILABLE = False
    print("WARNING: requests not installed. Install with: pip install requests")


@dataclass
class TestResult:
    """Test result with pass/fail status and details."""
    name: str
    passed: bool
    message: str
    duration_ms: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TestSuite:
    """Collection of test results."""
    name: str
    results: List[TestResult] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0
    
    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results)
    
    @property
    def pass_count(self) -> int:
        return sum(1 for r in self.results if r.passed)
    
    @property
    def fail_count(self) -> int:
        return sum(1 for r in self.results if not r.passed)
    
    @property
    def duration_seconds(self) -> float:
        return self.end_time - self.start_time if self.end_time > 0 else 0.0


class MigrationTester:
    """Comprehensive migration testing framework."""
    
    def __init__(self, sqlite_path: str, postgres_url: str, api_base_url: str = "http://localhost:8000"):
        self.sqlite_path = sqlite_path
        self.postgres_url = postgres_url
        self.api_base_url = api_base_url
        self.suites: List[TestSuite] = []
        
        # Connections
        self.sqlite_conn: Optional[sqlite3.Connection] = None
        self.pg_conn: Optional[Any] = None
    
    def connect(self):
        """Establish database connections."""
        print(f"Connecting to SQLite: {self.sqlite_path}")
        self.sqlite_conn = sqlite3.connect(self.sqlite_path)
        self.sqlite_conn.row_factory = sqlite3.Row
        
        if POSTGRES_AVAILABLE:
            print(f"Connecting to PostgreSQL: {self.postgres_url.split('@')[-1]}")
            self.pg_conn = psycopg2.connect(self.postgres_url)
        else:
            print("WARNING: PostgreSQL connection skipped (psycopg2 not installed)")
    
    def disconnect(self):
        """Close database connections."""
        if self.sqlite_conn:
            self.sqlite_conn.close()
        if self.pg_conn:
            self.pg_conn.close()
    
    def run_test(self, suite: TestSuite, test_name: str, test_func) -> TestResult:
        """Run a single test and record result."""
        print(f"  Running: {test_name}...", end=" ", flush=True)
        start = time.time()
        
        try:
            result = test_func()
            duration_ms = (time.time() - start) * 1000
            
            if isinstance(result, TestResult):
                result.duration_ms = duration_ms
                test_result = result
            else:
                test_result = TestResult(
                    name=test_name,
                    passed=True,
                    message="PASS",
                    duration_ms=duration_ms
                )
            
            status = "✓ PASS" if test_result.passed else "✗ FAIL"
            print(f"{status} ({duration_ms:.1f}ms)")
            
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            test_result = TestResult(
                name=test_name,
                passed=False,
                message=f"Exception: {str(e)}",
                duration_ms=duration_ms
            )
            print(f"✗ FAIL ({duration_ms:.1f}ms): {e}")
        
        suite.results.append(test_result)
        return test_result
    
    @contextmanager
    def run_suite(self, suite: TestSuite) -> Generator[TestSuite, None, None]:
        """Run a test suite."""
        print(f"\n{'='*80}")
        print(f"Test Suite: {suite.name}")
        print(f"{'='*80}")
        
        suite.start_time = time.time()
        try:
            yield suite  # Allow tests to be added
        finally:
            suite.end_time = time.time()
            
            print(f"\nSuite Results: {suite.pass_count} passed, {suite.fail_count} failed")
            print(f"Duration: {suite.duration_seconds:.2f}s")
            
            self.suites.append(suite)
    
    # Data Integrity Tests
    
    def test_row_counts(self) -> TestResult:
        """Validate row counts match between SQLite and PostgreSQL."""
        if not self.sqlite_conn or not self.pg_conn:
            return TestResult("row_counts", False, "Connections not established")
        
        tables = [
            "cursors", "tweets", "snapshots", "artifacts", "artifact_scores",
            "topics", "artifact_topics", "entities", "artifact_entities",
            "artifact_relationships", "topic_similarity", "experiments",
            "experiment_runs", "discovery_labels"
        ]
        
        mismatches = []
        counts = {}
        
        for table in tables:
            # Check if table exists in SQLite
            sqlite_cursor = self.sqlite_conn.cursor()
            sqlite_cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,)
            )
            if not sqlite_cursor.fetchone():
                continue
            
            # Get counts
            sqlite_cursor.execute(f"SELECT COUNT(*) FROM {table}")
            sqlite_count = sqlite_cursor.fetchone()[0]
            
            pg_cursor = self.pg_conn.cursor()
            pg_cursor.execute(f"SELECT COUNT(*) FROM {table}")
            pg_count = pg_cursor.fetchone()[0]
            
            counts[table] = {"sqlite": sqlite_count, "postgres": pg_count}
            
            if sqlite_count != pg_count:
                mismatches.append(f"{table}: SQLite={sqlite_count}, PostgreSQL={pg_count}")
        
        if mismatches:
            return TestResult(
                "row_counts",
                False,
                f"Row count mismatches: {', '.join(mismatches)}",
                details=counts
            )
        
        return TestResult(
            "row_counts",
            True,
            f"All {len(counts)} tables match",
            details=counts
        )
    
    def test_data_checksums(self) -> TestResult:
        """Validate data checksums for key tables."""
        if not self.sqlite_conn or not self.pg_conn:
            return TestResult("data_checksums", False, "Connections not established")
        
        # Check artifacts table checksums
        sqlite_cursor = self.sqlite_conn.cursor()
        sqlite_cursor.execute("SELECT id, title, source FROM artifacts ORDER BY id LIMIT 100")
        sqlite_data = [(row[0], row[1], row[2]) for row in sqlite_cursor.fetchall()]
        
        pg_cursor = self.pg_conn.cursor()
        pg_cursor.execute("SELECT id, title, source FROM artifacts ORDER BY id LIMIT 100")
        pg_data = [(row[0], row[1], row[2]) for row in pg_cursor.fetchall()]
        
        if sqlite_data != pg_data:
            return TestResult(
                "data_checksums",
                False,
                f"Data mismatch in artifacts (SQLite: {len(sqlite_data)} rows, PostgreSQL: {len(pg_data)} rows)"
            )
        
        return TestResult(
            "data_checksums",
            True,
            f"Verified {len(sqlite_data)} artifact records match"
        )
    
    def test_foreign_keys(self) -> TestResult:
        """Validate foreign key constraints."""
        if not self.pg_conn:
            return TestResult("foreign_keys", False, "PostgreSQL connection not established")
        
        pg_cursor = self.pg_conn.cursor()
        
        # Check for FK violations
        pg_cursor.execute("""
            SELECT conname, conrelid::regclass, confrelid::regclass
            FROM pg_constraint
            WHERE contype = 'f'
        """)
        
        fk_count = len(pg_cursor.fetchall())
        
        return TestResult(
            "foreign_keys",
            True,
            f"Verified {fk_count} foreign key constraints",
            details={"fk_count": fk_count}
        )
    
    def test_indexes(self) -> TestResult:
        """Validate indexes exist in PostgreSQL."""
        if not self.pg_conn:
            return TestResult("indexes", False, "PostgreSQL connection not established")
        
        pg_cursor = self.pg_conn.cursor()
        
        # Count indexes
        pg_cursor.execute("""
            SELECT COUNT(*)
            FROM pg_indexes
            WHERE schemaname = 'public'
        """)
        
        index_count = pg_cursor.fetchone()[0]
        
        if index_count < 30:  # Expected: 30+ indexes
            return TestResult(
                "indexes",
                False,
                f"Only {index_count} indexes found (expected 30+)"
            )
        
        return TestResult(
            "indexes",
            True,
            f"Verified {index_count} indexes exist",
            details={"index_count": index_count}
        )
    
    # Performance Tests
    
    def test_query_performance(self) -> TestResult:
        """Compare query performance between SQLite and PostgreSQL."""
        if not self.sqlite_conn or not self.pg_conn:
            return TestResult("query_performance", False, "Connections not established")
        
        queries = [
            ("discoveries", "SELECT * FROM artifacts ORDER BY discovery_score DESC LIMIT 100"),
            ("topics", "SELECT * FROM topics ORDER BY artifact_count DESC LIMIT 50"),
            ("recent", "SELECT * FROM artifacts WHERE created_at > date('now', '-7 days') LIMIT 100"),
        ]
        
        results = {}
        
        for query_name, query in queries:
            # SQLite timing
            sqlite_cursor = self.sqlite_conn.cursor()
            start = time.time()
            sqlite_cursor.execute(query)
            sqlite_cursor.fetchall()
            sqlite_ms = (time.time() - start) * 1000
            
            # PostgreSQL timing
            pg_cursor = self.pg_conn.cursor()
            start = time.time()
            pg_cursor.execute(query)
            pg_cursor.fetchall()
            pg_ms = (time.time() - start) * 1000
            
            results[query_name] = {
                "sqlite_ms": round(sqlite_ms, 2),
                "postgres_ms": round(pg_ms, 2),
                "ratio": round(pg_ms / sqlite_ms, 2) if sqlite_ms > 0 else 0
            }
        
        # Check if any query is >10x slower
        slow_queries = [k for k, v in results.items() if v["ratio"] > 10]
        
        if slow_queries:
            return TestResult(
                "query_performance",
                False,
                f"Queries >10x slower on PostgreSQL: {', '.join(slow_queries)}",
                details=results
            )
        
        return TestResult(
            "query_performance",
            True,
            "All queries within 10x of SQLite performance",
            details=results
        )
    
    # API Tests
    
    def test_api_health(self) -> TestResult:
        """Test API health endpoint."""
        if not REQUESTS_AVAILABLE or not requests:
            return TestResult("api_health", False, "requests library not installed")
        
        try:
            response = requests.get(f"{self.api_base_url}/health", timeout=5)
            
            if response.status_code == 200:
                return TestResult("api_health", True, "API responding")
            else:
                return TestResult(
                    "api_health",
                    False,
                    f"API returned status {response.status_code}"
                )
        except Exception as e:
            return TestResult("api_health", False, f"API unreachable: {e}")
    
    def test_api_discoveries(self) -> TestResult:
        """Test discoveries API endpoint."""
        if not REQUESTS_AVAILABLE or not requests:
            return TestResult("api_discoveries", False, "requests library not installed")
        
        try:
            response = requests.get(
                f"{self.api_base_url}/api/discoveries",
                params={"limit": 10},
                timeout=10
            )
            
            if response.status_code != 200:
                return TestResult(
                    "api_discoveries",
                    False,
                    f"API returned status {response.status_code}"
                )
            
            data = response.json()
            
            if not isinstance(data, list):
                return TestResult(
                    "api_discoveries",
                    False,
                    f"Expected list, got {type(data)}"
                )
            
            return TestResult(
                "api_discoveries",
                True,
                f"Retrieved {len(data)} discoveries",
                details={"count": len(data)}
            )
        
        except Exception as e:
            return TestResult("api_discoveries", False, f"API error: {e}")
    
    def test_api_topics(self) -> TestResult:
        """Test topics API endpoint."""
        if not REQUESTS_AVAILABLE or not requests:
            return TestResult("api_topics", False, "requests library not installed")
        
        try:
            response = requests.get(
                f"{self.api_base_url}/api/topics",
                params={"limit": 20},
                timeout=10
            )
            
            if response.status_code != 200:
                return TestResult(
                    "api_topics",
                    False,
                    f"API returned status {response.status_code}"
                )
            
            data = response.json()
            
            return TestResult(
                "api_topics",
                True,
                f"Retrieved {len(data)} topics",
                details={"count": len(data)}
            )
        
        except Exception as e:
            return TestResult("api_topics", False, f"API error: {e}")
    
    # Report Generation
    
    def generate_report(self, output_path: str):
        """Generate HTML test report."""
        html = self._generate_html_report()
        
        with open(output_path, "w") as f:
            f.write(html)
        
        print(f"\n✓ Report generated: {output_path}")
    
    def _generate_html_report(self) -> str:
        """Generate HTML content for test report."""
        total_tests = sum(len(s.results) for s in self.suites)
        total_passed = sum(s.pass_count for s in self.suites)
        total_failed = sum(s.fail_count for s in self.suites)
        
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>PostgreSQL Migration Test Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1 {{ color: #333; }}
        .summary {{ background: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0; }}
        .suite {{ margin: 20px 0; border: 1px solid #ddd; border-radius: 5px; }}
        .suite-header {{ background: #4CAF50; color: white; padding: 10px; }}
        .suite-header.failed {{ background: #f44336; }}
        .test {{ padding: 10px; border-bottom: 1px solid #eee; }}
        .test.passed {{ background: #e8f5e9; }}
        .test.failed {{ background: #ffebee; }}
        .details {{ font-size: 0.9em; color: #666; margin-top: 5px; }}
        .pass {{ color: #4CAF50; font-weight: bold; }}
        .fail {{ color: #f44336; font-weight: bold; }}
    </style>
</head>
<body>
    <h1>PostgreSQL Migration Test Report</h1>
    <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    
    <div class="summary">
        <h2>Summary</h2>
        <p><strong>Total Tests:</strong> {total_tests}</p>
        <p><strong class="pass">Passed:</strong> {total_passed}</p>
        <p><strong class="fail">Failed:</strong> {total_failed}</p>
        <p><strong>Success Rate:</strong> {total_passed*100//total_tests if total_tests > 0 else 0}%</p>
    </div>
"""
        
        for suite in self.suites:
            suite_status = "passed" if suite.passed else "failed"
            html += f"""
    <div class="suite">
        <div class="suite-header {suite_status}">
            <h3>{suite.name}</h3>
            <p>Duration: {suite.duration_seconds:.2f}s | {suite.pass_count} passed, {suite.fail_count} failed</p>
        </div>
"""
            
            for result in suite.results:
                test_status = "passed" if result.passed else "failed"
                html += f"""
        <div class="test {test_status}">
            <strong>{result.name}</strong> - {result.message} ({result.duration_ms:.1f}ms)
"""
                if result.details:
                    html += f"""
            <div class="details">
                <pre>{json.dumps(result.details, indent=2)}</pre>
            </div>
"""
                html += "        </div>\n"
            
            html += "    </div>\n"
        
        html += """
</body>
</html>
"""
        return html
    
    def print_summary(self):
        """Print test summary to console."""
        print("\n" + "="*80)
        print("Migration Test Summary")
        print("="*80)
        
        total_tests = sum(len(s.results) for s in self.suites)
        total_passed = sum(s.pass_count for s in self.suites)
        total_failed = sum(s.fail_count for s in self.suites)
        
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {total_passed}")
        print(f"Failed: {total_failed}")
        print(f"Success Rate: {total_passed*100//total_tests if total_tests > 0 else 0}%")
        
        print("\nSuite Breakdown:")
        for suite in self.suites:
            status = "✓ PASS" if suite.passed else "✗ FAIL"
            print(f"  {status} {suite.name}: {suite.pass_count}/{len(suite.results)} passed")
        
        print("="*80)
        
        if total_failed > 0:
            print("\n⚠️  Some tests failed. Review the report for details.")
            return False
        else:
            print("\n✅ All tests passed!")
            return True


def main():
    parser = argparse.ArgumentParser(
        description="Test PostgreSQL migration end-to-end"
    )
    parser.add_argument(
        "--sqlite",
        default="var/app.db",
        help="Path to SQLite database"
    )
    parser.add_argument(
        "--postgres",
        required=True,
        help="PostgreSQL connection string"
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="API base URL for testing"
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run quick validation tests only"
    )
    parser.add_argument(
        "--performance",
        action="store_true",
        help="Run performance tests"
    )
    parser.add_argument(
        "--report",
        help="Generate HTML report at specified path"
    )
    
    args = parser.parse_args()
    
    # Validate PostgreSQL availability
    if not POSTGRES_AVAILABLE:
        print("ERROR: psycopg2 not installed. Install with: pip install psycopg2-binary")
        sys.exit(1)
    
    # Create tester
    tester = MigrationTester(args.sqlite, args.postgres, args.api_url)
    
    try:
        tester.connect()
        
        # Data Integrity Suite
        with tester.run_suite(TestSuite("Data Integrity")) as suite:
            tester.run_test(suite, "Row Count Validation", tester.test_row_counts)
            tester.run_test(suite, "Data Checksum Validation", tester.test_data_checksums)
            tester.run_test(suite, "Foreign Key Constraints", tester.test_foreign_keys)
            tester.run_test(suite, "Index Validation", tester.test_indexes)
        
        # Performance Suite (if requested)
        if args.performance or not args.quick:
            with tester.run_suite(TestSuite("Performance")) as suite:
                tester.run_test(suite, "Query Performance Comparison", tester.test_query_performance)
        
        # API Suite
        if REQUESTS_AVAILABLE:
            with tester.run_suite(TestSuite("API Functionality")) as suite:
                tester.run_test(suite, "API Health Check", tester.test_api_health)
                tester.run_test(suite, "Discoveries Endpoint", tester.test_api_discoveries)
                tester.run_test(suite, "Topics Endpoint", tester.test_api_topics)
        
        # Print summary
        all_passed = tester.print_summary()
        
        # Generate report if requested
        if args.report:
            tester.generate_report(args.report)
        
        sys.exit(0 if all_passed else 1)
    
    finally:
        tester.disconnect()


if __name__ == "__main__":
    main()
