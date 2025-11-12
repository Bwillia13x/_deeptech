"""Identity resolution integration for Phase 2 pipeline."""

from __future__ import annotations

from typing import Any, Dict

from .config import Settings
from .db import (
    list_all_entities,
)
from .identity_resolution import (
    compute_affiliation_similarity,
    compute_name_similarity,
    confirm_entity_link_with_llm,
    find_candidate_matches,
    merge_entities,
)
from .llm_client import get_async_llm_client
from .logger import get_logger

log = get_logger(__name__)


class IdentityResolutionConfig:
    """Configuration for identity resolution pipeline."""
    
    def __init__(self, settings_or_config):  # type: ignore[no-untyped-def]
        """
        Initialize from either Settings object or IdentityResolutionConfig object.
        """
        # Handle both Settings and direct config object
        if hasattr(settings_or_config, 'app'):
            # It's a Settings object
            settings = settings_or_config
            identity_config = getattr(settings.app, 'identity_resolution', {})
            # If it's a Pydantic model, convert to dict
            if hasattr(identity_config, '__dict__'):
                identity_config = identity_config.__dict__
        else:
            # It's already a config dict or object
            identity_config = getattr(settings_or_config, '__dict__', settings_or_config)
        
        # Ensure we have a dict
        if not isinstance(identity_config, dict):
            identity_config = {}
        
        self.enabled = identity_config.get("enabled", True)
        self.similarity_threshold = identity_config.get("similarity_threshold", 0.75)
        self.auto_link_threshold = identity_config.get("auto_link_threshold", 0.90)
        self.manual_review_threshold = identity_config.get("manual_review_threshold", 0.70)
        self.reject_threshold = identity_config.get("reject_threshold", 0.70)
        
        # Weights for comprehensive similarity
        weights = identity_config.get("weights", {})
        self.name_weight = weights.get("name", 0.40)
        self.affiliation_weight = weights.get("affiliation", 0.25)
        self.domain_weight = weights.get("domain", 0.15)
        self.co_mention_weight = weights.get("co_mention", 0.10)
        self.content_weight = weights.get("content", 0.10)
        
        # Conservative linking for common names
        self.common_names = set(identity_config.get("common_names", []))
        self.institution_blacklist = set(identity_config.get("institution_blacklist", []))


def compute_comprehensive_similarity(
    entity1: Dict[str, Any],
    entity2: Dict[str, Any],
    config: IdentityResolutionConfig
) -> float:
    """
    Compute comprehensive similarity between two entities using multiple signals.
    
    Returns a weighted similarity score (0-1).
    """
    scores = {}
    weights = {}
    
    # Name similarity (highest weight)
    name_sim = compute_name_similarity(entity1["name"], entity2["name"])
    scores["name"] = name_sim
    weights["name"] = config.name_weight
    
    # Affiliation similarity (if available)
    if entity1.get("description") and entity2.get("description"):
        aff_sim = compute_affiliation_similarity(
            entity1["description"],
            entity2["description"]
        )
        scores["affiliation"] = aff_sim
        weights["affiliation"] = config.affiliation_weight
    
    # Domain similarity (from URLs/homepage)
    domain_sim = compute_domain_similarity(entity1, entity2)
    if domain_sim > 0:
        scores["domain"] = domain_sim
        weights["domain"] = config.domain_weight
    
    # Co-mention similarity (entities mentioned together)
    co_mention_sim = compute_co_mention_similarity(entity1, entity2)
    if co_mention_sim > 0:
        scores["co_mention"] = co_mention_sim
        weights["co_mention"] = config.co_mention_weight
    
    # Weighted average
    total_weight = sum(weights.values())
    if total_weight == 0:
        return 0.0
    
    weighted_sum = sum(scores[k] * weights[k] for k in scores)
    return weighted_sum / total_weight


def compute_domain_similarity(entity1: Dict[str, Any], entity2: Dict[str, Any]) -> float:
    """Compute similarity based on domain names in URLs."""
    import re
    
    def extract_domains(entity):  # type: ignore[no-untyped-def]
        domains = []
        if entity.get("homepage_url"):
            match = re.search(r'https?://([^/]+)', entity["homepage_url"])
            if match:
                domains.append(match.group(1))
        
        # Also check accounts for domain info
        for account in entity.get("accounts", []):
            url = account.get("url", "")
            if url:
                match = re.search(r'https?://([^/]+)', url)
                if match:
                    domains.append(match.group(1))
        
        return domains
    
    domains1 = extract_domains(entity1)
    domains2 = extract_domains(entity2)
    
    if not domains1 or not domains2:
        return 0.0
    
    # Compute Jaccard similarity of domain sets
    set1 = set(domains1)
    set2 = set(domains2)
    
    intersection = set1.intersection(set2)
    union = set1.union(set2)
    
    if not union:
        return 0.0
    
    return len(intersection) / len(union)


