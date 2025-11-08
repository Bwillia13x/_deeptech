"""Input validation utilities for Signal Harvester."""

from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException


def validate_tweet_id(tweet_id: str) -> str:
    """Validate tweet ID format."""
    if not tweet_id or not isinstance(tweet_id, str):
        raise HTTPException(status_code=400, detail="tweet_id must be a non-empty string")
    
    # Twitter IDs are numeric strings, typically 18-19 digits
    if not re.match(r'^\d+$', tweet_id):
        raise HTTPException(status_code=400, detail="tweet_id must be numeric")
    
    if len(tweet_id) < 10 or len(tweet_id) > 20:
        raise HTTPException(status_code=400, detail="tweet_id length must be between 10-20 digits")
    
    return tweet_id


def validate_limit(limit: int, min_val: int = 1, max_val: int = 200) -> int:
    """Validate pagination limit."""
    if not isinstance(limit, int):
        raise HTTPException(status_code=400, detail="limit must be an integer")
    
    if limit < min_val or limit > max_val:
        raise HTTPException(
            status_code=400,
            detail=f"limit must be between {min_val} and {max_val}"
        )
    
    return limit


def validate_salience(salience: float, min_val: float = 0.0, max_val: float = 100.0) -> float:
    """Validate salience score."""
    if not isinstance(salience, (int, float)):
        raise HTTPException(status_code=400, detail="salience must be a number")
    
    if salience < min_val or salience > max_val:
        raise HTTPException(
            status_code=400,
            detail=f"salience must be between {min_val} and {max_val}"
        )
    
    return float(salience)


def validate_hours(hours: int | None, min_val: int = 1, max_val: int = 168) -> int | None:
    """Validate hours filter."""
    if hours is None:
        return None
    
    if not isinstance(hours, int):
        raise HTTPException(status_code=400, detail="hours must be an integer")
    
    if hours < min_val or hours > max_val:
        raise HTTPException(
            status_code=400,
            detail=f"hours must be between {min_val} and {max_val}"
        )
    
    return hours


def validate_api_key(api_key: str | None) -> str | None:
    """Validate API key format."""
    if api_key is None:
        return None
    
    if not isinstance(api_key, str):
        raise HTTPException(status_code=400, detail="API key must be a string")
    
    if len(api_key) < 16:
        raise HTTPException(status_code=400, detail="API key must be at least 16 characters")
    
    if len(api_key) > 128:
        raise HTTPException(status_code=400, detail="API key must not exceed 128 characters")
    
    # Check for reasonable API key characters (alphanumeric + some special chars)
    if not re.match(r'^[a-zA-Z0-9-_]+$', api_key):
        raise HTTPException(status_code=400, detail="API key contains invalid characters")
    
    return api_key


def validate_query_name(name: str) -> str:
    """Validate query name format."""
    if not name or not isinstance(name, str):
        raise HTTPException(status_code=400, detail="Query name must be a non-empty string")
    
    if len(name) < 3:
        raise HTTPException(status_code=400, detail="Query name must be at least 3 characters")
    
    if len(name) > 50:
        raise HTTPException(status_code=400, detail="Query name must not exceed 50 characters")
    
    # Only allow alphanumeric, underscore, and hyphen
    if not re.match(r'^[a-zA-Z0-9_-]+$', name):
        raise HTTPException(
            status_code=400,
            detail="Query name can only contain letters, numbers, hyphens, and underscores"
        )
    
    return name


def validate_twitter_query(query: str) -> str:
    """Validate Twitter search query format."""
    if not query or not isinstance(query, str):
        raise HTTPException(status_code=400, detail="Query must be a non-empty string")
    
    if len(query) < 5:
        raise HTTPException(status_code=400, detail="Query must be at least 5 characters")
    
    if len(query) > 500:
        raise HTTPException(status_code=400, detail="Query must not exceed 500 characters")
    
    # Basic validation - Twitter queries can be complex
    # Just check for common issues
    if query.count('"') % 2 != 0:
        raise HTTPException(status_code=400, detail="Query has unbalanced quotes")
    
    if query.count('(') != query.count(')'):
        raise HTTPException(status_code=400, detail="Query has unbalanced parentheses")
    
    return query


def sanitize_string(input_str: str, max_length: int = 1000) -> str:
    """Sanitize string input to prevent injection attacks."""
    if not isinstance(input_str, str):
        raise HTTPException(status_code=400, detail="Input must be a string")
    
    # Remove null bytes and control characters
    sanitized = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', input_str)
    
    # Limit length
    if len(sanitized) > max_length:
        raise HTTPException(
            status_code=400,
            detail=f"Input exceeds maximum length of {max_length} characters"
        )
    
    return sanitized


def validate_and_sanitize_dict(data: dict[str, Any], allowed_keys: set[str]) -> dict[str, Any]:
    """Validate and sanitize a dictionary input."""
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Input must be a dictionary/object")
    
    # Check for unexpected keys
    unexpected_keys = set(data.keys()) - allowed_keys
    if unexpected_keys:
        raise HTTPException(
            status_code=400,
            detail=f"Unexpected keys: {', '.join(unexpected_keys)}"
        )
    
    # Sanitize string values
    sanitized = {}
    for key, value in data.items():
        if isinstance(value, str):
            sanitized[key] = sanitize_string(value)
        else:
            sanitized[key] = value
    
    return sanitized


def validate_configuration(config: dict[str, Any]) -> tuple[bool, str | None]:
    """Validate configuration dictionary."""
    try:
        # Check required top-level keys
        required_keys = {"app", "queries"}
        missing_keys = required_keys - set(config.keys())
        if missing_keys:
            return False, f"Missing required configuration keys: {missing_keys}"
        
        # Validate app section
        app_config = config.get("app", {})
        if not isinstance(app_config, dict):
            return False, "app must be a dictionary"
        
        # Validate queries
        queries = config.get("queries", [])
        if not isinstance(queries, list):
            return False, "queries must be a list"
        
        for i, query in enumerate(queries):
            if not isinstance(query, dict):
                return False, f"Query {i} must be a dictionary"
            
            if "name" not in query:
                return False, f"Query {i} missing required field: name"
            
            if "query" not in query:
                return False, f"Query {i} missing required field: query"
        
        return True, None
    
    except ValueError as e:
        return False, f"Configuration validation error: {str(e)}"
