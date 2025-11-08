from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from typing import Any


class JSONFormatter(logging.Formatter):
    """JSON log formatter for structured logging."""
    
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.hostname = os.getenv("HOSTNAME", "localhost")
    
    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.now().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "hostname": self.hostname,
            "pid": record.process,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields if present
        if hasattr(record, "extra_fields"):
            log_obj.update(record.extra_fields)
        
        return json.dumps(log_obj)


def configure_logging(level: str | None = None, json_output: bool = False) -> None:
    """Configure logging with optional JSON output for production."""
    lvl_str = (level or os.getenv("LOG_LEVEL") or "INFO").upper()
    lvl = getattr(logging, lvl_str, logging.INFO)
    
    # Remove existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    if json_output or os.getenv("LOG_FORMAT") == "json":
        # JSON logging for production
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        logging.basicConfig(
            level=lvl,
            handlers=[handler],
            force=True
        )
    else:
        # Try to use RichHandler for development
        try:
            from rich.logging import RichHandler

            logging.basicConfig(
                level=lvl,
                format="%(message)s",
                datefmt="[%X]",
                handlers=[RichHandler(
                    rich_tracebacks=True,
                    markup=True,
                    show_time=True,
                    show_level=True,
                    show_path=False
                )],
                force=True
            )
        except Exception:
            # Fallback to standard logging
            logging.basicConfig(
                level=lvl,
                format="%(asctime)s %(levelname)s %(name)s - %(message)s",
                force=True
            )


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)


def log_extra(**kwargs: Any) -> dict[str, Any]:
    """Helper to create extra fields for structured logging."""
    return {"extra_fields": kwargs}