def compute_co_mention_similarity(entity1: Dict[str, Any], entity2: Dict[str, Any]) -> float:
    """
    Compute similarity based on how often entities are mentioned together.
    
    This looks at artifacts where both entities are co-authors or co-mentioned.
    """
    # In a real implementation, we would query the database to find:
    # 1. Artifacts where both entities are authors
    # 2. Artifacts where both entities are mentioned in text
    # 3. Compute overlap metrics
    
    # For now, return 0 as this requires more sophisticated analysis
    # This would be implemented with artifact co-occurrence analysis
    return 0.0


def should_apply_conservative_linking(entity: Dict[str, Any], config: IdentityResolutionConfig) -> bool:
    """
    Determine if conservative linking should be applied for this entity.
    
    Conservative linking is used for:
    1. Common names (John, Michael, etc.)
    2. Ambiguous institutions
    3. Very short names
    """
    name = entity["name"].lower()
    
    # Check for common names
    first_name = name.split()[0] if name.split() else ""
    if first_name in config.common_names:
        return True
    
    # Check for ambiguous institutions
    for blacklist_term in config.institution_blacklist:
        if blacklist_term.lower() in name:
            return True
    
    # Very short names are ambiguous
    if len(name.strip()) < 5:
        return True
    
    return False


def create_merge_review(
    db_path: str,
    primary_entity: Dict[str, Any],
    duplicate_entity: Dict[str, Any],
    similarity: float,
    reason: str
) -> int:
    """
    Create a review queue entry for manual review of entity merge.
    
    Returns the review ID.
    """
    import sqlite3

    from .utils import utc_now_iso
    
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            cur = conn.execute(
                """
                INSERT INTO entity_merge_reviews (
                    primary_entity_id,
                    duplicate_entity_id,
                    similarity_score,
                    reason,
                    status,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    primary_entity["id"],
                    duplicate_entity["id"],
                    similarity,
                    reason,
                    "pending",  # pending, approved, rejected
                    utc_now_iso()
                )
            )
            rowid = cur.lastrowid
            if rowid is None:
                raise RuntimeError("Failed to create merge review")
            return rowid
    finally:
        conn.close()


async def process_entity_batch(
    entities: list[Dict[str, Any]],
    all_entities: list[Dict[str, Any]],
    config: IdentityResolutionConfig,
    llm_client: Any,
    db_path: str
) -> Dict[str, int]:
    """Process a batch of entities for identity resolution."""
    processed = 0
    merged = 0
    review_created = 0
    
    for entity in entities:
        processed += 1
        
        # Skip if conservative linking applies (will be handled separately)
        if should_apply_conservative_linking(entity, config):
            log.debug("Skipping entity '%s' for conservative linking batch", entity["name"])
            continue
        
        # Find candidate matches
        candidates = find_candidate_matches(
            entity,
            all_entities,
            config.similarity_threshold
        )
        
        if not candidates:
            continue
        
        log.info("Entity '%s' has %d candidate matches", entity["name"], len(candidates))
        
        # Process each candidate
        for candidate, similarity in candidates:
            # Compute comprehensive similarity
            comp_similarity = compute_comprehensive_similarity(
                entity,
                candidate,
                config
            )
            
            # Decision based on similarity and configuration
            if comp_similarity >= config.auto_link_threshold:
                # Auto-merge
                log.info("Auto-merging entities: %s <-> %s (%.2f)",
                        entity["name"], candidate["name"], comp_similarity)
                
                if merge_entities(db_path, entity["id"], candidate["id"]):
                    merged += 1
                    # Remove duplicate from processing list
                    all_entities = [e for e in all_entities if e["id"] != candidate["id"]]
                    
            elif comp_similarity >= config.manual_review_threshold:
                # Create review queue entry
                if llm_client:
                    # Get LLM reasoning
                    is_same, reasoning = await confirm_entity_link_with_llm(
                        entity, candidate, comp_similarity, llm_client
                    )
                    
                    if is_same:
                        # LLM confirms, proceed with merge
                        if merge_entities(db_path, entity["id"], candidate["id"]):
                            merged += 1
                            all_entities = [e for e in all_entities if e["id"] != candidate["id"]]
                    else:
                        # Create review with LLM reasoning
                        review_id = create_merge_review(
                            db_path, entity, candidate, comp_similarity, reasoning
                        )
                        review_created += 1
                        log.info("Created merge review %d for entities '%s' <-> '%s'",
                               review_id, entity["name"], candidate["name"])
                else:
                    # No LLM, create review with similarity reason
                    reason = f"Similarity score: {comp_similarity:.2f}"
                    review_id = create_merge_review(
                        db_path, entity, candidate, comp_similarity, reason
                    )
                    review_created += 1
            else:
                # Below threshold, reject
                log.debug("Rejecting candidate '%s' for entity '%s' (similarity: %.2f)",
                         candidate["name"], entity["name"], comp_similarity)
    
    return {
        "processed": processed,
        "merged": merged,
        "review_created": review_created
    }


async def run_identity_resolution_pipeline(
    db_path: str,
    settings: Settings,
    batch_size: int = 100,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Run identity resolution as part of the main pipeline.
    
    Args:
        db_path: Database path
        settings: Application settings
        batch_size: Number of entities to process in each batch
        dry_run: If True, only log what would be done without making changes
    
    Returns:
        Dictionary with processing statistics
    """
    if not settings.app.identity_resolution.enabled:
        log.info("Identity resolution disabled in configuration")
        return {"status": "disabled", "processed": 0, "merged": 0}
    
    config = IdentityResolutionConfig(settings)
    
    # Get LLM client if available
    llm_client = None
    if settings.app.llm.provider != "dummy":
        try:
            llm_client = get_async_llm_client(
                settings.app.llm.provider,
                settings.app.llm.model,
                settings.app.llm.temperature
            )
            log.info("LLM client initialized for identity resolution")
        except Exception as e:
            log.warning("Could not initialize LLM client: %s", e)
    
    # Get all entities
    all_entities = list_all_entities(db_path)
    log.info("Found %d entities for identity resolution", len(all_entities))
    
    if not all_entities:
        return {"status": "no_entities", "processed": 0, "merged": 0}
    
    if dry_run:
        log.info("DRY RUN: Would process %d entities", len(all_entities))
        return {"status": "dry_run", "entities_found": len(all_entities)}
    
    # Process in batches
    total_stats = {
        "processed": 0,
        "merged": 0,
        "review_created": 0,
        "batches": 0
    }
    
    for i in range(0, len(all_entities), batch_size):
        batch = all_entities[i:i + batch_size]
        
        log.info("Processing batch %d/%d (%d entities)",
                total_stats["batches"] + 1,
                (len(all_entities) + batch_size - 1) // batch_size,
                len(batch))
        
        batch_stats = await process_entity_batch(
            batch,
            all_entities,
            config,
            llm_client,
            db_path
        )
        
        total_stats["processed"] += batch_stats["processed"]
        total_stats["merged"] += batch_stats["merged"]
        total_stats["review_created"] += batch_stats["review_created"]
        total_stats["batches"] += 1
        
        log.info("Batch complete: processed=%d, merged=%d, reviews=%d",
                batch_stats["processed"],
                batch_stats["merged"],
                batch_stats["review_created"])
    
    log.info("Identity resolution pipeline complete: %s", total_stats)
    
    return {
        "status": "completed",
        **total_stats
    }


# Database helper for merge reviews
MERGE_REVIEWS_TABLE = """
CREATE TABLE IF NOT EXISTS entity_merge_reviews (
    id INTEGER PRIMARY KEY,
    primary_entity_id INTEGER NOT NULL,
    duplicate_entity_id INTEGER NOT NULL,
    similarity_score REAL NOT NULL,
    reason TEXT,
    status TEXT NOT NULL,           -- pending, approved, rejected
    reviewer TEXT,                  -- who reviewed it
    reviewed_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(primary_entity_id) REFERENCES entities(id),
    FOREIGN KEY(duplicate_entity_id) REFERENCES entities(id)
);

CREATE INDEX IF NOT EXISTS idx_merge_reviews_status ON entity_merge_reviews(status);
CREATE INDEX IF NOT EXISTS idx_merge_reviews_created ON entity_merge_reviews(created_at);
"""


def init_merge_reviews_table(db_path: str) -> None:
    """Initialize the merge reviews table."""
    from .db import connect
    
    conn = connect(db_path)
    try:
        with conn:
            conn.executescript(MERGE_REVIEWS_TABLE)
        log.info("Initialized entity_merge_reviews table")
    finally:
        conn.close()
