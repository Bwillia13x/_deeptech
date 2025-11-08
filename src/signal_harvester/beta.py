"""Beta user management system."""

from __future__ import annotations

import json
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from .db import connect


@dataclass
class BetaUser:
    """Beta user data model."""
    
    id: int
    email: str
    invite_code: str
    status: str
    created_at: datetime
    activated_at: Optional[datetime]
    metadata: dict[str, Any]


def generate_invite_code(length: int = 32) -> str:
    """Generate a secure invite code."""
    return secrets.token_urlsafe(length)


def create_beta_user(db_path: str, email: str, metadata: Optional[dict[str, Any]] = None) -> BetaUser:
    """Create a new beta user with invite code.
    
    Args:
        db_path: Path to the SQLite database file
        email: User's email address
        metadata: Optional metadata dictionary
        
    Returns:
        BetaUser object
        
    Raises:
        sqlite3.IntegrityError: If email already exists
    """
    invite_code = generate_invite_code()
    metadata_json = json.dumps(metadata or {})
    
    with connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO beta_users (email, invite_code, metadata)
            VALUES (?, ?, ?)
            RETURNING id, email, invite_code, status, created_at, activated_at, metadata
            """,
            (email, invite_code, metadata_json),
        )
        row = cursor.fetchone()
        if not row:
            raise sqlite3.Error("Failed to create beta user")
        
    return BetaUser(
        id=row[0],
        email=row[1],
        invite_code=row[2],
        status=row[3],
        created_at=datetime.fromisoformat(row[4]),
        activated_at=datetime.fromisoformat(row[5]) if row[5] else None,
        metadata=json.loads(row[6]),
    )


def get_beta_user_by_invite(db_path: str, invite_code: str) -> Optional[BetaUser]:
    """Get beta user by invite code.
    
    Args:
        db_path: Path to the SQLite database file
        invite_code: Invite code to look up
        
    Returns:
        BetaUser object or None if not found
    """
    with connect(db_path) as conn:
        cursor = conn.execute(
            "SELECT * FROM beta_users WHERE invite_code = ?",
            (invite_code,),
        )
        row = cursor.fetchone()
        
    if not row:
        return None
        
    return BetaUser(
        id=row[0],
        email=row[1],
        invite_code=row[2],
        status=row[3],
        created_at=datetime.fromisoformat(row[4]),
        activated_at=datetime.fromisoformat(row[5]) if row[5] else None,
        metadata=json.loads(row[6]),
    )


def get_beta_user_by_email(db_path: str, email: str) -> Optional[BetaUser]:
    """Get beta user by email.
    
    Args:
        db_path: Path to the SQLite database file
        email: Email address to look up
        
    Returns:
        BetaUser object or None if not found
    """
    with connect(db_path) as conn:
        cursor = conn.execute(
            "SELECT * FROM beta_users WHERE email = ?",
            (email,),
        )
        row = cursor.fetchone()
        
    if not row:
        return None
        
    return BetaUser(
        id=row[0],
        email=row[1],
        invite_code=row[2],
        status=row[3],
        created_at=datetime.fromisoformat(row[4]),
        activated_at=datetime.fromisoformat(row[5]) if row[5] else None,
        metadata=json.loads(row[6]),
    )


def activate_beta_user(db_path: str, invite_code: str) -> bool:
    """Activate a beta user.
    
    Args:
        db_path: Path to the SQLite database file
        invite_code: Invite code to activate
        
    Returns:
        True if activation successful, False otherwise
    """
    with connect(db_path) as conn:
        cursor = conn.execute(
            """
            UPDATE beta_users 
            SET status = 'active', activated_at = CURRENT_TIMESTAMP 
            WHERE invite_code = ? AND status = 'pending'
            RETURNING id
            """,
            (invite_code,),
        )
        return cursor.fetchone() is not None


def list_beta_users(db_path: str, status: Optional[str] = None) -> list[BetaUser]:
    """List beta users, optionally filtered by status.
    
    Args:
        db_path: Path to the SQLite database file
        status: Optional status filter (pending, active, expired)
        
    Returns:
        List of BetaUser objects
    """
    with connect(db_path) as conn:
        if status:
            cursor = conn.execute(
                "SELECT * FROM beta_users WHERE status = ? ORDER BY created_at DESC",
                (status,),
            )
        else:
            cursor = conn.execute("SELECT * FROM beta_users ORDER BY created_at DESC")
        
        rows = cursor.fetchall()
        
    return [
        BetaUser(
            id=row[0],
            email=row[1],
            invite_code=row[2],
            status=row[3],
            created_at=datetime.fromisoformat(row[4]),
            activated_at=datetime.fromisoformat(row[5]) if row[5] else None,
            metadata=json.loads(row[6]),
        )
        for row in rows
    ]


def expire_invite(db_path: str, invite_code: str) -> bool:
    """Expire a beta invite.
    
    Args:
        db_path: Path to the SQLite database file
        invite_code: Invite code to expire
        
    Returns:
        True if expiration successful, False otherwise
    """
    with connect(db_path) as conn:
        cursor = conn.execute(
            """
            UPDATE beta_users 
            SET status = 'expired'
            WHERE invite_code = ? AND status = 'pending'
            RETURNING id
            """,
            (invite_code,),
        )
        return cursor.fetchone() is not None


def get_beta_stats(db_path: str) -> dict[str, int]:
    """Get beta program statistics.
    
    Args:
        db_path: Path to the SQLite database file
        
    Returns:
        Dictionary with statistics
    """
    with connect(db_path) as conn:
        cursor = conn.execute(
            """
            SELECT 
                status,
                COUNT(*) as count
            FROM beta_users
            GROUP BY status
            """,
        )
        rows = cursor.fetchall()
        
    stats = {"pending": 0, "active": 0, "expired": 0, "total": 0}
    for row in rows:
        status = row[0]
        count = row[1]
        stats[status] = count
        stats["total"] += count
        
    return stats
