#!/usr/bin/env python3
"""CLI-accessible wrapper for the PostgreSQL validation helpers."""

from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    from signal_harvester.postgres_validation import validate_postgresql
except ImportError:  # pragma: no cover - fallback for direct script execution
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "src"))
    from signal_harvester.postgres_validation import validate_postgresql


if __name__ == "__main__":
    success = validate_postgresql(os.environ.get("DATABASE_URL"))
    sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Validation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = validate_postgresql()
    sys.exit(0 if success else 1)
