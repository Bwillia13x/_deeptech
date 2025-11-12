"""Analytics and reporting module for Signal Harvester.

Provides comprehensive analytics capabilities including:
- Source breakdowns and distributions
- Temporal trend analysis
- Cross-source correlation analysis
- System health metrics
- Performance monitoring
"""

from __future__ import annotations

import sqlite3
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, TypedDict

from .config import Settings
from .logger import get_logger

log = get_logger(__name__)

class DailySourceMetrics(TypedDict):
    count: int
    avg_discovery_score: float
    avg_novelty: float
    avg_emergence: float
    avg_obscurity: float


class DailyTotals(TypedDict):
    count: int
    avg_score: float


class DailyTrendEntry(TypedDict):
    sources: Dict[str, DailySourceMetrics]
    totals: DailyTotals


def get_source_distribution(db_path: str, hours: Optional[int] = None) -> Dict[str, Any]:
    """Get distribution of artifacts across sources.
    
    Args:
        db_path: Path to SQLite database
        hours: Optional time window in hours (None for all time)
        
    Returns:
        Dictionary with source distribution and metrics
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        # Base query
        query = """
            SELECT 
                source,
                COUNT(*) as count,
                AVG(discovery_score) as avg_discovery_score,
                AVG(novelty) as avg_novelty,
                AVG(emergence) as avg_emergence,
                AVG(obscurity) as avg_obscurity
            FROM artifacts a
            LEFT JOIN scores s ON a.id = s.artifact_id
            WHERE 1=1
        """
        params = []
        
        # Add time filter if specified
        if hours:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            query += " AND a.published_at >= ?"
            params.append(cutoff.isoformat())
        
        query += " GROUP BY source ORDER BY count DESC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        sources = []
        total_artifacts = 0
        
        for row in rows:
            source = row[0]
            count = row[1]
            avg_discovery = row[2] or 0
            avg_novelty = row[3] or 0
            avg_emergence = row[4] or 0
            avg_obscurity = row[5] or 0
            
            sources.append({
                "source": source,
                "count": count,
                "percentage": 0,  # Will be calculated
                "avg_discovery_score": round(avg_discovery, 2),
                "avg_novelty": round(avg_novelty, 2),
                "avg_emergence": round(avg_emergence, 2),
                "avg_obscurity": round(avg_obscurity, 2)
            })
            total_artifacts += count
        
        # Calculate percentages
        for source in sources:
            source["percentage"] = round((source["count"] / total_artifacts * 100) if total_artifacts > 0 else 0, 1)
        
        return {
            "sources": sources,
            "total_artifacts": total_artifacts,
            "time_window": f"{hours}h" if hours else "all_time"
        }


def get_temporal_trends(db_path: str, days: int = 30) -> Dict[str, Any]:
    """Get temporal trends for artifacts and scores.
    
    Args:
        db_path: Path to SQLite database
        days: Number of days to analyze
        
    Returns:
        Dictionary with daily trends and metrics
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        query = """
            SELECT 
                DATE(published_at) as date,
                source,
                COUNT(*) as count,
                AVG(discovery_score) as avg_discovery_score,
                AVG(novelty) as avg_novelty,
                AVG(emergence) as avg_emergence,
                AVG(obscurity) as avg_obscurity
            FROM artifacts a
            LEFT JOIN scores s ON a.id = s.artifact_id
            WHERE published_at >= date('now', '-{days} days')
            GROUP BY DATE(published_at), source
            ORDER BY date DESC
        """.format(days=days)
        
        cursor.execute(query)
        rows = cursor.fetchall()
        
        # Organize by date then source
        daily_data: defaultdict[str, DailyTrendEntry] = defaultdict(
            lambda: {"sources": {}, "totals": {"count": 0, "avg_score": 0.0}}
        )
        
        for row in rows:
            date = row[0]
            source = row[1]
            count = row[2]
            avg_discovery = row[3] or 0
            avg_novelty = row[4] or 0
            avg_emergence = row[5] or 0
            avg_obscurity = row[6] or 0
            
            daily_data[date]["sources"][source] = {
                "count": count,
                "avg_discovery_score": round(avg_discovery, 2),
                "avg_novelty": round(avg_novelty, 2),
                "avg_emergence": round(avg_emergence, 2),
                "avg_obscurity": round(avg_obscurity, 2)
            }
            
            daily_data[date]["totals"]["count"] += count
        
        # Calculate daily averages
        for date, data in daily_data.items():
            total_count = sum(s["count"] for s in data["sources"].values())
            weighted_score = sum(
                s["count"] * s["avg_discovery_score"] for s in data["sources"].values()
            )
            data["totals"]["avg_score"] = round(
                weighted_score / total_count if total_count > 0 else 0, 2
            )
        
        return {
            "daily_trends": dict(daily_data),
            "days": days,
            "summary": {
                "total_artifacts": sum(d["totals"]["count"] for d in daily_data.values()),
                "avg_daily_artifacts": round(
                    sum(d["totals"]["count"] for d in daily_data.values()) / len(daily_data), 1
                ) if daily_data else 0,
            }
        }


