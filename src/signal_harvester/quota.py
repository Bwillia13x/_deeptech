from __future__ import annotations

import argparse
import json
import re
from typing import List, Optional, TypedDict

from .logger import configure_logging, get_logger
from .prune import PruneResult, prune_snapshots
from .stats import StatsResult, _humanize_bytes, compute_stats

log = get_logger(__name__)


class QuotaInfo(TypedDict):
    max_bytes: int | None
    max_files: int | None
    keep_min: int


class QuotaPlan(TypedDict):
    ok: bool
    base_dir: str
    before: StatsResult
    plan_keep: int
    planned_remove: list[str]
    quota: QuotaInfo
    quota_satisfied_after_plan: bool
    blocked_by_keep_min: bool


class QuotaApplyResult(TypedDict):
    ok: bool
    base_dir: str
    dry_run: bool
    quota: QuotaInfo
    before: StatsResult
    after: StatsResult | None
    plan_keep: int
    planned_remove: list[str]
    removed: list[str]
    quota_satisfied_after_plan: bool
    blocked_by_keep_min: bool
    prune_result: PruneResult | None


_SIZE_RE = re.compile(r"^\s*(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>[KMGTP]?i?B?|)\s*$", re.IGNORECASE)
_DECIMAL = {
    "": 1,
    "B": 1,
    "K": 10**3,
    "KB": 10**3,
    "M": 10**6,
    "MB": 10**6,
    "G": 10**9,
    "GB": 10**9,
    "T": 10**12,
    "TB": 10**12,
    "P": 10**15,
    "PB": 10**15,
}
_BINARY = {
    "KI": 2**10,
    "KIB": 2**10,
    "MI": 2**20,
    "MIB": 2**20,
    "GI": 2**30,
    "GIB": 2**30,
    "TI": 2**40,
    "TIB": 2**40,
    "PI": 2**50,
    "PIB": 2**50,
}


def parse_size_to_bytes(s: str) -> int:
    """
    Parse human-friendly size strings into bytes.
    Examples: "100", "10K", "10KB", "10KiB", "2.5MiB", "1G", "1GiB"
    """
    if s is None:
        raise ValueError("size string is None")
    m = _SIZE_RE.match(s)
    if not m:
        raise ValueError(f"invalid size: {s!r}")
    num_str = m.group("num")
    unit = m.group("unit").upper()
    # Normalize binary suffixes without trailing B
    unit = unit.replace("IB", "I").replace("B", "B")  # keep B units, KI/MI also handled below

    try:
        value = float(num_str)
    except Exception as e:
        raise ValueError(f"invalid numeric value in size: {s!r}") from e

    mult = None
    if unit in _BINARY:
        mult = _BINARY[unit]
    elif unit in _DECIMAL:
        mult = _DECIMAL[unit]
    elif unit.rstrip("B") in _DECIMAL:
        mult = _DECIMAL[unit.rstrip("B")]
    else:
        # Try e.g. "KI", "MI" without B
        if unit in _BINARY:
            mult = _BINARY[unit]
        else:
            raise ValueError(f"unknown size unit: {unit!r} in {s!r}")

    bytes_val = int(value * mult)
    if bytes_val < 0:
        raise ValueError("size must be non-negative")
    return bytes_val


def compute_quota_plan(
    base_dir: str,
    max_bytes: Optional[int] = None,
    max_files: Optional[int] = None,
    keep_min: int = 0,
) -> QuotaPlan:
    """
    Determine how many oldest snapshots need to be pruned to satisfy
    the given quota constraints. Does not delete anything.

    Returns a dict including:
      - ok: bool
      - base_dir: str
      - before: stats dict from compute_stats()
      - plan_keep: int (snapshots to keep)
      - planned_remove: [names]
      - quota: {max_bytes, max_files, keep_min}
      - quota_satisfied_after_plan: bool
      - blocked_by_keep_min: bool
    """
    if keep_min < 0:
        keep_min = 0

    stats: StatsResult = compute_stats(base_dir)
    snaps = list(stats["snapshots"])
    total_bytes = stats["total_bytes"]
    total_files = stats["total_files"]

    count = len(snaps)
    keep = count
    planned_remove: List[str] = []
    bytes_left = total_bytes
    files_left = total_files
    blocked = False

    def needs_more_prune() -> bool:
        need_b = (max_bytes is not None) and (bytes_left > max_bytes)
        need_f = (max_files is not None) and (files_left > max_files)
        return bool(need_b or need_f)

    idx = 0
    while needs_more_prune():
        if keep <= keep_min or idx >= count:
            blocked = True
            break
        # Remove oldest snapshot (assumes existing_snapshots sorts oldest->newest)
        snap = snaps[idx]
        planned_remove.append(str(snap["name"]))
        bytes_left -= snap["size_bytes"]
        files_left -= snap["file_count"]
        keep -= 1
        idx += 1

    satisfied = not needs_more_prune()

    return {
        "ok": True,
        "base_dir": base_dir,
        "before": stats,
        "plan_keep": keep,
        "planned_remove": planned_remove,
        "quota": {"max_bytes": max_bytes, "max_files": max_files, "keep_min": keep_min},
        "quota_satisfied_after_plan": satisfied,
        "blocked_by_keep_min": blocked,
    }


