from __future__ import annotations

import argparse
import os
from typing import Optional

from .logger import configure_logging, get_logger
from .site import build_all
from .snapshot import rotate_snapshot
from .xscore_utils import parse_datetime

log = get_logger(__name__)


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="harvest-snapshot",
        description="Create a new snapshot from a source JSON file with shape {'rows': [...]}",
    )
    p.add_argument("--base-dir", required=True, help="Snapshots base directory")
    p.add_argument("--src", required=True, help="Path to source JSON file containing {'rows': [...]}")

    p.add_argument("--now", help="Snapshot datetime (ISO 8601). If only date is given, midnight UTC is assumed.")
    p.add_argument("--keep", type=int, default=10, help="Retention: keep this many recent snapshots (default: 10)")
    p.add_argument("--diff", action="store_true", help="Generate a diff vs the previous snapshot")
    p.add_argument("--no-gzip", action="store_true", help="Disable gzip variants for generated files")
    p.add_argument("--no-csv", action="store_true", help="Do not write CSV/CSV.gz")
    p.add_argument("--no-ndjson", action="store_true", help="Do not write NDJSON/NDJSON.gz")
    p.add_argument("--no-schema", action="store_true", help="Do not write schema.json")
    p.add_argument("--no-checksums", action="store_true", help="Do not write checksums.json")

    p.add_argument("--update-site", action="store_true", help="After snapshot, update site artifacts")
    p.add_argument("--base-url", help="Public base URL (required if --update-site)")

    p.add_argument("--log-level", default="INFO")

    args = p.parse_args(argv)
    configure_logging(args.log_level)

    if args.update_site and not args.base_url:
        p.error("--base-url is required when using --update-site")

    if not os.path.exists(args.src):
        p.error(f"source JSON not found: {args.src}")

    now_dt = parse_datetime(args.now) if args.now else parse_datetime(None)

    root = rotate_snapshot(
        base_dir=args.base_dir,
        src=args.src,
        now=now_dt,
        keep=args.keep,
        gzip_copy=not args.no_gzip,
        generate_diff=args.diff,
        write_ndjson=not args.no_ndjson,
        gzip_ndjson=not args.no_gzip and not args.no_ndjson,
        write_csv=not args.no_csv,
        gzip_csv=not args.no_gzip and not args.no_csv,
        write_diff_json=True,
        gzip_diff_json=not args.no_gzip,
        write_checksums_file=not args.no_checksums,
        write_schema_files=not args.no_schema,
    )
    print(f"snapshot created: {root}")

    if args.update_site:
        result = build_all(
            base_dir=args.base_dir,
            base_url=args.base_url,
            write_robots=True,
            write_sitemap=True,
            write_latest=True,
            write_feeds=True,
        )
        if result["ok"]:
            outputs = result["outputs"]
            if isinstance(outputs, dict):
                print(f"updated site artifacts: {', '.join(sorted(str(k) for k in outputs.keys()))}")
        else:
            errors = result.get("errors", [])
            print(f"site build failed: {errors}")
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