def get_cross_source_correlations(db_path: str, hours: int = 168) -> Dict[str, Any]:
    """Analyze correlations between different sources.
    
    Args:
        db_path: Path to SQLite database
        hours: Time window in hours (default: 7 days)
        
    Returns:
        Dictionary with correlation analysis results
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        # Find topics that appear in multiple sources within the time window
        query = """
            WITH topic_sources AS (
                SELECT 
                    t.name as topic,
                    a.source,
                    COUNT(DISTINCT a.id) as artifact_count,
                    COUNT(DISTINCT DATE(a.published_at)) as days_active
                FROM topics t
                JOIN artifact_topics at ON t.id = at.topic_id
                JOIN artifacts a ON at.artifact_id = a.id
                LEFT JOIN scores s ON a.id = s.artifact_id
                WHERE a.published_at >= datetime('now', '-{hours} hours')
                    AND s.discovery_score >= 70  -- High-quality artifacts only
                GROUP BY t.name, a.source
            )
            SELECT 
                topic,
                GROUP_CONCAT(source || ':' || artifact_count || ':' || days_active) as source_data
            FROM topic_sources
            GROUP BY topic
            HAVING COUNT(DISTINCT source) > 1
            ORDER BY COUNT(DISTINCT source) DESC, SUM(artifact_count) DESC
        """.format(hours=hours)
        
        cursor.execute(query)
        rows = cursor.fetchall()
        
        correlations = []
        for row in rows:
            topic = row[0]
            source_data = row[1]
            
            # Parse source data
            sources = {}
            for item in source_data.split(","):
                parts = item.split(":")
                if len(parts) == 3:
                    source = parts[0]
                    count = int(parts[1])
                    days = int(parts[2])
                    sources[source] = {"count": count, "days_active": days}
            
            correlations.append({
                "topic": topic,
                "sources": sources,
                "source_count": len(sources),
                "total_artifacts": sum(s["count"] for s in sources.values())
            })
        
        return {
            "correlations": correlations,
            "time_window": f"{hours}h",
            "summary": {
                "total_correlated_topics": len(correlations),
                "avg_sources_per_topic": round(
                    sum(c["source_count"] for c in correlations) / len(correlations), 1
                ) if correlations else 0
            }
        }


def get_system_health(db_path: str, settings: Settings) -> Dict[str, Any]:
    """Get comprehensive system health metrics.
    
    Args:
        db_path: Path to SQLite database
        settings: Application settings
        
    Returns:
        Dictionary with system health status
    """
    components: dict[str, dict[str, Any]] = {}
    health: dict[str, Any] = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "components": components,
        "metrics": {}
    }
    
    # Database health
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Check database size
            cursor.execute("PRAGMA page_count")
            page_count = cursor.fetchone()[0]
            cursor.execute("PRAGMA page_size")
            page_size = cursor.fetchone()[0]
            db_size_mb = (page_count * page_size) / (1024 * 1024)
            
            # Check table counts
            cursor.execute("SELECT COUNT(*) FROM artifacts")
            artifact_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM entities")
            entity_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM topics")
            topic_count = cursor.fetchone()[0]
            
            # Check for recent activity
            cursor.execute("""
                SELECT COUNT(*) FROM artifacts 
                WHERE published_at >= datetime('now', '-24 hours')
            """)
            recent_artifacts = cursor.fetchone()[0]
            
            components["database"] = {
                "status": "healthy",
                "size_mb": round(db_size_mb, 1),
                "artifact_count": artifact_count,
                "entity_count": entity_count,
                "topic_count": topic_count,
                "recent_artifacts_24h": recent_artifacts
            }
            
    except Exception as e:
        components["database"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health["status"] = "unhealthy"
    
    # Pipeline health
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Check for unanalyzed artifacts
            cursor.execute("""
                SELECT COUNT(*) FROM artifacts a
                LEFT JOIN artifact_topics at ON a.id = at.artifact_id
                WHERE at.artifact_id IS NULL
            """)
            unanalyzed_count = cursor.fetchone()[0]
            
            # Check for unscored artifacts
            cursor.execute("""
                SELECT COUNT(*) FROM artifacts a
                LEFT JOIN scores s ON a.id = s.artifact_id
                WHERE s.artifact_id IS NULL
            """)
            unscored_count = cursor.fetchone()[0]
            
            components["pipeline"] = {
                "status": "healthy" if unanalyzed_count < 100 else "warning",
                "unanalyzed_artifacts": unanalyzed_count,
                "unscored_artifacts": unscored_count
            }
            
    except Exception as e:
        components["pipeline"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health["status"] = "unhealthy"
    
    # API health (basic check)
    components["api"] = {
        "status": "healthy",
        "version": "1.0.0"
    }
    
    # Overall status determination
    component_statuses = [comp["status"] for comp in components.values()]
    if any(status == "unhealthy" for status in component_statuses):
        health["status"] = "unhealthy"
    elif any(status == "warning" for status in component_statuses):
        health["status"] = "warning"
    
    return health


def get_score_distributions(db_path: str) -> Dict[str, Any]:
    """Get distributions of discovery scores and components.
    
    Args:
        db_path: Path to SQLite database
        
    Returns:
        Dictionary with score distributions
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        # Get overall distributions
        query = """
            SELECT 
                COUNT(*) as total,
                AVG(discovery_score) as avg_discovery,
                MIN(discovery_score) as min_discovery,
                MAX(discovery_score) as max_discovery,
                AVG(novelty) as avg_novelty,
                AVG(emergence) as avg_emergence,
                AVG(obscurity) as avg_obscurity
            FROM scores
            WHERE discovery_score IS NOT NULL
        """
        
        cursor.execute(query)
        row = cursor.fetchone()
        
        percentile_values: dict[str, float] = {}
        source_breakdown: list[dict[str, float | int]] = []

        distributions = {
            "summary": {
                "total_scored": row[0] or 0,
                "avg_discovery_score": round(row[1] or 0, 2),
                "min_discovery_score": round(row[2] or 0, 2),
                "max_discovery_score": round(row[3] or 0, 2),
                "avg_novelty": round(row[4] or 0, 2),
                "avg_emergence": round(row[5] or 0, 2),
                "avg_obscurity": round(row[6] or 0, 2)
            },
            "percentiles": percentile_values,
            "source_breakdown": source_breakdown
        }
        
        # Calculate percentiles
        percentile_points = [10, 25, 50, 75, 90, 95, 99]
        for p in percentile_points:
            cursor.execute(f"""
                SELECT discovery_score FROM scores
                WHERE discovery_score IS NOT NULL
                ORDER BY discovery_score
                LIMIT 1 OFFSET (SELECT COUNT(*) FROM scores WHERE discovery_score IS NOT NULL) * {p} / 100
            """)
            result = cursor.fetchone()
            if result:
                percentile_values[f"p{p}"] = round(result[0], 2)
        
        # Get source-specific distributions
        cursor.execute("""
            SELECT 
                a.source,
                COUNT(*) as count,
                AVG(s.discovery_score) as avg_discovery,
                AVG(s.novelty) as avg_novelty,
                AVG(s.emergence) as avg_emergence,
                AVG(s.obscurity) as avg_obscurity
            FROM scores s
            JOIN artifacts a ON s.artifact_id = a.id
            GROUP BY a.source
            ORDER BY count DESC
        """)
        
        for row in cursor.fetchall():
            source_breakdown.append({
                "source": row[0],
                "count": row[1],
                "avg_discovery_score": round(row[2] or 0, 2),
                "avg_novelty": round(row[3] or 0, 2),
                "avg_emergence": round(row[4] or 0, 2),
                "avg_obscurity": round(row[5] or 0, 2)
            })
        
        return distributions


def generate_analytics_report(db_path: str, settings: Settings, days: int = 7) -> Dict[str, Any]:
    """Generate a comprehensive analytics report.
    
    Args:
        db_path: Path to SQLite database
        settings: Application settings
        days: Number of days to analyze
        
    Returns:
        Complete analytics report
    """
    start_time = time.time()
    
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "period": f"{days} days",
        "source_distribution": get_source_distribution(db_path, hours=days*24),
        "temporal_trends": get_temporal_trends(db_path, days=days),
        "cross_source_correlations": get_cross_source_correlations(db_path, hours=days*24),
        "score_distributions": get_score_distributions(db_path),
        "system_health": get_system_health(db_path, settings),
        "generation_time_seconds": 0
    }
    
    report["generation_time_seconds"] = round(time.time() - start_time, 2)
    
    return report
