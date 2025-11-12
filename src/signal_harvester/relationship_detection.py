"""Cross-source corroboration: Detect and score relationships between artifacts."""

from __future__ import annotations

import re
from typing import Any

import numpy as np

from .db import (
    create_artifact_relationship,
    get_artifact_relationships,
    list_artifacts_for_scoring,
)
from .embeddings import get_artifact_embedding
from .logger import get_logger

log = get_logger(__name__)

# Relationship types
RELATIONSHIP_TYPES = {
    "cite": "Paper cites another paper",
    "reference": "Tweet/post mentions paper/repo",
    "discuss": "Multiple artifacts about same breakthrough",
    "implement": "Code implements research paper",
    "mention": "Generic mention or link",
    "related": "Semantically related artifacts",
}

# Regular expressions for extracting identifiers
ARXIV_ID_PATTERN = re.compile(r"(?:arxiv[:\s/]*|abs/)(\d{4}\.\d{4,5})", re.IGNORECASE)
DOI_PATTERN = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
GITHUB_URL_PATTERN = re.compile(r"github\.com/([a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+)", re.IGNORECASE)


def extract_arxiv_ids(text: str) -> list[str]:
    """Extract arXiv IDs from text.
    
    Args:
        text: Text to search
        
    Returns:
        List of arXiv IDs (e.g., ['2301.12345', '2302.98765'])
    """
    if not text:
        return []
    
    matches = ARXIV_ID_PATTERN.findall(text)
    # Normalize to YYYY.NNNNN format
    return [match for match in matches if match]


def extract_dois(text: str) -> list[str]:
    """Extract DOIs from text.
    
    Args:
        text: Text to search
        
    Returns:
        List of DOIs
    """
    if not text:
        return []
    
    matches = DOI_PATTERN.findall(text)
    return [match.lower() for match in matches]


def extract_github_repos(text: str) -> list[str]:
    """Extract GitHub repository identifiers from text.
    
    Args:
        text: Text to search
        
    Returns:
        List of repo paths (e.g., ['openai/gpt-4', 'pytorch/pytorch'])
    """
    if not text:
        return []
    
    matches = GITHUB_URL_PATTERN.findall(text)
    # Remove trailing slashes and normalize
    return [match.rstrip("/") for match in matches]


def compute_semantic_similarity(
    artifact1: dict[str, Any],
    artifact2: dict[str, Any],
) -> float:
    """Compute semantic similarity between two artifacts using embeddings.
    
    Args:
        artifact1: First artifact dictionary
        artifact2: Second artifact dictionary
        
    Returns:
        Similarity score 0.0-1.0
    """
    try:
        # Get embeddings for both artifacts
        text1 = f"{artifact1.get('title', '')} {artifact1.get('text', '')}"
        text2 = f"{artifact2.get('title', '')} {artifact2.get('text', '')}"
        
        if not text1.strip() or not text2.strip():
            return 0.0
        
        emb1 = get_artifact_embedding(text1)
        emb2 = get_artifact_embedding(text2)
        
        # Cosine similarity (embeddings are already normalized)
        similarity = float(np.dot(emb1, emb2))
        
        # Clamp to [0, 1] and handle edge cases
        return max(0.0, min(1.0, (similarity + 1.0) / 2.0))  # Map [-1, 1] to [0, 1]
        
    except Exception as e:
        log.error(f"Error computing semantic similarity: {e}")
        return 0.0