def apply_quota(
    base_dir: str,
    max_bytes: Optional[int] = None,
    max_files: Optional[int] = None,
    keep_min: int = 0,
    dry_run: bool = True,
    rebuild_site: bool = False,
    rebuild_html: bool = False,
) -> QuotaApplyResult:
    """
    Apply quota by pruning oldest snapshots as needed (delegates to prune_snapshots).
    """
    plan = compute_quota_plan(base_dir, max_bytes=max_bytes, max_files=max_files, keep_min=keep_min)
    keep = plan["plan_keep"]
    planned_remove = plan["planned_remove"]

    removed: List[str] = []
    prune_res: PruneResult | None = None

    if planned_remove and not dry_run:
        # Delegate actual deletion to existing prune logic
        prune_res = prune_snapshots(
            base_dir,
            keep=keep,
            dry_run=False,
            rebuild_site=rebuild_site,
            rebuild_html=rebuild_html,
        )
        removed = list(prune_res["removed"])

    after_stats = compute_stats(base_dir) if not dry_run else None

    return {
        "ok": True,
        "base_dir": base_dir,
        "dry_run": dry_run,
        "quota": plan["quota"],
        "before": plan["before"],
        "after": after_stats,
        "plan_keep": keep,
        "planned_remove": planned_remove,
        "removed": removed,
        "quota_satisfied_after_plan": plan["quota_satisfied_after_plan"],
        "blocked_by_keep_min": plan["blocked_by_keep_min"],
        "prune_result": prune_res,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="harvest-quota",
        description="Prune oldest snapshots until size/file quotas are satisfied."
    )
    parser.add_argument("--base-dir", required=True, help="Snapshots base directory")
    parser.add_argument("--max-bytes", help="Maximum total size across snapshots (e.g., 50GiB)")
    parser.add_argument("--max-files", type=int, help="Maximum total file count across snapshots")
    parser.add_argument("--keep-min", type=int, default=0, help="Minimum number of snapshots to always keep")
    parser.add_argument("--json", action="store_true", help="Output JSON to stdout")
    parser.add_argument("--force", action="store_true", help="Apply changes (default is dry-run)")
    parser.add_argument("--rebuild-site", action="store_true", help="Rebuild site index after pruning")
    parser.add_argument("--rebuild-html", action="store_true", help="Rebuild HTML after pruning")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    configure_logging(args.log_level)

    if args.max_bytes is None and args.max_files is None:
        log.error("At least one of --max-bytes or --max-files is required")
        print("[FAIL] You must specify --max-bytes and/or --max-files")
        return 2

    max_bytes: Optional[int] = None
    if args.max_bytes is not None:
        try:
            max_bytes = parse_size_to_bytes(args.max_bytes)
        except ValueError as e:
            log.error("Invalid --max-bytes: %s", e)
            print("[FAIL] invalid --max-bytes:", e)
            return 2

    dry_run = not args.force

    try:
        res = apply_quota(
            base_dir=args.base_dir,
            max_bytes=max_bytes,
            max_files=args.max_files,
            keep_min=args.keep_min,
            dry_run=dry_run,
            rebuild_site=args.rebuild_site,
            rebuild_html=args.rebuild_html,
        )
    except Exception as e:
        log.exception("Quota application failed")
        print("[FAIL] quota failed:", e)
        return 2

    # res is already a QuotaApplyResult
    before = res["before"]
    after = res["after"]
    planned = res["planned_remove"]
    removed = res["removed"]
    satisfied = res["quota_satisfied_after_plan"]
    res["blocked_by_keep_min"]
    quota = res["quota"]

    if args.json:
        print(json.dumps(res, indent=2, default=str))
        return 0

    def fmtq() -> str:
        parts = []
        max_bytes = quota.get("max_bytes")
        max_files = quota.get("max_files")
        if max_bytes is not None:
            parts.append(f"max_bytes={_humanize_bytes(max_bytes)}")
        if max_files is not None:
            parts.append(f"max_files={max_files}")
        parts.append(f"keep_min={quota['keep_min']}")
        return ", ".join(parts)

    snap_count = int(before['snapshot_count'])
    size_str = _humanize_bytes(int(before['total_bytes']))
    file_count = int(before['total_files'])
    print(f"[OK] Before: {snap_count} snapshots, {size_str}, files {file_count}")
    print(f"Quota: {fmtq()}")

    if not planned:
        if satisfied:
            print("[OK] Quota already satisfied; nothing to prune.")
        else:
            print("[WARN] Quota not satisfied but blocked by keep_min or no snapshots left to remove.")
        return 0

    print(f"Plan: remove {len(planned)} oldest snapshots -> keep {res['plan_keep']}")
    if dry_run:
        print("[DRY-RUN] Would remove:", ", ".join(planned))
        return 0

    print("[APPLY] Removed:", ", ".join(removed))
    if after:
        after_count = after['snapshot_count']
        after_size = _humanize_bytes(after['total_bytes'])
        after_files = after['total_files']
        print(f"[OK] After: {after_count} snapshots, total size {after_size}, files {after_files}")
    print(f"[OK] After: {after_count} snapshots, total size {after_size}, files {after_files}")

    if not satisfied:
        print("[WARN] Quota still not satisfied (likely due to keep_min).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
