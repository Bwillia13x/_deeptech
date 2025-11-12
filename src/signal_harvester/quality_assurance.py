"""Quality Assurance System for Signal Harvester.

Phase 2.4: Automated validation rules, quality scoring, audit trails, and review queues.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from .config import Settings, load_settings
from .logger import get_logger
from .utils import utc_now_iso

log = get_logger(__name__)


class ValidationSeverity(Enum):
    """Severity levels for validation issues."""
    
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ReviewStatus(Enum):
    """Status of review queue items."""
    
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"


@dataclass
class ValidationRule:
    """Definition of a validation rule."""
    
    rule_id: str
    name: str
    description: str
    severity: ValidationSeverity
    check_type: str  # "artifact", "entity", "topic", "score"
    condition_sql: str  # SQL WHERE clause that identifies violations
    fix_sql: Optional[str] = None  # Optional SQL to auto-fix issues
    enabled: bool = True


@dataclass
class QualityScore:
    """Quality score for an artifact, entity, or topic."""
    
    target_type: str  # "artifact", "entity", "topic"
    target_id: int
    overall_score: float  # 0-100
    component_scores: Dict[str, float]
    validation_issues: List[Dict[str, Any]]
    computed_at: str
    last_reviewed_at: Optional[str] = None
    reviewer: Optional[str] = None


@dataclass
class AuditEvent:
    """Audit trail event."""
    
    event_type: str  # "create", "update", "delete", "review", "merge", "score"
    entity_type: str  # "artifact", "entity", "topic", "account", "score"
    entity_id: int
    user_id: Optional[str]  # None for system actions
    old_values: Optional[Dict[str, Any]]
    new_values: Dict[str, Any]
    timestamp: str
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class QualityAssuranceEngine:
    """Main quality assurance engine."""
    
    def __init__(self, db_path: str, settings: Settings | None = None):
        self.db_path = db_path
        self.settings = settings or load_settings()
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize quality assurance database tables."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        try:
            with conn:
                # Validation rules table
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS validation_rules (
                        rule_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        description TEXT,
                        severity TEXT NOT NULL,
                        check_type TEXT NOT NULL,
                        condition_sql TEXT NOT NULL,
                        fix_sql TEXT,
                        enabled INTEGER DEFAULT 1,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                    );
                    """
                )
                conn.execute(
                    (
                        "CREATE INDEX IF NOT EXISTS idx_validation_rules_type "
                        "ON validation_rules(check_type);"
                    )
                )
                conn.execute(
                    (
                        "CREATE INDEX IF NOT EXISTS idx_validation_rules_enabled "
                        "ON validation_rules(enabled);"
                    )
                )
                
                # Validation issues table
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS validation_issues (
                        id INTEGER PRIMARY KEY,
                        rule_id TEXT NOT NULL,
                        target_type TEXT NOT NULL,
                        target_id INTEGER NOT NULL,
                        issue_details TEXT,
                        status TEXT DEFAULT 'open',
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        resolved_at TEXT,
                        resolved_by TEXT,
                        FOREIGN KEY(rule_id) REFERENCES validation_rules(rule_id),
                        UNIQUE(rule_id, target_type, target_id)
                    );
                    """
                )
                conn.execute(
                    (
                        "CREATE INDEX IF NOT EXISTS idx_validation_issues_target "
                        "ON validation_issues(target_type, target_id);"
                    )
                )
                conn.execute(
                    (
                        "CREATE INDEX IF NOT EXISTS idx_validation_issues_status "
                        "ON validation_issues(status);"
                    )
                )
                conn.execute(
                    (
                        "CREATE INDEX IF NOT EXISTS idx_validation_issues_rule "
                        "ON validation_issues(rule_id);"
                    )
                )
                
                # Quality scores table
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS quality_scores (
                        target_type TEXT NOT NULL,
                        target_id INTEGER NOT NULL,
                        overall_score REAL NOT NULL,
                        component_scores TEXT NOT NULL,
                        validation_issue_count INTEGER DEFAULT 0,
                        computed_at TEXT NOT NULL,
                        last_reviewed_at TEXT,
                        reviewer TEXT,
                        PRIMARY KEY(target_type, target_id)
                    );
                    """
                )
                conn.execute(
                    (
                        "CREATE INDEX IF NOT EXISTS idx_quality_scores_overall "
                        "ON quality_scores(overall_score);"
                    )
                )
                conn.execute(
                    (
                        "CREATE INDEX IF NOT EXISTS idx_quality_scores_computed "
                        "ON quality_scores(computed_at);"
                    )
                )
                
                # Audit trail table
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS audit_trail (
                        id INTEGER PRIMARY KEY,
                        event_type TEXT NOT NULL,
                        entity_type TEXT NOT NULL,
                        entity_id INTEGER NOT NULL,
                        user_id TEXT,
                        old_values TEXT,
                        new_values TEXT NOT NULL,
                        timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                        ip_address TEXT,
                        user_agent TEXT
                    );
                    """
                )
                conn.execute(
                    (
                        "CREATE INDEX IF NOT EXISTS idx_audit_trail_entity "
                        "ON audit_trail(entity_type, entity_id);"
                    )
                )
                conn.execute(
                    (
                        "CREATE INDEX IF NOT EXISTS idx_audit_trail_event "
                        "ON audit_trail(event_type);"
                    )
                )
                conn.execute(
                    (
                        "CREATE INDEX IF NOT EXISTS idx_audit_trail_timestamp "
                        "ON audit_trail(timestamp);"
                    )
                )
                
                # Review queue table
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS review_queue (
                        id INTEGER PRIMARY KEY,
                        item_type TEXT NOT NULL,
                        item_id INTEGER NOT NULL,
                        review_type TEXT NOT NULL,
                        priority INTEGER DEFAULT 0,
                        status TEXT DEFAULT 'pending',
                        assigned_to TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        due_at TEXT,
                        reviewed_at TEXT,
                        reviewer TEXT,
                        review_notes TEXT,
                        decision TEXT,
                        UNIQUE(item_type, item_id, review_type)
                    );
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_review_queue_status ON review_queue(status);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_review_queue_assigned ON review_queue(assigned_to);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_review_queue_priority ON review_queue(priority DESC);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_review_queue_due ON review_queue(due_at);"
                )
                
                # Data quality metrics table
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS data_quality_metrics (
                        metric_name TEXT PRIMARY KEY,
                        metric_value REAL,
                        metric_description TEXT,
                        computed_at TEXT DEFAULT CURRENT_TIMESTAMP
                    );
                    """
                )
                
                log.info("Quality assurance database tables initialized")
        finally:
            conn.close()
    
    def register_default_rules(self) -> None:
        """Register default validation rules."""
        default_rules = [
            # Artifact validation rules
            ValidationRule(
                rule_id="artifact_missing_text",
                name="Artifact Missing Text",
                description="Artifact has no text content",
                severity=ValidationSeverity.ERROR,
                check_type="artifact",
                condition_sql="text IS NULL OR TRIM(text) = ''",
            ),
            ValidationRule(
                rule_id="artifact_missing_title",
                name="Artifact Missing Title",
                description="Artifact has no title",
                severity=ValidationSeverity.WARNING,
                check_type="artifact",
                condition_sql="title IS NULL OR TRIM(title) = ''",
            ),
            ValidationRule(
                rule_id="artifact_future_date",
                name="Artifact Future Date",
                description="Artifact has a future publication date",
                severity=ValidationSeverity.ERROR,
                check_type="artifact",
                condition_sql="published_at > datetime('now')",
            ),
            ValidationRule(
                rule_id="artifact_old_date",
                name="Artifact Very Old Date",
                description="Artifact is older than 2 years",
                severity=ValidationSeverity.INFO,
                check_type="artifact",
                condition_sql="published_at < datetime('now', '-2 years')",
            ),
            ValidationRule(
                rule_id="artifact_no_entities",
                name="Artifact No Entities",
                description="Artifact has no linked entities",
                severity=ValidationSeverity.WARNING,
                check_type="artifact",
                condition_sql="author_entity_ids IS NULL OR author_entity_ids = '[]'",
            ),
            
            # Entity validation rules
            ValidationRule(
                rule_id="entity_missing_name",
                name="Entity Missing Name",
                description="Entity has no name",
                severity=ValidationSeverity.CRITICAL,
                check_type="entity",
                condition_sql="name IS NULL OR TRIM(name) = ''",
            ),
            ValidationRule(
                rule_id="entity_no_accounts",
                name="Entity No Accounts",
                description="Entity has no linked accounts",
                severity=ValidationSeverity.WARNING,
                check_type="entity",
                condition_sql="id NOT IN (SELECT DISTINCT entity_id FROM accounts)",
            ),
            ValidationRule(
                rule_id="entity_duplicate_name",
                name="Entity Duplicate Name",
                description="Multiple entities have the same name",
                severity=ValidationSeverity.WARNING,
                check_type="entity",
                condition_sql="""id IN (
                    SELECT e1.id FROM entities e1 
                    JOIN entities e2 ON e1.name = e2.name AND e1.id < e2.id
                )""",
            ),
            
            # Score validation rules
            ValidationRule(
                rule_id="score_out_of_range",
                name="Score Out of Range",
                description="Discovery score is outside valid range (0-100)",
                severity=ValidationSeverity.ERROR,
                check_type="score",
                condition_sql="discovery_score < 0 OR discovery_score > 100",
            ),
            ValidationRule(
                rule_id="score_missing_components",
                name="Score Missing Components",
                description="Score is missing component values",
                severity=ValidationSeverity.WARNING,
                check_type="score",
                condition_sql="novelty IS NULL OR emergence IS NULL OR obscurity IS NULL",
            ),
            
            # Topic validation rules
            ValidationRule(
                rule_id="topic_missing_name",
                name="Topic Missing Name",
                description="Topic has no name",
                severity=ValidationSeverity.CRITICAL,
                check_type="topic",
                condition_sql="name IS NULL OR TRIM(name) = ''",
            ),
            ValidationRule(
                rule_id="topic_no_artifacts",
                name="Topic No Artifacts",
                description="Topic has no linked artifacts",
                severity=ValidationSeverity.INFO,
                check_type="topic",
                condition_sql="id NOT IN (SELECT DISTINCT topic_id FROM artifact_topics)",
            ),
        ]
        
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        try:
            with conn:
                for rule in default_rules:
                    conn.execute(
                        (
                            "INSERT OR REPLACE INTO validation_rules "
                            "(rule_id, name, description, severity, check_type, condition_sql, "
                            "fix_sql, enabled, created_at, updated_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);"
                        ),
                        (
                            rule.rule_id,
                            rule.name,
                            rule.description,
                            rule.severity.value,
                            rule.check_type,
                            rule.condition_sql,
                            rule.fix_sql,
                            int(rule.enabled),
                        ),
                    )
            log.info("Registered %d default validation rules", len(default_rules))
        finally:
            conn.close()
    
    def run_validation(self, check_type: str, target_id: int | None = None) -> List[Dict[str, Any]]:
        """Run validation rules for a specific type and optional target."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        try:
            with conn:
                # Get enabled rules for the check type
                rules = conn.execute(
                    """
                    SELECT rule_id, name, description, severity, check_type, condition_sql
                    FROM validation_rules 
                    WHERE check_type = ? AND enabled = 1;
                    """,
                    (check_type,),
                ).fetchall()
                
                issues = []
                
                for rule in rules:
                    # Build query to find violations
                    if check_type == "artifact":
                        base_table = "artifacts"
                        id_column = "id"
                    elif check_type == "entity":
                        base_table = "entities"
                        id_column = "id"
                    elif check_type == "topic":
                        base_table = "topics"
                        id_column = "id"
                    elif check_type == "score":
                        base_table = "scores"
                        id_column = "artifact_id"
                    else:
                        continue
                    
                    # Apply target filter if specified
                    where_clause = f"WHERE {rule[5]}"  # condition_sql is at index 5
                    if target_id is not None:
                        where_clause += f" AND {id_column} = {target_id}"
                    
                    query = f"SELECT {id_column} as target_id FROM {base_table} {where_clause}"
                    
                    try:
                        violations = conn.execute(query).fetchall()
                        
                        for violation in violations:
                            # violation is a tuple with one element: target_id
                            target_id_value = violation[0]
                            issue = {
                                "rule_id": rule[0],  # rule_id at index 0
                                "rule_name": rule[1],  # name at index 1
                                "description": rule[2],  # description at index 2
                                "severity": rule[3],  # severity at index 3
                                "target_type": check_type,
                                "target_id": target_id_value,
                            }
                            issues.append(issue)
                            
                            # Store in validation_issues table
                            conn.execute(
                                """
                                INSERT OR IGNORE INTO validation_issues 
                                (rule_id, target_type, target_id, issue_details, status, created_at)
                                VALUES (?, ?, ?, ?, 'open', CURRENT_TIMESTAMP);
                                """,
                                (
                                    rule[0],  # rule_id
                                    check_type,
                                    target_id_value,
                                    json.dumps(issue),
                                ),
                            )
                    except sqlite3.Error as e:
                        log.error("Validation rule %s failed: %s", rule[0], e)
                
                return issues
        finally:
            conn.close()
    
    def compute_quality_score(self, target_type: str, target_id: int) -> QualityScore:
        """Compute quality score for a target."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        try:
            with conn:
                # Count validation issues by severity
                issues = conn.execute(
                    """
                    SELECT vr.severity, COUNT(vi.id) as count
                    FROM validation_issues vi
                    JOIN validation_rules vr ON vi.rule_id = vr.rule_id
                    WHERE vi.target_type = ? AND vi.target_id = ? AND vi.status = 'open'
                    GROUP BY vr.severity;
                    """,
                    (target_type, target_id),
                ).fetchall()
                
                issue_counts = {row[0]: row[1] for row in issues}
                total_issues = sum(issue_counts.values())
                
                # Calculate component scores
                completeness_score = self._compute_completeness(target_type, target_id, conn)
                consistency_score = self._compute_consistency(target_type, target_id, conn)
                timeliness_score = self._compute_timeliness(target_type, target_id, conn)
                
                # Weight validation issues by severity
                severity_weights = {
                    "info": 1,
                    "warning": 5,
                    "error": 20,
                    "critical": 50,
                }
                
                issue_penalty = sum(
                    issue_counts.get(severity, 0) * severity_weights[severity]
                    for severity in severity_weights
                )
                
                # Overall score (0-100)
                base_score = (
                    completeness_score * 0.4 +
                    consistency_score * 0.3 +
                    timeliness_score * 0.3
                )
                
                overall_score = max(0, min(100, base_score - issue_penalty))
                
                component_scores = {
                    "completeness": completeness_score,
                    "consistency": consistency_score,
                    "timeliness": timeliness_score,
                    "issue_penalty": issue_penalty,
                }
                
                # Store quality score
                now = utc_now_iso()
                conn.execute(
                    """
                    INSERT OR REPLACE INTO quality_scores 
                    (target_type, target_id, overall_score, component_scores, validation_issue_count, computed_at)
                    VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    (
                        target_type,
                        target_id,
                        overall_score,
                        json.dumps(component_scores),
                        total_issues,
                        now,
                    ),
                )
                
                # Get review info
                review_info = conn.execute(
                    """
                    SELECT reviewed_at, reviewer
                    FROM review_queue 
                    WHERE item_type = ? AND item_id = ? AND status = 'completed' AND decision = 'approved'
                    ORDER BY reviewed_at DESC
                    LIMIT 1;
                    """,
                    (target_type, target_id),
                ).fetchone()
                
                # Get actual validation issues for this target
                validation_issues = conn.execute(
                    """
                    SELECT 
                        vi.rule_id,
                        vr.name as rule_name,
                        vr.description,
                        vr.severity,
                        vi.issue_details,
                        vi.created_at
                    FROM validation_issues vi
                    JOIN validation_rules vr ON vi.rule_id = vr.rule_id
                    WHERE vi.target_type = ? AND vi.target_id = ? AND vi.status = 'open'
                    ORDER BY vr.severity DESC, vi.created_at DESC;
                    """,
                    (target_type, target_id),
                ).fetchall()
                
                validation_issue_details: list[dict[str, Any]] = []
                for row in validation_issues:
                    validation_issue_details.append(
                        {
                            "rule_id": row[0],
                            "rule_name": row[1],
                            "description": row[2],
                            "severity": row[3],
                        }
                    )

                return QualityScore(
                    target_type=target_type,
                    target_id=target_id,
                    overall_score=overall_score,
                    component_scores=component_scores,
                    validation_issues=validation_issue_details,
                    computed_at=now,
                    last_reviewed_at=review_info[0] if review_info else None,
                    reviewer=review_info[1] if review_info else None,
                )
        finally:
            conn.close()
    
    def _compute_completeness(self, target_type: str, target_id: int, conn: sqlite3.Connection) -> float:
        """Compute completeness score (0-100)."""
        if target_type == "artifact":
            row = conn.execute(
                "SELECT title, text, url, published_at, author_entity_ids FROM artifacts WHERE id = ?",
                (target_id,),
            ).fetchone()
            if not row:
                return 0
            
            required_fields = ["title", "text", "published_at"]
            optional_fields = ["url", "author_entity_ids"]
            
        elif target_type == "entity":
            row = conn.execute(
                "SELECT name, description, homepage_url FROM entities WHERE id = ?",
                (target_id,),
            ).fetchone()
            if not row:
                return 0
            
            required_fields = ["name"]
            optional_fields = ["description", "homepage_url"]
            
        elif target_type == "topic":
            row = conn.execute(
                "SELECT name, taxonomy_path, description FROM topics WHERE id = ?",
                (target_id,),
            ).fetchone()
            if not row:
                return 0
            
            required_fields = ["name"]
            optional_fields = ["taxonomy_path", "description"]
        else:
            return 0
        
        # Count non-null/empty fields
        if target_type == "artifact":
            columns = ["title", "text", "url", "published_at", "author_entity_ids"]
            row_dict = dict(zip(columns, row))
        elif target_type == "entity":
            columns = ["name", "description", "homepage_url"]
            row_dict = dict(zip(columns, row))
        elif target_type == "topic":
            columns = ["name", "taxonomy_path", "description"]
            row_dict = dict(zip(columns, row))
        else:
            row_dict = {}
        
        filled_required = sum(
            1
            for field in required_fields
            if (value := row_dict.get(field)) and str(value).strip()
        )
        filled_optional = sum(
            1
            for field in optional_fields
            if (value := row_dict.get(field)) and str(value).strip()
        )
        
        required_score = (filled_required / len(required_fields)) * 100 if required_fields else 100
        optional_bonus = (filled_optional / len(optional_fields)) * 20 if optional_fields else 0
        
        return min(100, required_score + optional_bonus)
    
    def _compute_consistency(self, target_type: str, target_id: int, conn: sqlite3.Connection) -> float:
        """Compute consistency score (0-100)."""
        if target_type == "entity":
            # Check if entity has consistent account information
            accounts = conn.execute(
                "SELECT platform, handle_or_id FROM accounts WHERE entity_id = ?",
                (target_id,),
            ).fetchall()
            
            if not accounts:
                return 50  # Neutral if no accounts
            
            if not accounts:
                return 50  # Neutral if no accounts
            
            # Check for naming consistency across platforms
            accounts_list = [{"platform": acc[0], "handle_or_id": acc[1]} for acc in accounts]
            name_variations = len({acc["handle_or_id"].lower() for acc in accounts_list})
            platform_count = len(accounts_list)
            
            if name_variations == 1:
                return 100  # Perfect consistency
            elif name_variations <= platform_count:
                return 80 - (name_variations * 10)  # Deduct for variations
            else:
                return 50
        
        elif target_type == "artifact":
            # Check if artifact has consistent entity linking
            result = conn.execute(
                """
                SELECT COUNT(DISTINCT entity_id) as count
                FROM accounts a
                JOIN artifacts art ON art.id = ?
                WHERE a.entity_id IN (
                    SELECT json_each.value 
                    FROM json_each(art.author_entity_ids)
                )
                """,
                (target_id,),
            ).fetchone()
            entity_count = result[0] if result else 0
            
            return 100 if entity_count > 0 else 60
        
        return 100  # Default for other types
    
    def _compute_timeliness(self, target_type: str, target_id: int, conn: sqlite3.Connection) -> float:
        """Compute timeliness score (0-100)."""
        if target_type == "artifact":
            row = conn.execute(
                "SELECT published_at, created_at FROM artifacts WHERE id = ?",
                (target_id,),
            ).fetchone()
            if not row:
                return 50
            
            columns = ["published_at", "created_at"]
            row_dict = dict(zip(columns, row))
            
            if not row_dict.get("published_at"):
                return 50
            
            try:
                pub_date = datetime.fromisoformat(row_dict["published_at"].replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                age_days = (now - pub_date).days
                
                # Score higher for recent content, but not too recent (might be incomplete)
                if age_days < 1:
                    return 70  # Very recent, might still be processing
                elif age_days < 30:
                    return 100  # Optimal age
                elif age_days < 365:
                    return 90 - (age_days / 30)  # Gradual decline
                else:
                    return max(20, 80 - (age_days / 365) * 10)  # Older content
            except (ValueError, TypeError):
                return 50
        
        elif target_type == "entity":
            # Check last activity date
            row = conn.execute(
                "SELECT last_activity_date FROM entities WHERE id = ?",
                (target_id,),
            ).fetchone()
            if not row:
                return 50
            
            columns = ["last_activity_date"]
            row_dict = dict(zip(columns, row))
            
            if not row_dict.get("last_activity_date"):
                return 50
            
            try:
                activity_date = datetime.fromisoformat(row_dict["last_activity_date"].replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                days_since = (now - activity_date).days
                
                if days_since < 30:
                    return 100
                elif days_since < 180:
                    return 90 - (days_since / 30)
                else:
                    return max(10, 70 - (days_since / 180) * 10)
            except (ValueError, TypeError):
                return 50
        
        return 100
    
    def log_audit_event(self, event: AuditEvent, conn: sqlite3.Connection | None = None) -> int:
        """Log an audit event. Returns the event ID."""
        own_conn = conn is None
        if own_conn:
            connection = sqlite3.connect(self.db_path, timeout=10.0)
        else:
            assert conn is not None
            connection = conn

        try:
            rowid: int | None = None
            with connection:
                cur = connection.execute(
                    (
                        "INSERT INTO audit_trail "
                        "(event_type, entity_type, entity_id, user_id, "
                        "old_values, new_values, timestamp, ip_address, user_agent) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);"
                    ),
                    (
                        event.event_type,
                        event.entity_type,
                        event.entity_id,
                        event.user_id,
                        json.dumps(event.old_values) if event.old_values else None,
                        json.dumps(event.new_values),
                        event.timestamp,
                        event.ip_address,
                        event.user_agent,
                    ),
                )
                rowid = cur.lastrowid
            if rowid is None:
                raise RuntimeError("Failed to log audit event; missing Last Row ID")
            return rowid
        finally:
            if own_conn:
                connection.close()
    
    def add_to_review_queue(
        self,
        item_type: str,
        item_id: int,
        review_type: str,
        priority: int = 0,
        assigned_to: str | None = None,
        due_hours: int = 72,
    ) -> int:
        """Add an item to the review queue. Returns the review ID."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        try:
            with conn:
                # Calculate due date
                due_at = datetime.now(timezone.utc) + timedelta(hours=due_hours)
                due_at_iso = due_at.isoformat().replace("+00:00", "Z")
                
                cur = conn.execute(
                    """
                    INSERT OR REPLACE INTO review_queue 
                    (item_type, item_id, review_type, priority, status, assigned_to, created_at, due_at)
                    VALUES (?, ?, ?, ?, 'pending', ?, CURRENT_TIMESTAMP, ?);
                    """,
                    (item_type, item_id, review_type, priority, assigned_to, due_at_iso),
                )
                
                review_id = cur.lastrowid
                if review_id is None:
                    raise RuntimeError("Failed to insert review queue item")
                
                # Log audit event
                self.log_audit_event(
                    AuditEvent(
                        event_type="review_created",
                        entity_type=item_type,
                        entity_id=item_id,
                        user_id=None,
                        old_values=None,
                        new_values={
                            "review_id": review_id,
                            "review_type": review_type,
                            "priority": priority,
                            "assigned_to": assigned_to,
                        },
                        timestamp=utc_now_iso(),
                    ),
                    conn=conn,
                )
                
                return review_id
        finally:
            conn.close()
    
    def process_review(
        self,
        review_id: int,
        reviewer: str,
        decision: str,
        review_notes: str | None = None,
    ) -> None:
        """Process a review decision."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        try:
            with conn:
                # Get review details
                review = conn.execute(
                    "SELECT item_type, item_id, review_type FROM review_queue WHERE id = ?",
                    (review_id,),
                ).fetchone()
                
                if not review:
                    raise ValueError(f"Review {review_id} not found")
                
                review_dict = {"item_type": review[0], "item_id": review[1], "review_type": review[2]}
                
                # Update review status
                now = utc_now_iso()
                conn.execute(
                    """
                    UPDATE review_queue 
                    SET status = 'completed',
                        reviewed_at = ?,
                        reviewer = ?,
                        review_notes = ?,
                        decision = ?
                    WHERE id = ?;
                    """,
                    (now, reviewer, review_notes, decision, review_id),
                )
                
                # Log audit event
                self.log_audit_event(
                    AuditEvent(
                        event_type="review_completed",
                        entity_type=review_dict["item_type"],
                        entity_id=review_dict["item_id"],
                        user_id=reviewer,
                        old_values={"status": "pending"},
                        new_values={
                            "status": "completed",
                            "decision": decision,
                            "review_notes": review_notes,
                        },
                        timestamp=now,
                    ),
                    conn=conn,
                )
                
                # Update quality score with review info
                conn.execute(
                    (
                        "INSERT OR REPLACE INTO quality_scores "
                        "(target_type, target_id, overall_score, component_scores, "
                        "validation_issue_count, computed_at, last_reviewed_at, reviewer) "
                        "SELECT target_type, target_id, overall_score, component_scores, "
                        "validation_issue_count, computed_at, ?, ? "
                        "FROM quality_scores "
                        "WHERE target_type = ? AND target_id = ?;"
                    ),
                    (now, reviewer, review_dict["item_type"], review_dict["item_id"]),
                )
                
                log.info("Review %d processed by %s: %s", review_id, reviewer, decision)
        finally:
            conn.close()
    
    def get_review_queue(
        self,
        status: str = "pending",
        assigned_to: str | None = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get items from the review queue."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        try:
            with conn:
                query = """
                    SELECT 
                        rq.*,
                        qs.overall_score as quality_score,
                        qs.validation_issue_count
                    FROM review_queue rq
                    LEFT JOIN quality_scores qs ON rq.item_type = qs.target_type AND rq.item_id = qs.target_id
                    WHERE rq.status = ?
                """
                params: list[object] = [status]
                
                if assigned_to:
                    query += " AND rq.assigned_to = ?"
                    params.append(assigned_to)
                
                query += " ORDER BY rq.priority DESC, rq.created_at ASC LIMIT ?"
                params.append(limit)
                
                cur = conn.execute(query, params)
                results = []
                for row in cur.fetchall():
                    # Map tuple to dict using known column order
                    # rq.* columns (13) + quality_score + validation_issue_count = 15 total
                    columns = [
                        'id', 'item_type', 'item_id', 'review_type', 'priority', 'status', 
                        'assigned_to', 'created_at', 'due_at', 'reviewed_at', 'reviewer', 
                        'review_notes', 'decision', 'quality_score', 'validation_issue_count'
                    ]
                    row_dict = dict(zip(columns, row))
                    # Convert quality_score and validation_issue_count if they exist
                    if row_dict.get('quality_score') is not None:
                        row_dict['quality_score'] = float(row_dict['quality_score'])
                    if row_dict.get('validation_issue_count') is not None:
                        row_dict['validation_issue_count'] = int(row_dict['validation_issue_count'])
                    results.append(row_dict)
                return results
        finally:
            conn.close()
    
    def get_data_quality_metrics(self) -> Dict[str, Any]:
        """Get overall data quality metrics."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        try:
            with conn:
                metrics = {}
                
                # Overall quality score distribution
                quality_stats = conn.execute(
                    """
                    SELECT 
                        COUNT(*) as total,
                        AVG(overall_score) as avg_score,
                        MIN(overall_score) as min_score,
                        MAX(overall_score) as max_score
                    FROM quality_scores;
                    """
                ).fetchone()
                
                if quality_stats:
                    metrics["quality_score_stats"] = {
                        "total": quality_stats[0],
                        "avg_score": quality_stats[1],
                        "min_score": quality_stats[2],
                        "max_score": quality_stats[3],
                    }
                else:
                    metrics["quality_score_stats"] = {}
                
                # Validation issues by severity
                issue_counts = conn.execute(
                    """
                    SELECT 
                        vr.severity,
                        COUNT(vi.id) as count
                    FROM validation_issues vi
                    JOIN validation_rules vr ON vi.rule_id = vr.rule_id
                    WHERE vi.status = 'open'
                    GROUP BY vr.severity;
                    """
                ).fetchall()
                
                metrics["open_issues_by_severity"] = {row[0]: row[1] for row in issue_counts}
                
                # Review queue stats
                review_stats = conn.execute(
                    """
                    SELECT 
                        status,
                        COUNT(*) as count,
                        AVG(priority) as avg_priority
                    FROM review_queue
                    GROUP BY status;
                    """
                ).fetchall()
                
                review_stats_map: dict[str, dict[str, float | int]] = {}
                for row in review_stats:
                    review_stats_map[row[0]] = {
                        "count": int(row[1]),
                        "avg_priority": float(row[2]) if row[2] is not None else 0.0,
                    }
                metrics["review_queue_stats"] = review_stats_map
                
                # Entity linking quality
                entity_linking = conn.execute(
                    """
                    SELECT 
                        COUNT(DISTINCT e.id) as total_entities,
                        COUNT(DISTINCT a.entity_id) as entities_with_accounts,
                        COUNT(DISTINCT a.entity_id) * 100.0 / COUNT(DISTINCT e.id) as linking_rate
                    FROM entities e
                    LEFT JOIN accounts a ON e.id = a.entity_id;
                    """
                ).fetchone()
                
                if entity_linking:
                    metrics["entity_linking"] = {
                        "total_entities": entity_linking[0],
                        "entities_with_accounts": entity_linking[1],
                        "linking_rate": entity_linking[2],
                    }
                else:
                    metrics["entity_linking"] = {}
                
                # Store metrics
                now = utc_now_iso()
                for metric_name, value in metrics.items():
                    conn.execute(
                        (
                            "INSERT OR REPLACE INTO data_quality_metrics "
                            "(metric_name, metric_value, metric_description, computed_at) "
                            "VALUES (?, ?, ?, ?);"
                        ),
                        (
                            metric_name,
                            float(value.get("avg_score", 0)) if isinstance(value, dict) else 0,
                            json.dumps(value),
                            now,
                        ),
                    )
                
                return metrics
        finally:
            conn.close()
    
    def run_full_quality_check(self) -> Dict[str, Any]:
        """Run complete quality check across all data types."""
        log.info("Starting full quality check")
        
        results: dict[str, Any] = {}
        
        # Run validation for each type
        for check_type in ["artifact", "entity", "topic", "score"]:
            issues = self.run_validation(check_type)
            results[f"{check_type}_validation_issues"] = len(issues)
            log.info("Found %d validation issues for %s", len(issues), check_type)
        
        # Compute quality scores for all items
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        try:
            with conn:
                for target_type in ["artifact", "entity", "topic"]:
                    # Get all IDs for the type
                    if target_type == "artifact":
                        ids = conn.execute("SELECT id FROM artifacts").fetchall()
                    elif target_type == "entity":
                        ids = conn.execute("SELECT id FROM entities").fetchall()
                    elif target_type == "topic":
                        ids = conn.execute("SELECT id FROM topics").fetchall()
                    
                    for row in ids:
                        self.compute_quality_score(target_type, row[0])
                    
                    results[f"{target_type}_quality_scores_computed"] = len(ids)
                    log.info("Computed quality scores for %d %s", len(ids), target_type)
        finally:
            conn.close()
        
        # Get overall metrics
        results["data_quality_metrics"] = self.get_data_quality_metrics()
        
        # Generate review queue items for low-quality items
        self._generate_review_queue_items()
        
        log.info("Full quality check completed")
        return results
    
    def _generate_review_queue_items(self) -> None:
        """Generate review queue items for low-quality data."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        try:
            with conn:
                # Find low-quality artifacts
                low_quality_artifacts = conn.execute(
                    """
                    SELECT target_id, overall_score
                    FROM quality_scores
                    WHERE target_type = 'artifact' AND overall_score < 50
                    ORDER BY overall_score ASC
                    LIMIT 100;
                    """
                ).fetchall()
                
                for artifact in low_quality_artifacts:
                    self.add_to_review_queue(
                        item_type="artifact",
                        item_id=artifact[0],
                        review_type="quality_review",
                        priority=max(1, int(100 - artifact[1])),
                    )
                
                # Find entities with linking issues
                entities_no_accounts = conn.execute(
                    """
                    SELECT e.id
                    FROM entities e
                    LEFT JOIN accounts a ON e.id = a.entity_id
                    WHERE a.id IS NULL
                    LIMIT 50;
                    """
                ).fetchall()
                
                for entity in entities_no_accounts:
                    self.add_to_review_queue(
                        item_type="entity",
                        item_id=entity[0],
                        review_type="linking_review",
                        priority=70,
                    )
                
                log.info(
                    "Generated %d artifact reviews and %d entity linking reviews",
                    len(low_quality_artifacts),
                    len(entities_no_accounts),
                )
        finally:
            conn.close()


def create_quality_engine(db_path: str, settings: Settings | None = None) -> QualityAssuranceEngine:
    """Factory function to create and initialize a quality assurance engine."""
    engine = QualityAssuranceEngine(db_path, settings)
    engine.register_default_rules()
    return engine
