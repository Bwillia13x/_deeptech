"""
Researcher Profile Analytics Module

Implements Phase 2.3: Researcher profile analytics including impact metrics,
collaboration networks, research trajectory tracking, platform activity scoring,
expertise area identification, and influence scoring.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, TypedDict

import numpy as np
from sentence_transformers import SentenceTransformer

from .config import Settings
from .db import connect
from .logger import get_logger

log = get_logger(__name__)


class TaxonomyStats(TypedDict):
    count: int
    topics: list[str]


class TaxonomyEntry(TypedDict):
    category: str
    artifact_count: int
    topics: list[str]


class PipelineResults(TypedDict):
    processed: int
    successful: int
    failed: int
    entity_ids: list[int]


class ResearcherProfileAnalytics:
    """Main class for researcher profile analytics computation."""
    
    def __init__(self, db_path: str, settings: Settings):
        self.db_path = db_path
        self.settings = settings
        self.embedding_model: Optional[SentenceTransformer] = None
        
    def _get_embedding_model(self) -> SentenceTransformer:
        """Lazy load embedding model."""
        if self.embedding_model is None:
            # Use a small, fast model for embeddings
            self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        return self.embedding_model
    
    def compute_impact_metrics(self, entity_id: int) -> Dict[str, Any]:
        """
        Compute impact metrics for a researcher based on their artifacts.
        
        Uses discovery scores as a proxy for impact since we don't have
        direct citation data.
        """
        conn = connect(self.db_path)
        try:
            # Get all artifacts by this entity
            cur = conn.execute("""
                SELECT a.id, a.published_at, 
                       COALESCE(s.discovery_score, 0) as discovery_score,
                       COALESCE(s.novelty, 0) as novelty,
                       COALESCE(s.emergence, 0) as emergence,
                       COALESCE(s.obscurity, 0) as obscurity
                FROM artifacts a
                LEFT JOIN scores s ON a.id = s.artifact_id
                WHERE a.author_entity_ids LIKE ?
                ORDER BY a.published_at DESC
            """, (f'%{entity_id}%',))
            
            artifacts = [dict(row) for row in cur.fetchall()]
            
            if not artifacts:
                return {
                    "total_artifacts": 0,
                    "avg_discovery_score": 0.0,
                    "max_discovery_score": 0.0,
                    "h_index_proxy": 0,
                    "total_impact": 0.0,
                    "recent_impact": 0.0,
                    "novelty_avg": 0.0,
                    "emergence_avg": 0.0,
                    "obscurity_avg": 0.0
                }
            
            # Calculate metrics
            total_artifacts = len(artifacts)
            discovery_scores = [a["discovery_score"] or 0 for a in artifacts]
            novelty_scores = [a["novelty"] or 0 for a in artifacts]
            emergence_scores = [a["emergence"] or 0 for a in artifacts]
            obscurity_scores = [a["obscurity"] or 0 for a in artifacts]
            
            # H-index proxy: number of artifacts with score >= position
            sorted_scores = sorted(discovery_scores, reverse=True)
            h_index = sum(1 for i, score in enumerate(sorted_scores, 1) if score >= i)
            
            # Recent impact (last 90 days)
            cutoff_date = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
            recent_artifacts = [a for a in artifacts if a["published_at"] and a["published_at"] > cutoff_date]
            recent_impact = sum(a["discovery_score"] or 0 for a in recent_artifacts)
            
            return {
                "total_artifacts": total_artifacts,
                "avg_discovery_score": float(np.mean(discovery_scores)),
                "max_discovery_score": float(max(discovery_scores)),
                "h_index_proxy": int(h_index),
                "total_impact": float(sum(discovery_scores)),
                "recent_impact": float(recent_impact),
                "novelty_avg": float(np.mean(novelty_scores)),
                "emergence_avg": float(np.mean(emergence_scores)),
                "obscurity_avg": float(np.mean(obscurity_scores))
            }
        finally:
            conn.close()
    
    def compute_collaboration_network(self, entity_id: int) -> Dict[str, Any]:
        """
        Build collaboration network for a researcher based on co-authored artifacts.
        """
        conn = connect(self.db_path)
        try:
            # Get all artifacts by this entity with their co-authors
            cur = conn.execute("""
                SELECT a.id, a.author_entity_ids, s.discovery_score
                FROM artifacts a
                JOIN scores s ON a.id = s.artifact_id
                WHERE a.author_entity_ids LIKE ?
            """, (f'%{entity_id}%',))
            
            artifacts = [dict(row) for row in cur.fetchall()]
            
            if not artifacts:
                return {
                    "collaborators": [], 
                    "total_collaborators": 0,
                    "total_collaborations": 0,
                    "network_density": 0.0, 
                    "centrality": 0.0
                }
            
            # Build collaboration graph
            collaborator_counts: defaultdict[int, int] = defaultdict(int)
            collaboration_strength: defaultdict[int, float] = defaultdict(float)
            
            for artifact in artifacts:
                try:
                    author_ids = json.loads(artifact["author_entity_ids"] or "[]")
                    score = artifact["discovery_score"] or 0
                    
                    for author_id in author_ids:
                        if author_id != entity_id:
                            collaborator_counts[author_id] += 1
                            collaboration_strength[author_id] += score
                except (json.JSONDecodeError, TypeError):
                    continue
            
            # Get top collaborators
            collaborators = []
            for collab_id, count in collaborator_counts.items():
                # Get entity info
                cur = conn.execute(
                    "SELECT name, type FROM entities WHERE id = ?",
                    (collab_id,)
                )
                entity_row = cur.fetchone()
                
                if entity_row:
                    collaborators.append({
                        "entity_id": collab_id,
                        "name": entity_row["name"],
                        "type": entity_row["type"],
                        "collaboration_count": count,
                        "total_strength": float(collaboration_strength[collab_id]),
                        "avg_strength": float(collaboration_strength[collab_id] / count)
                    })
            
            # Sort by collaboration strength
            collaborators.sort(key=lambda x: x["total_strength"], reverse=True)
            
            # Calculate network metrics
            total_possible_edges = len(collaborators) * (len(collaborators) - 1) / 2 if len(collaborators) > 1 else 1
            network_density = len(collaborators) / total_possible_edges if total_possible_edges > 0 else 0
            
            # Simple centrality measure (normalized)
            centrality = len(collaborators) / max(len(artifacts), 1)
            total_collaborations = sum(collaborator_counts.values())
            
            return {
                "collaborators": collaborators[:20],  # Top 20 collaborators
                "total_collaborators": len(collaborators),
                "total_collaborations": int(total_collaborations),
                "network_density": float(network_density),
                "centrality": float(min(centrality, 1.0))
            }
        finally:
            conn.close()
    
    def compute_research_trajectory(self, entity_id: int) -> Dict[str, Any]:
        """
        Track research trajectory over time: topic evolution, productivity trends, impact trends.
        """
        conn = connect(self.db_path)
        try:
            # Get artifacts with topics over time
            cur = conn.execute("""
                SELECT 
                    a.id, 
                    a.published_at, 
                    s.discovery_score, 
                    GROUP_CONCAT(at.topic_id) as topic_ids,
                    GROUP_CONCAT(t.name) as topic_names
                FROM artifacts a
                JOIN scores s ON a.id = s.artifact_id
                LEFT JOIN artifact_topics at ON a.id = at.artifact_id
                LEFT JOIN topics t ON at.topic_id = t.id
                WHERE a.author_entity_ids LIKE ?
                GROUP BY a.id
                ORDER BY a.published_at
            """, (f'%{entity_id}%',))
            
            artifacts = [dict(row) for row in cur.fetchall()]
            
            if not artifacts:
                return {
                    "timeline": [],
                    "topic_evolution": [],
                    "productivity_trend": [],
                    "impact_trend": [],
                    "current_focus": [],
                    "emerging_topics": [],
                    "declining_topics": []
                }
            
            # Build timeline
            timeline = []
            monthly_productivity: defaultdict[str, int] = defaultdict(int)
            monthly_impact: defaultdict[str, float] = defaultdict(float)
            topic_timeline: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
            
            for artifact in artifacts:
                pub_date = artifact["published_at"]
                if not pub_date:
                    continue
                
                # Parse date and extract month
                try:
                    date_obj = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                    month_key = date_obj.strftime("%Y-%m")
                except ValueError:
                    continue
                
                score = artifact["discovery_score"] or 0
                
                # Aggregate by month
                monthly_productivity[month_key] += 1
                monthly_impact[month_key] += score
                
                # Track topics over time
                topic_ids = artifact["topic_ids"]
                if topic_ids:
                    for topic_id in topic_ids.split(","):
                        if topic_id:
                            topic_timeline[topic_id].append({
                                "date": pub_date,
                                "score": score
                            })
                
                timeline.append({
                    "date": pub_date,
                    "artifact_id": artifact["id"],
                    "score": float(score)
                })
            
            # Analyze topic evolution
            current_topics: defaultdict[str, dict[str, float | int]] = defaultdict(
                lambda: {"count": 0, "total_score": 0, "recent_score": 0}
            )
            cutoff_date = (datetime.now(timezone.utc) - timedelta(days=180)).isoformat()
            
            for topic_id, events in topic_timeline.items():
                for event in events:
                    current_topics[topic_id]["count"] += 1
                    current_topics[topic_id]["total_score"] += event["score"]
                    
                    if event["date"] > cutoff_date:
                        current_topics[topic_id]["recent_score"] += event["score"]
            
            # Get topic names
            topic_evolution = []
            for topic_id, stats in current_topics.items():
                cur = conn.execute(
                    "SELECT name FROM topics WHERE id = ?",
                    (int(topic_id),)
                )
                topic_row = cur.fetchone()
                
                if topic_row:
                    topic_evolution.append({
                        "topic_id": int(topic_id),
                        "topic_name": topic_row["name"],
                        "total_artifacts": stats["count"],
                        "avg_score": float(stats["total_score"] / stats["count"]),
                        "recent_activity": float(stats["recent_score"]),
                        "trend": "emerging" if stats["recent_score"] > (stats["total_score"] * 0.3) else "stable"
                    })
            
            # Sort by total impact
            topic_evolution.sort(key=lambda x: x["recent_activity"], reverse=True)
            
            # Build productivity and impact trends
            sorted_months = sorted(monthly_productivity.keys())
            productivity_trend = [
                {"month": month, "count": monthly_productivity[month]}
                for month in sorted_months
            ]
            
            impact_trend = [
                {"month": month, "total_impact": float(monthly_impact[month])}
                for month in sorted_months
            ]
            
            # Identify emerging and declining topics
            emerging_topics = [t for t in topic_evolution if t["trend"] == "emerging"][:5]
            declining_topics = [
                t
                for t in topic_evolution
                if (
                    t["trend"] == "stable"
                    and t["recent_activity"] < (t["avg_score"] * 0.5)
                )
            ][:5]
            
            return {
                "timeline": timeline[-50:],  # Last 50 artifacts
                "topic_evolution": topic_evolution[:10],  # Top 10 topics
                "productivity_trend": productivity_trend[-12:],  # Last 12 months
                "impact_trend": impact_trend[-12:],  # Last 12 months
                "current_focus": topic_evolution[:5],  # Top 5 current topics
                "emerging_topics": emerging_topics,
                "declining_topics": declining_topics
            }
        finally:
            conn.close()
    
    def compute_platform_activity(self, entity_id: int) -> Dict[str, Any]:
        """
        Compute platform activity scores across different platforms.
        """
        conn = connect(self.db_path)
        try:
            # Get accounts for this entity
            cur = conn.execute("""
                SELECT platform, handle_or_id, created_at
                FROM accounts
                WHERE entity_id = ?
            """, (entity_id,))
            
            # Get activity by platform
            platform_activity = {}
            
            for platform in ["x", "github", "arxiv"]:
                # Count artifacts from this platform
                cur = conn.execute("""
                    SELECT COUNT(*) as count, MAX(published_at) as last_activity
                    FROM artifacts a
                    JOIN scores s ON a.id = s.artifact_id
                    WHERE a.author_entity_ids LIKE ? AND a.source = ?
                """, (f'%[{entity_id}]%', platform))
                
                row = cur.fetchone()
                if row:
                    platform_activity[platform] = {
                        "artifact_count": row["count"] or 0,
                        "last_activity": row["last_activity"],
                        "active": (row["count"] or 0) > 0
                    }
            
            # Calculate activity scores
            total_artifacts = sum(p["artifact_count"] for p in platform_activity.values())
            
            for platform, activity in platform_activity.items():
                if total_artifacts > 0:
                    activity["activity_score"] = float(activity["artifact_count"] / total_artifacts)
                else:
                    activity["activity_score"] = 0.0
            
            # Determine primary platform
            primary_platform = max(platform_activity.keys(), 
                                 key=lambda p: platform_activity[p]["activity_score"]) if platform_activity else None
            
            # Cross-platform consistency
            active_platforms = [p for p, a in platform_activity.items() if a["active"]]
            cross_platform_score = len(active_platforms) / len(platform_activity) if platform_activity else 0
            
            return {
                "platforms": platform_activity,
                "primary_platform": primary_platform,
                "cross_platform_score": float(cross_platform_score),
                "active_platforms": active_platforms,
                "platform_diversity": float(len(active_platforms))
            }
        finally:
            conn.close()
    
    def identify_expertise_areas(self, entity_id: int) -> Dict[str, Any]:
        """
        Identify expertise areas based on topics and artifact content.
        """
        conn = connect(self.db_path)
        try:
            # Get all artifacts with topics for this entity
            cur = conn.execute("""
                SELECT 
                    at.topic_id,
                    t.name as topic_name,
                    t.taxonomy_path,
                    COUNT(*) as artifact_count,
                    AVG(s.discovery_score) as avg_score,
                    MAX(a.published_at) as last_activity
                FROM artifacts a
                JOIN artifact_topics at ON a.id = at.artifact_id
                JOIN topics t ON at.topic_id = t.id
                JOIN scores s ON a.id = s.artifact_id
                WHERE a.author_entity_ids LIKE ?
                GROUP BY at.topic_id, t.name, t.taxonomy_path
                ORDER BY artifact_count DESC, avg_score DESC
            """, (f'%{entity_id}%',))
            
            topic_expertise = [dict(row) for row in cur.fetchall()]
            
            if not topic_expertise:
                return {
                    "primary_expertise": [],
                    "secondary_expertise": [],
                    "taxonomy_coverage": [],
                    "expertise_score": 0.0,
                    "topic_diversity": 0.0,
                    "total_topics": 0
                }
            
            # Calculate expertise scores
            max_count = max(t["artifact_count"] for t in topic_expertise)
            
            for topic in topic_expertise:
                # Normalize by max count and incorporate quality (discovery score)
                normalized_count = topic["artifact_count"] / max_count if max_count > 0 else 0
                quality_factor = min((topic["avg_score"] or 0) / 100, 1.0)  # Normalize to 0-1
                topic["expertise_score"] = float((normalized_count * 0.7) + (quality_factor * 0.3))
            
            # Categorize expertise levels
            primary_threshold = 0.6
            secondary_threshold = 0.3
            
            primary_expertise = [t for t in topic_expertise if t["expertise_score"] >= primary_threshold][:5]
            secondary_expertise = [
                t
                for t in topic_expertise
                if secondary_threshold <= t["expertise_score"] < primary_threshold
            ][:10]
            
            # Analyze taxonomy coverage
            taxonomy_coverage: defaultdict[str, TaxonomyStats] = defaultdict(
                lambda: {"count": 0, "topics": []}
            )
            
            for topic in topic_expertise:
                taxonomy = topic["taxonomy_path"] or "uncategorized"
                base_category = taxonomy.split("/")[0] if "/" in taxonomy else taxonomy
                
                taxonomy_coverage[base_category]["count"] += topic["artifact_count"]
                taxonomy_coverage[base_category]["topics"].append(topic["topic_name"])
            
            taxonomy_list: list[TaxonomyEntry] = [
                {
                    "category": cat,
                    "artifact_count": stats["count"],
                    "topics": stats["topics"][:5]  # Top 5 topics per category
                }
                for cat, stats in taxonomy_coverage.items()
            ]
            
            # Sort by artifact count
            taxonomy_list.sort(key=lambda x: x["artifact_count"], reverse=True)
            
            # Calculate overall expertise score and diversity
            total_expertise_score = sum(t["expertise_score"] for t in topic_expertise)
            topic_diversity = len(topic_expertise) / max(len(taxonomy_coverage), 1)
            
            return {
                "primary_expertise": primary_expertise,
                "secondary_expertise": secondary_expertise,
                "taxonomy_coverage": taxonomy_list[:5],  # Top 5 categories
                "expertise_score": float(total_expertise_score),
                "topic_diversity": float(topic_diversity),
                "total_topics": len(topic_expertise)
            }
        finally:
            conn.close()
    
    def compute_influence_score(self, entity_id: int) -> float:
        """
        Compute overall influence score as a composite metric.
        """
        # Get all component metrics
        impact = self.compute_impact_metrics(entity_id)
        network = self.compute_collaboration_network(entity_id)
        trajectory = self.compute_research_trajectory(entity_id)
        platform = self.compute_platform_activity(entity_id)
        expertise = self.identify_expertise_areas(entity_id)
        
        # Weighted combination
        weights = {
            "impact": 0.30,
            "network": 0.20,
            "trajectory": 0.20,
            "platform": 0.15,
            "expertise": 0.15
        }
        
        # Normalize components to 0-100 scale
        impact_score = min((impact["total_impact"] / max(impact["total_artifacts"], 1)) * 10, 100)
        collaboration_component = (
            (network["total_collaborators"] / max(network["total_collaborations"], 1)) * 50
        )
        network_score = min(
            network["centrality"] * 100 + collaboration_component,
            100,
        )
        trajectory_score = min(len(trajectory["emerging_topics"]) * 20 + len(trajectory["timeline"]) * 2, 100)
        platform_score = min(platform["cross_platform_score"] * 100 + platform["platform_diversity"] * 20, 100)
        expertise_score = min(expertise["expertise_score"] * 10, 100)
        
        # Composite score
        influence_score = (
            weights["impact"] * impact_score +
            weights["network"] * network_score +
            weights["trajectory"] * trajectory_score +
            weights["platform"] * platform_score +
            weights["expertise"] * expertise_score
        )
        
        return float(min(influence_score, 100.0))
    
    def compute_full_profile(self, entity_id: int) -> Dict[str, Any]:
        """
        Compute complete researcher profile with all metrics.
        """
        # Get basic entity info
        conn = connect(self.db_path)
        try:
            cur = conn.execute(
                "SELECT name, type, description, homepage_url FROM entities WHERE id = ?",
                (entity_id,)
            )
            entity_row = cur.fetchone()
            
            if not entity_row:
                raise ValueError(f"Entity {entity_id} not found")
            
            # Compute all metrics
            impact_metrics = self.compute_impact_metrics(entity_id)
            collaboration_network = self.compute_collaboration_network(entity_id)
            research_trajectory = self.compute_research_trajectory(entity_id)
            platform_activity = self.compute_platform_activity(entity_id)
            expertise_areas = self.identify_expertise_areas(entity_id)
            influence_score = self.compute_influence_score(entity_id)
            
            # Get last activity date
            all_dates = []
            if research_trajectory["timeline"]:
                all_dates.extend([t["date"] for t in research_trajectory["timeline"]])
            
            last_activity_date = max(all_dates) if all_dates else None
            
            return {
                "entity_id": entity_id,
                "name": entity_row["name"],
                "type": entity_row["type"],
                "description": entity_row["description"],
                "homepage_url": entity_row["homepage_url"],
                "impact_metrics": impact_metrics,
                "collaboration_network": collaboration_network,
                "research_trajectory": research_trajectory,
                "platform_activity": platform_activity,
                "expertise_areas": expertise_areas,
                "influence_score": influence_score,
                "last_activity_date": last_activity_date,
                "computed_at": datetime.now(timezone.utc).isoformat()
            }
        finally:
            conn.close()
    
    def update_entity_profile(self, entity_id: int) -> bool:
        """
        Update the entity record with computed profile data.
        """
        profile = self.compute_full_profile(entity_id)
        
        conn = connect(self.db_path)
        try:
            with conn:
                conn.execute("""
                    UPDATE entities SET
                      impact_metrics = ?,
                      collaboration_network = ?,
                      research_trajectory = ?,
                      expertise_areas = ?,
                      influence_score = ?,
                      platform_activity = ?,
                      last_activity_date = ?,
                      updated_at = ?
                    WHERE id = ?
                """, (
                    json.dumps(profile["impact_metrics"]),
                    json.dumps(profile["collaboration_network"]),
                    json.dumps(profile["research_trajectory"]),
                    json.dumps(profile["expertise_areas"]),
                    profile["influence_score"],
                    json.dumps(profile["platform_activity"]),
                    profile["last_activity_date"],
                    profile["computed_at"],
                    entity_id
                ))
            
            log.info(f"Updated profile for entity {entity_id} ({profile['name']})")
            return True
        except sqlite3.Error as e:
            log.error(f"Failed to update profile for entity {entity_id}: {e}")
            return False
        finally:
            conn.close()


def run_researcher_analytics_pipeline(
    db_path: str, 
    settings: Settings, 
    entity_id: Optional[int] = None,
    batch_size: int = 100
) -> PipelineResults:
    """
    Run the researcher analytics pipeline for all entities or a specific entity.
    """
    analytics = ResearcherProfileAnalytics(db_path, settings)
    
    conn = connect(db_path)
    try:
        if entity_id:
            # Process single entity
            entity_ids = [entity_id]
        else:
            # Get all person entities
            cur = conn.execute("""
                SELECT id FROM entities 
                WHERE type = 'person'
                ORDER BY id
            """)
            entity_ids = [row["id"] for row in cur.fetchall()]
        
        results: PipelineResults = {
            "processed": 0,
            "successful": 0,
            "failed": 0,
            "entity_ids": []
        }
        
        # Process in batches
        for i in range(0, len(entity_ids), batch_size):
            batch = entity_ids[i:i + batch_size]
            
            for eid in batch:
                try:
                    success = analytics.update_entity_profile(eid)
                    if success:
                        results["successful"] += 1
                        results["entity_ids"].append(eid)
                    else:
                        results["failed"] += 1
                except Exception as e:
                    log.error(f"Error processing entity {eid}: {e}")
                    results["failed"] += 1
                
                results["processed"] += 1
            
            log.info(f"Processed batch {i//batch_size + 1}: {len(batch)} entities")
        
        return results
    finally:
        conn.close()
