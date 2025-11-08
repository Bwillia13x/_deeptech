from __future__ import annotations

import argparse
import json
import os
from typing import TypedDict

from .logger import configure_logging, get_logger
from .snapshot import existing_snapshots


class SnapshotInfo(TypedDict):
    name: str
    path: str
    size_bytes: int
    file_count: int


class StatsResult(TypedDict):
    ok: bool
    base_dir: str
    snapshot_count: int
    total_bytes: int
    total_files: int
    snapshots: list[SnapshotInfo]

log = get_logger(__name__)


def _dir_size_and_files(path: str) -> dict[str, int]:
    total_bytes = 0
    file_count = 0
    for root, dirs, files in os.walk(path, onerror=None):
        for name in files:
            fp = os.path.join(root, name)
            try:
                st = os.lstat(fp)
                total_bytes += int(getattr(st, "st_size", 0) or 0)
                file_count += 1
            except Exception:
                # Ignore unreadable files
                pass
    return {"bytes": total_bytes, "files": file_count}


def compute_stats(base_dir: str) -> StatsResult:
    """
    Compute per-snapshot size and file count, plus totals.

    Returns:
        {
          "ok": bool,
          "base_dir": str,
          "snapshot_count": int,
          "total_bytes": int,
          "total_files": int,
          "snapshots": [
             {"name": str, "path": str, "size_bytes": int, "file_count": int},
             ...
          ]
        }
    """
    snaps = existing_snapshots(base_dir)
    log.info("Found %d snapshots", len(snaps))

    results: list[SnapshotInfo] = []
    total_bytes = 0
    total_files = 0

    for snap in snaps:
        spath = os.path.join(base_dir, snap)
        stats = _dir_size_and_files(spath)
        results.append(
            SnapshotInfo(
                name=snap,
                path=spath,
                size_bytes=stats["bytes"],
                file_count=stats["files"],
            )
        )
        total_bytes += int(stats["bytes"])
        total_files += int(stats["files"])

    return {
        "ok": True,
        "base_dir": base_dir,
        "snapshot_count": len(snaps),
        "total_bytes": total_bytes,
        "total_files": total_files,
        "snapshots": results,
    }


def _humanize_bytes(n: int) -> str:
    # Simple humanization to KiB, MiB, GiB
    step = 1024.0
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    f = float(n)
    for u in units:
        if f < step or u == units[-1]:
            if u == "B":
                return f"{int(f)} {u}"
            return f"{f:.2f} {u}"
        f /= step
    return f"{n} B"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="harvest-stats",
        description="Report size and file counts for signal harvester snapshots."
    )
    parser.add_argument("--base-dir", required=True, help="Snapshots base directory")
    parser.add_argument("--json", action="store_true", help="Output JSON to stdout")
    parser.add_argument(
        "--sort",
        choices=["name", "size", "files"],
        default="name",
        help="Sort snapshots by this field"
    )
    parser.add_argument("--desc", action="store_true", help="Sort descending")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of snapshots shown (0 = all)")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    configure_logging(args.log_level)

    try:
        res = compute_stats(args.base_dir)
    except Exception as e:
        log.error("Stats failed: %s", e)
        print("[FAIL] stats failed:", e)
        return 2

    snaps = list(res["snapshots"])
    if args.sort == "name":
        snaps.sort(key=lambda x: str(x["name"]), reverse=args.desc)
    elif args.sort == "size":
        snaps.sort(key=lambda x: int(x["size_bytes"]), reverse=args.desc)
    elif args.sort == "files":
        snaps.sort(key=lambda x: int(x["file_count"]), reverse=args.desc)

    if args.limit and args.limit > 0:
        snaps = snaps[: args.limit]

    if args.json:
        out = dict(res)
        out["snapshots"] = snaps
        print(json.dumps(out, indent=2))
        return 0

    # Human-readable output
    print(f"[OK] {res['snapshot_count']} snapshots")
    total_bytes = int(res.get('total_bytes', 0))
    total_files = int(res.get('total_files', 0))
    print(f"Total size: {_humanize_bytes(total_bytes)} across {total_files} files")
    for s in snaps:
        print(
            f"- {s['name']}: size={_humanize_bytes(int(s['size_bytes']))}, files={s['file_count']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
