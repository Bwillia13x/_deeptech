from __future__ import annotations

import os
import shutil
from typing import Dict, List, Optional

from .logger import get_logger
from .rebuild import run_rebuilds
from .stats import SnapshotInfo, compute_stats

log = get_logger(__name__)


def delete_snapshots_by_name(
    base_dir: str,
    names: List[str],
    dry_run: bool = True,
    rebuild_site: bool = False,
    rebuild_html: bool = False,
    site_args: Optional[List[str]] = None,
    html_args: Optional[List[str]] = None,
    ignore_missing_rebuilds: bool = True,
) -> Dict[str, object]:
    """
    Delete an arbitrary set of snapshot directories by name (non-contiguous).
    - Validates names exist in stats.
    - Removes directories oldest->newest.
    - Returns plan and results; stats are recomputed if applied.

    Rebuild operations, if requested, are invoked (best-effort) via signal_harvester.rebuild.
    """
    names = [str(n) for n in names]
    # Deduplicate while preserving order provided by 'names'
    seen = set()
    deduped: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            deduped.append(n)
    names = deduped

    stats_before = compute_stats(base_dir)
    snaps = list(stats_before["snapshots"])
    name_to_info = {str(s.get("name")): s for s in snaps}

    missing = [n for n in names if n not in name_to_info]
    if missing:
        return {
            "ok": False,
            "base_dir": base_dir,
            "dry_run": dry_run,
            "before": stats_before,
            "after": None,
            "removed": [],
            "planned_remove": names,
            "errors": [{"name": n, "error": "not found"} for n in missing],
            "missing": missing,
            "rebuild_result": None,
        }

    # Remove oldest->newest by ordering via stats list (assumed oldest->newest)
    index_by_name = {str(snaps[i]["name"]): i for i in range(len(snaps))}
    to_remove_names = sorted(names, key=lambda n: index_by_name[n])

    removed: List[str] = []
    errors: List[Dict[str, str]] = []

    def _snap_dir(info: SnapshotInfo, name: str) -> str:
        # Try to derive a directory path from stats; fallback to base_dir/snapshots/<name>
        candidates = []
        for key in ("dir", "snapshot_dir", "path"):
            v = info.get(key)
            if isinstance(v, str):
                candidates.append(v)
        # Fallback default
        candidates.append(os.path.join(base_dir, "snapshots", name))
        for c in candidates:
            if os.path.isdir(c):
                return c
        # Last resort: return the last candidate even if not exists
        return candidates[-1]

    if not dry_run:
        for n in to_remove_names:
            info = name_to_info[n]
            dpath = _snap_dir(info, n)
            try:
                if os.path.isdir(dpath):
                    shutil.rmtree(dpath)
                    removed.append(n)
                else:
                    log.warning("Snapshot dir not found (treat as removed): %s", dpath)
                    removed.append(n)
            except Exception as e:
                log.exception("Failed to remove snapshot %s at %s", n, dpath)
                errors.append({"name": n, "error": str(e)})

    after_stats = compute_stats(base_dir) if not dry_run else None

    rebuild_result = None
    if rebuild_site or rebuild_html:
        rebuild_result = run_rebuilds(
            base_dir,
            rebuild_site=rebuild_site,
            rebuild_html=rebuild_html,
            dry_run=dry_run,
            site_args=site_args,
            html_args=html_args,
            ignore_missing=ignore_missing_rebuilds,
        )

    return {
        "ok": len(errors) == 0,
        "base_dir": base_dir,
        "dry_run": dry_run,
        "before": stats_before,
        "after": after_stats,
        "planned_remove": to_remove_names,
        "removed": removed if not dry_run else [],
        "errors": errors,
        "rebuild_site": rebuild_site,
        "rebuild_html": rebuild_html,
        "rebuild_result": rebuild_result,
    }
