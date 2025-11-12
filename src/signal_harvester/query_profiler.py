"""Enhanced database query profiling and optimization tools."""

from __future__ import annotations

import json
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


@dataclass
class SlowQuery:
    """Record of a slow query execution."""

    query: str
    execution_time_ms: float
    row_count: int
    timestamp: datetime
    explain_plan: List[str]
    has_full_scan: bool


@dataclass
class IndexRecommendation:
    """Recommended index to add based on query patterns."""

    table_name: str
    columns: List[str]
    index_name: str
    reason: str
    benefit_score: int  # 1-10 scale
    sample_query: str


class QueryProfiler:
    """Advanced query profiling with slow query detection and index recommendations."""

    def __init__(
        self,
        db_path: str,
        slow_threshold_ms: float = 100.0,
        enable_logging: bool = True,
    ):
        """Initialize profiler.

        Args:
            db_path: Path to SQLite database
            slow_threshold_ms: Queries slower than this are logged
            enable_logging: Whether to log slow queries to file
        """
        self.db_path = db_path
        self.slow_threshold_ms = slow_threshold_ms
        self.enable_logging = enable_logging
        self.slow_queries: List[SlowQuery] = []
        self.log_file = Path("logs/slow_queries.jsonl")

        if self.enable_logging:
            self.log_file.parent.mkdir(exist_ok=True)

    def profile_query(
        self,
        conn: sqlite3.Connection,
        query: str,
        label: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Profile a single query execution with detailed metrics.

        Args:
            conn: Database connection
            query: SQL query to profile
            label: Optional label for the query

        Returns:
            Dict with execution_time_ms, row_count, explain_plan, has_full_scan
        """
        # Get explain plan first
        explain_plan = self._get_explain_plan(conn, query)
        has_full_scan = self._has_full_table_scan(explain_plan)

        # Time the query
        start = time.perf_counter()
        cursor = conn.execute(query)
        rows = cursor.fetchall()
        end = time.perf_counter()

        execution_time_ms = (end - start) * 1000
        row_count = len(rows)

        result = {
            "query": query,
            "label": label,
            "execution_time_ms": execution_time_ms,
            "row_count": row_count,
            "explain_plan": explain_plan,
            "has_full_scan": has_full_scan,
        }

        # Log if slow
        if execution_time_ms >= self.slow_threshold_ms:
            slow_query = SlowQuery(
                query=query,
                execution_time_ms=execution_time_ms,
                row_count=row_count,
                timestamp=datetime.utcnow(),
                explain_plan=explain_plan,
                has_full_scan=has_full_scan,
            )
            self.slow_queries.append(slow_query)

            if self.enable_logging:
                self._log_slow_query(slow_query)

        return result

    def _get_explain_plan(self, conn: sqlite3.Connection, query: str) -> List[str]:
        """Get EXPLAIN QUERY PLAN output."""
        try:
            cursor = conn.execute(f"EXPLAIN QUERY PLAN {query}")
            plan_rows = cursor.fetchall()
            return [f"{row[0]}-{row[1]}-{row[2]}: {row[3]}" for row in plan_rows]
        except sqlite3.Error:
            return []

    def _has_full_table_scan(self, explain_plan: List[str]) -> bool:
        """Check if query plan includes a full table scan."""
        for line in explain_plan:
            if "SCAN" in line.upper() and "USING INDEX" not in line.upper():
                return True
        return False

    def _log_slow_query(self, slow_query: SlowQuery) -> None:
        """Log slow query to JSONL file."""
        log_entry = {
            "timestamp": slow_query.timestamp.isoformat(),
            "execution_time_ms": slow_query.execution_time_ms,
            "row_count": slow_query.row_count,
            "has_full_scan": slow_query.has_full_scan,
            "query": slow_query.query[:200],  # Truncate long queries
            "explain_plan": slow_query.explain_plan,
        }

        with open(self.log_file, "a") as f:
            f.write(json.dumps(log_entry) + "\n")

    def analyze_index_usage(self, conn: sqlite3.Connection) -> List[Dict[str, Any]]:
        """Analyze current index usage and coverage.

        Returns:
            List of index stats with usage information
        """
        # Get all indexes
        cursor = conn.execute(
            """
            SELECT name, tbl_name, sql 
            FROM sqlite_master 
            WHERE type = 'index' AND name NOT LIKE 'sqlite_%'
            ORDER BY tbl_name, name
            """
        )
        indexes = cursor.fetchall()

        index_stats = []
        for idx_name, table_name, create_sql in indexes:
            # Extract columns from CREATE INDEX statement
            columns = self._extract_index_columns(create_sql or "")

            index_stats.append(
                {
                    "index_name": idx_name,
                    "table_name": table_name,
                    "columns": columns,
                    "create_sql": create_sql,
                }
            )

        return index_stats

    def _extract_index_columns(self, create_sql: str) -> List[str]:
        """Extract column names from CREATE INDEX statement."""
        match = re.search(r"\((.*?)\)", create_sql)
        if match:
            columns_str = match.group(1)
            return [col.strip() for col in columns_str.split(",")]
        return []

    def recommend_indexes(
        self, conn: sqlite3.Connection
    ) -> List[IndexRecommendation]:
        """Generate index recommendations based on slow queries and table scans.

        Returns:
            List of recommended indexes with benefit scores
        """
        recommendations: List[IndexRecommendation] = []
        existing_indexes = {
            f"{stats['table_name']}.{','.join(stats['columns'])}": stats["index_name"]
            for stats in self.analyze_index_usage(conn)
        }

        # Analyze slow queries for missing indexes
        for slow_query in self.slow_queries:
            if not slow_query.has_full_scan:
                continue

            # Extract table names and potential filter columns
            tables = self._extract_table_names(slow_query.query)
            filter_columns = self._extract_filter_columns(slow_query.query)

            for table, columns in filter_columns.items():
                if table not in tables:
                    continue

                index_key = f"{table}.{','.join(columns)}"
                if index_key in existing_indexes:
                    continue  # Index already exists

                # Calculate benefit score based on query frequency and slowness
                benefit_score = min(10, int(slow_query.execution_time_ms / 10))

                index_name = f"idx_{table}_{'_'.join(columns)}"
                recommendations.append(
                    IndexRecommendation(
                        table_name=table,
                        columns=columns,
                        index_name=index_name,
                        reason=f"Frequent full table scan on {table} with WHERE {', '.join(columns)}",
                        benefit_score=benefit_score,
                        sample_query=slow_query.query[:200],
                    )
                )

        # Remove duplicates and sort by benefit score
        unique_recs = {
            f"{rec.table_name}.{','.join(rec.columns)}": rec for rec in recommendations
        }
        return sorted(unique_recs.values(), key=lambda r: r.benefit_score, reverse=True)

    def _extract_table_names(self, query: str) -> Set[str]:
        """Extract table names from SQL query."""
        tables = set()
        # Match FROM and JOIN clauses
        matches = re.findall(
            r"(?:FROM|JOIN)\s+(\w+)", query, re.IGNORECASE | re.MULTILINE
        )
        tables.update(matches)
        return tables

    def _extract_filter_columns(self, query: str) -> Dict[str, List[str]]:
        """Extract columns used in WHERE and ON clauses by table.

        Returns:
            Dict mapping table names to lists of filter columns
        """
        filter_columns: Dict[str, List[str]] = {}

        # Extract WHERE conditions
        where_match = re.search(r"WHERE\s+(.+?)(?:ORDER|GROUP|LIMIT|$)", query, re.IGNORECASE | re.DOTALL)
        if where_match:
            where_clause = where_match.group(1)
            # Find table.column patterns
            column_matches = re.findall(r"(\w+)\.(\w+)", where_clause)
            for table, column in column_matches:
                if table not in filter_columns:
                    filter_columns[table] = []
                if column not in filter_columns[table]:
                    filter_columns[table].append(column)

        return filter_columns

    def generate_report(self) -> None:
        """Generate rich console report of profiling results."""
        console.rule("Query Profiling Report")

        # Slow queries summary
        if self.slow_queries:
            slow_table = Table(title=f"Slow Queries (>{self.slow_threshold_ms}ms)", show_lines=True)
            slow_table.add_column("Time (ms)", justify="right", style="red")
            slow_table.add_column("Rows", justify="right")
            slow_table.add_column("Full Scan", justify="center")
            slow_table.add_column("Query", style="dim")

            for sq in self.slow_queries[:10]:  # Top 10 slowest
                full_scan = "❌" if sq.has_full_scan else "✓"
                query_preview = sq.query[:80] + "..." if len(sq.query) > 80 else sq.query
                slow_table.add_row(
                    f"{sq.execution_time_ms:.2f}",
                    str(sq.row_count),
                    full_scan,
                    query_preview,
                )

            console.print(slow_table)
        else:
            console.print(Panel("✓ No slow queries detected!", style="green"))

        console.print()

    def generate_index_report(
        self, conn: sqlite3.Connection, show_create_statements: bool = True
    ) -> None:
        """Generate report of index recommendations."""
        recommendations = self.recommend_indexes(conn)

        if not recommendations:
            console.print(Panel("✓ No missing indexes detected!", style="green"))
            return

        console.rule("Index Recommendations")

        rec_table = Table(title="Recommended Indexes", show_lines=True)
        rec_table.add_column("Benefit", justify="center", style="bold")
        rec_table.add_column("Table")
        rec_table.add_column("Columns")
        rec_table.add_column("Reason", style="dim")

        for rec in recommendations:
            benefit_emoji = "🔴" if rec.benefit_score >= 7 else "🟡" if rec.benefit_score >= 4 else "🟢"
            rec_table.add_row(
                f"{benefit_emoji} {rec.benefit_score}/10",
                rec.table_name,
                ", ".join(rec.columns),
                rec.reason,
            )

        console.print(rec_table)

        if show_create_statements:
            console.print("\n[bold]CREATE INDEX Statements:[/bold]\n")
            for rec in recommendations:
                create_stmt = (
                    f"CREATE INDEX {rec.index_name} "
                    f"ON {rec.table_name}({', '.join(rec.columns)});"
                )
                console.print(f"  {create_stmt}")
            console.print()


def get_query_execution_plan(
    conn: sqlite3.Connection, query: str, verbose: bool = False
) -> List[Dict[str, Any]]:
    """Get detailed query execution plan with EQP details.

    Args:
        conn: Database connection
        query: SQL query to analyze
        verbose: If True, returns EXPLAIN (bytecode) in addition to EXPLAIN QUERY PLAN

    Returns:
        List of plan steps with selectid, order, from, detail
    """
    plan_steps = []

    # Get EXPLAIN QUERY PLAN
    cursor = conn.execute(f"EXPLAIN QUERY PLAN {query}")
    for row in cursor.fetchall():
        plan_steps.append(
            {
                "type": "plan",
                "selectid": row[0],
                "order": row[1],
                "from": row[2],
                "detail": row[3],
            }
        )

    # Optionally get bytecode EXPLAIN
    if verbose:
        cursor = conn.execute(f"EXPLAIN {query}")
        bytecode_steps = []
        for row in cursor.fetchall():
            bytecode_steps.append(
                {
                    "type": "bytecode",
                    "addr": row[0],
                    "opcode": row[1],
                    "p1": row[2],
                    "p2": row[3],
                    "p3": row[4],
                    "p4": row[5],
                    "p5": row[6],
                    "comment": row[7],
                }
            )
        plan_steps.extend(bytecode_steps)

    return plan_steps