def detect_citation_relationships(
    db_path: str,
    source_artifact: dict[str, Any],
) -> list[dict[str, Any]]:
    """Detect citation relationships for a source artifact.
    
    Looks for arXiv IDs, DOIs, and GitHub repos mentioned in the text.
    
    Args:
        db_path: Path to SQLite database
        source_artifact: Source artifact to analyze
        
    Returns:
        List of detected relationships with metadata
    """
    relationships = []
    
    # Extract text content
    text = f"{source_artifact.get('title', '')} {source_artifact.get('text', '')} {source_artifact.get('url', '')}"
    
    # Extract identifiers
    arxiv_ids = extract_arxiv_ids(text)
    github_repos = extract_github_repos(text)
    
    # Find matching artifacts in database
    artifacts = list_artifacts_for_scoring(db_path)
    
    for artifact in artifacts:
        if artifact["id"] == source_artifact["id"]:
            continue  # Skip self-references
        
        confidence = 0.0
        detection_method = None
        metadata: dict[str, Any] = {}
        
        # Check arXiv ID matches
        if artifact["source"] == "arxiv":
            artifact_arxiv_id = artifact.get("source_id", "")
            for arxiv_id in arxiv_ids:
                if arxiv_id in artifact_arxiv_id:
                    confidence = 0.95
                    detection_method = "arxiv_id_match"
                    metadata["arxiv_id"] = arxiv_id
                    break
        
        # Check GitHub repo matches
        if artifact["source"] == "github":
            artifact_url = artifact.get("url", "")
            for repo in github_repos:
                if repo in artifact_url:
                    confidence = 0.90
                    detection_method = "github_url_match"
                    metadata["github_repo"] = repo
                    break
        
        # Determine relationship type
        if confidence > 0.0:
            source_type = source_artifact.get("source", "")
            target_type = artifact.get("source", "")
            
            # Tweet/post referencing paper/repo
            if source_type == "x" and target_type in ["arxiv", "github"]:
                relationship_type = "reference"
            # GitHub repo implementing arXiv paper
            elif source_type == "github" and target_type == "arxiv":
                relationship_type = "implement"
            # Paper citing paper
            elif source_type == "arxiv" and target_type == "arxiv":
                relationship_type = "cite"
            else:
                relationship_type = "mention"
            
            relationships.append({
                "target_artifact_id": artifact["id"],
                "relationship_type": relationship_type,
                "confidence": confidence,
                "detection_method": detection_method,
                "metadata": metadata,
            })
    
    return relationships


