from __future__ import annotations

import argparse
import os
import shutil
from typing import Any, TypedDict

from .logger import configure_logging, get_logger
from .rebuild import run_rebuilds
from .snapshot import existing_snapshots


class PruneStats(TypedDict):
    snapshot_count: int
    total_bytes: int
    total_files: int
    snapshots: list[Any]  # noqa: UP006


class PruneResult(TypedDict):
    ok: bool
    base_dir: str
    dry_run: bool
    before: PruneStats
    after: PruneStats | None
    keep: int
    planned_remove: list[str]
    removed: list[str]
    freed_bytes: int
    errors: list[dict[str, str]]
    rebuild_result: dict[str, object] | None

log = get_logger(__name__)


def _dir_size(path: str) -> int:
    total = 0
    for root, dirs, files in os.walk(path, onerror=None):
        for name in files:
            fp = os.path.join(root, name)
            try:
                st = os.lstat(fp)
                total += int(getattr(st, "st_size", 0) or 0)
            except Exception:
                # Ignore unreadable files
                pass
    return total


def prune_snapshots(
    base_dir: str,
    keep: int,
    dry_run: bool = True,
    rebuild_site: bool = False,
    rebuild_html: bool = False,
    site_args: list[str] | None = None,
    html_args: list[str] | None = None,
    ignore_missing_rebuilds: bool = True,
) -> PruneResult:
    """
    Prune snapshots by keeping only the newest 'keep' snapshots.
    Removes oldest-first to reach the desired count.
    """
    if keep < 0:
        raise ValueError("keep must be >= 0")

    snaps = existing_snapshots(base_dir)
    log.info("Found %d snapshots", len(snaps))
    if not snaps:
        before: PruneStats = {"snapshot_count": 0, "total_bytes": 0, "total_files": 0, "snapshots": []}
        after_empty: PruneStats = {"snapshot_count": 0, "total_bytes": 0, "total_files": 0, "snapshots": []}
        after: PruneStats | None = None if dry_run else after_empty
        res: PruneResult = {
            "ok": True,
            "base_dir": base_dir,
            "dry_run": dry_run,
            "before": before,
            "after": after,
            "keep": keep,
            "planned_remove": [],
            "removed": [],
            "freed_bytes": 0,
            "errors": [],
            "rebuild_result": None,
        }
        return res

    # Oldest first; keep newest `keep`
    to_remove = snaps[:-keep] if keep > 0 else snaps[:]
    snaps[-keep:] if keep > 0 else []

    freed = 0
    actually_removed: list[str] = []
    errors: list[dict[str, str]] = []

    for snap in to_remove:
        path = os.path.join(base_dir, snap)
        size = _dir_size(path)
        freed += size
        log.info("Remove snapshot %s (size ~ %d bytes)%s", snap, size, " [dry-run]" if dry_run else "")
        if not dry_run:
            try:
                shutil.rmtree(path)
                actually_removed.append(snap)
            except Exception as e:
                log.error("Failed to remove %s: %s", path, e)
                errors.append({"name": snap, "error": str(e)})

    remaining = existing_snapshots(base_dir)

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

    before_stats: PruneStats = {"snapshot_count": len(snaps), "total_bytes": 0, "total_files": 0, "snapshots": []}
    after_result: PruneStats = {"snapshot_count": len(remaining), "total_bytes": 0, "total_files": 0, "snapshots": []}
    after_stats: PruneStats | None = None if dry_run else after_result
    
    result: PruneResult = {
        "ok": len(errors) == 0,
        "base_dir": base_dir,
        "dry_run": dry_run,
        "before": before_stats,
        "after": after_stats,
        "keep": keep,
        "planned_remove": to_remove,
        "removed": actually_removed if not dry_run else [],
        "freed_bytes": freed,
        "errors": errors,
        "rebuild_result": rebuild_result,
    }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="harvest-prune", description="Prune snapshots by keeping only the newest N snapshots."
    )
    parser.add_argument("--base-dir", required=True)
    parser.add_argument("--keep", required=True, type=int)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--force", action="store_true", help="Apply changes (default dry-run)")
    parser.add_argument("--rebuild-site", action="store_true", help="Rebuild site index after pruning")
    parser.add_argument("--rebuild-html", action="store_true", help="Rebuild HTML after pruning")
    parser.add_argument("--site-arg", action="append", default=[], help="Extra arg for site rebuild (repeatable)")
    parser.add_argument("--html-arg", action="append", default=[], help="Extra arg for HTML rebuild (repeatable)")
    parser.add_argument(
        "--ignore-missing-rebuilds",
        action="store_true",
        default=True,
        help="Skip rebuild steps if modules are missing"
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    configure_logging(args.log_level)

    dry_run = not args.force

    try:
        res = prune_snapshots(
            base_dir=args.base_dir,
            keep=args.keep,
            dry_run=dry_run,
            rebuild_site=args.rebuild_site,
            rebuild_html=args.rebuild_html,
            site_args=args.site_arg or [],
            html_args=args.html_arg or [],
            ignore_missing_rebuilds=args.ignore_missing_rebuilds,
        )
    except Exception as e:
        log.exception("Prune failed")
        print("[FAIL] prune failed:", e)
        return 2

    if args.json:
        import json
        print(json.dumps(res, indent=2, default=str))
        return 0

    # res is already a PruneResult
    before = res["before"]
    after = res["after"]
    planned_remove = res["planned_remove"]
    removed = res["removed"]

    from .stats import _humanize_bytes
    print(
        f"[OK] Before: {before['snapshot_count']} snapshots, "
        f"total size {_humanize_bytes(before['total_bytes'])}"
    )
    if dry_run:
        print(f"[DRY-RUN] Would remove: {', '.join(planned_remove)}")
        return 0

    print("[APPLY] Removed:", ", ".join(removed))
    if after:
        after_count = after['snapshot_count']
        after_size = _humanize_bytes(after['total_bytes'])
        print(f"[OK] After: {after_count} snapshots, total size {after_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
