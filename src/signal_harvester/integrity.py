from __future__ import annotations

import hashlib
import json
import os
from typing import Any


def _sha256_file(path: str) -> str:
    """Compute SHA256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def write_checksums_file(base_dir: str, files: list[str]) -> None:
    """
    Write a checksums.json manifest for the given files.
    Each file path should be relative to base_dir.
    """
    manifest = []
    for rel_path in files:
        full_path = os.path.join(base_dir, rel_path)
        if os.path.isfile(full_path):
            checksum = _sha256_file(full_path)
            manifest.append({
                "path": rel_path,
                "sha256": checksum,
                "size": os.path.getsize(full_path)
            })
    
    checksums_path = os.path.join(base_dir, "checksums.json")
    with open(checksums_path, "w", encoding="utf-8") as f:
        json.dump({"files": manifest}, f, ensure_ascii=False, indent=2)


def verify_checksums_file(base_dir: str) -> dict[str, Any]:
    """
    Verify all files in checksums.json against their hashes.
    Returns verification result with details.
    """
    checksums_path = os.path.join(base_dir, "checksums.json")
    if not os.path.exists(checksums_path):
        return {"ok": False, "error": "checksums.json not found"}
    
    with open(checksums_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    
    results: dict[str, Any] = {"ok": True, "verified": [], "mismatched": [], "missing": []}
    
    for file_info in manifest.get("files", []):
        rel_path = file_info["path"]
        expected_sha = file_info["sha256"]
        full_path = os.path.join(base_dir, rel_path)
        
        if not os.path.isfile(full_path):
            results["missing"].append({"path": rel_path, "expected_sha256": expected_sha})
            results["ok"] = False
        else:
            actual_sha = _sha256_file(full_path)
            if actual_sha == expected_sha:
                results["verified"].append({"path": rel_path, "sha256": actual_sha})
            else:
                results["mismatched"].append({
                    "path": rel_path, 
                    "expected_sha256": expected_sha,
                    "actual_sha256": actual_sha
                })
                results["ok"] = False
    
    return results