def detect_semantic_relationships(
    db_path: str,
    source_artifact: dict[str, Any],
    min_similarity: float = 0.80,
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """Detect semantic relationships using embedding similarity.
    
    Finds artifacts that are semantically similar but from different sources.
    
    Args:
        db_path: Path to SQLite database
        source_artifact: Source artifact to analyze
        min_similarity: Minimum similarity threshold (0.0-1.0)
        max_results: Maximum number of relationships to return
        
    Returns:
        List of detected relationships with metadata
    """
    relationships = []
    
    # Get all artifacts
    artifacts = list_artifacts_for_scoring(db_path)
    
    # Filter to different sources only
    source_source = source_artifact.get("source", "")
    candidates = [
        a for a in artifacts
        if a["id"] != source_artifact["id"] and a.get("source") != source_source
    ]
    
    if not candidates:
        return []
    
    # Compute similarities in batch for efficiency
    similarities = []
    for artifact in candidates:
        similarity = compute_semantic_similarity(source_artifact, artifact)
        if similarity >= min_similarity:
            similarities.append((artifact, similarity))
    
    # Sort by similarity and take top N
    similarities.sort(key=lambda x: x[1], reverse=True)
    top_matches = similarities[:max_results]
    
    for artifact, similarity in top_matches:
        # Determine relationship type based on sources
        source_type = source_artifact.get("source", "")
        target_type = artifact.get("source", "")
        
        if source_type == "x" and target_type in ["arxiv", "github"]:
            relationship_type = "discuss"
        elif source_type == "github" and target_type == "arxiv":
            relationship_type = "implement"
        elif source_type == "arxiv" and target_type == "github":
            relationship_type = "related"
        else:
            relationship_type = "related"
        
        relationships.append({
            "target_artifact_id": artifact["id"],
            "relationship_type": relationship_type,
            "confidence": similarity,
            "detection_method": "semantic_similarity",
            "metadata": {"similarity_score": float(similarity)},
        })
    
    return relationships


def run_relationship_detection(
    db_path: str,
    artifact_id: int | None = None,
    enable_semantic: bool = True,
    semantic_threshold: float = 0.80,
) -> dict[str, Any]:
    """Run relationship detection for artifacts.
    
    Args:
        db_path: Path to SQLite database
        artifact_id: Specific artifact ID to process, or None for all
        enable_semantic: Whether to run semantic similarity detection
        semantic_threshold: Minimum similarity for semantic relationships
        
    Returns:
        Statistics about detected relationships
    """
    log.info("Starting relationship detection (semantic=%s, threshold=%.2f)", enable_semantic, semantic_threshold)
    
    # Get artifacts to process
    artifacts = list_artifacts_for_scoring(db_path)
    
    if artifact_id:
        artifacts = [a for a in artifacts if a["id"] == artifact_id]
    
    if not artifacts:
        log.warning("No artifacts found for relationship detection")
        return {"processed": 0, "relationships_created": 0}
    
    stats = {
        "processed": 0,
        "relationships_created": 0,
        "by_type": {},
        "by_method": {},
    }
    
    for artifact in artifacts:
        stats["processed"] += 1
        
        # Detect citation relationships (always enabled)
        citation_rels = detect_citation_relationships(db_path, artifact)
        
        for rel in citation_rels:
            rel_id = create_artifact_relationship(
                db_path=db_path,
                source_artifact_id=artifact["id"],
                target_artifact_id=rel["target_artifact_id"],
                relationship_type=rel["relationship_type"],
                confidence=rel["confidence"],
                detection_method=rel["detection_method"],
                metadata=rel["metadata"],
            )
            
            if rel_id:
                stats["relationships_created"] += 1
                stats["by_type"][rel["relationship_type"]] = stats["by_type"].get(rel["relationship_type"], 0) + 1
                stats["by_method"][rel["detection_method"]] = stats["by_method"].get(rel["detection_method"], 0) + 1
        
        # Detect semantic relationships (if enabled)
        if enable_semantic:
            semantic_rels = detect_semantic_relationships(
                db_path=db_path,
                source_artifact=artifact,
                min_similarity=semantic_threshold,
            )
            
            for rel in semantic_rels:
                rel_id = create_artifact_relationship(
                    db_path=db_path,
                    source_artifact_id=artifact["id"],
                    target_artifact_id=rel["target_artifact_id"],
                    relationship_type=rel["relationship_type"],
                    confidence=rel["confidence"],
                    detection_method=rel["detection_method"],
                    metadata=rel["metadata"],
                )
                
                if rel_id:
                    stats["relationships_created"] += 1
                    stats["by_type"][rel["relationship_type"]] = stats["by_type"].get(rel["relationship_type"], 0) + 1
                    stats["by_method"][rel["detection_method"]] = stats["by_method"].get(rel["detection_method"], 0) + 1
        
        if stats["processed"] % 10 == 0:
            log.info(
                "Processed %d artifacts, created %d relationships",
                stats["processed"],
                stats["relationships_created"],
            )
    
    log.info("Relationship detection complete: %s", stats)
    return stats


def get_citation_graph(
    db_path: str,
    artifact_id: int,
    depth: int = 2,
    min_confidence: float = 0.5,
) -> dict[str, Any]:
    """Get citation graph for an artifact with configurable depth.
    
    Args:
        db_path: Path to SQLite database
        artifact_id: Root artifact ID
        depth: Graph traversal depth (1-3)
        min_confidence: Minimum confidence threshold
        
    Returns:
        Citation graph with nodes and edges
    """
    nodes = {}
    edges = []
    visited = set()
    
    def traverse(current_id: int, current_depth: int) -> None:
        if current_depth > depth or current_id in visited:
            return
        
        visited.add(current_id)
        
        # Get relationships
        relationships = get_artifact_relationships(
            db_path=db_path,
            artifact_id=current_id,
            direction="both",
            min_confidence=min_confidence,
        )
        
        for rel in relationships:
            source_id = rel["source_artifact_id"]
            target_id = rel["target_artifact_id"]
            
            # Add to nodes if not present
            if source_id not in nodes:
                nodes[source_id] = {
                    "id": source_id,
                    "title": rel.get("source_title", ""),
                    "source": rel.get("source_source", ""),
                    "type": rel.get("source_type", ""),
                }
            
            if target_id not in nodes:
                nodes[target_id] = {
                    "id": target_id,
                    "title": rel.get("target_title", ""),
                    "source": rel.get("target_source", ""),
                    "type": rel.get("target_type", ""),
                }
            
            # Add edge
            edges.append({
                "source": source_id,
                "target": target_id,
                "relationship_type": rel["relationship_type"],
                "confidence": rel["confidence"],
                "detection_method": rel.get("detection_method", ""),
            })
            
            # Recurse to next depth
            if current_id == source_id:
                traverse(target_id, current_depth + 1)
            else:
                traverse(source_id, current_depth + 1)
    
    # Start traversal
    traverse(artifact_id, 0)
    
    return {
        "root_artifact_id": artifact_id,
        "depth": depth,
        "min_confidence": min_confidence,
        "nodes": list(nodes.values()),
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }
