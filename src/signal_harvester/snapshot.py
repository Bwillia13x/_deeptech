from __future__ import annotations

import csv
import gzip
import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

from . import integrity as _integrity  # BUGFIX: import module to avoid name clash
from .logger import get_logger
from .xscore_utils import parse_datetime

__all__ = ["existing_snapshots", "rotate_snapshot"]

log = get_logger(__name__)


def _snap_name_from_dt(ts: datetime) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.date().isoformat()


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _read_rows_from_src(src: str) -> List[Dict[str, object]]:
    with open(src, "r", encoding="utf-8") as f:
        data = json.load(f)
    rows = data.get("rows", [])
    if not isinstance(rows, list):
        raise ValueError("source JSON missing 'rows' list")
    return rows


def _write_json(path: str, obj: object) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _gzip_copy(in_path: str, out_path: str) -> None:
    with open(in_path, "rb") as fin, gzip.open(out_path, "wb") as fout:
        while True:
            chunk = fin.read(1024 * 1024)
            if not chunk:
                break
            fout.write(chunk)


def _write_ndjson(path: str, rows: List[Dict[str, object]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False))
            f.write("\n")


def _write_csv(path: str, rows: List[Dict[str, object]]) -> None:
    keys_set: set[str] = set()
    for r in rows:
        keys_set.update(r.keys())
    headers = sorted(keys_set)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in headers})


def _write_schema(path: str, rows: List[Dict[str, object]]) -> None:
    props: Dict[str, Dict[str, object]] = {}
    types_map: Dict[type, str] = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        dict: "object",
        list: "array",
        type(None): "null",
    }
    sample = {}
    for r in rows:
        for k, v in r.items():
            if k not in sample:
                sample[k] = v

    for k, v in sample.items():
        t = types_map.get(type(v), "string")
        props[k] = {"type": t}

    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Signal Harvester Snapshot Rows",
        "type": "array",
        "items": {
            "type": "object",
            "properties": props,
            "additionalProperties": True,
        },
    }
    _write_json(path, schema)


def _collect_files_for_manifest(root: str) -> List[str]:
    allowed_suffixes = (
        ".json",
        ".json.gz",
        ".ndjson",
        ".ndjson.gz",
        ".csv",
        ".csv.gz",
    )
    out: List[str] = []
    for dirpath, _, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        for fn in filenames:
            if fn == "checksums.json":
                continue
            if not any(fn.endswith(suf) for suf in allowed_suffixes):
                continue
            rel = os.path.join(rel_dir, fn) if rel_dir != "." else fn
            out.append(rel.replace(os.sep, "/"))
    out.sort()
    return out


def _diff_rows(
    prev_rows: List[Dict[str, object]],
    curr_rows: List[Dict[str, object]],
    key: str = "tweet_id",
) -> Dict[str, object]:
    prev_index: Dict[str, Dict[str, object]] = {str(r.get(key)): r for r in prev_rows if key in r}
    curr_index: Dict[str, Dict[str, object]] = {str(r.get(key)): r for r in curr_rows if key in r}

    added = []
    removed = []
    changed = []

    for k in curr_index.keys() - prev_index.keys():
        added.append(curr_index[k])
    for k in prev_index.keys() - curr_index.keys():
        removed.append(prev_index[k])

    for k in curr_index.keys() & prev_index.keys():
        a = curr_index[k]
        b = prev_index[k]
        if a != b:
            changed.append({"before": b, "after": a})

    return {"added": added, "removed": removed, "changed": changed}


def existing_snapshots(base_dir: str) -> List[str]:
    """Return sorted list of existing snapshot directory names (YYYY-MM-DD format)."""
    if not os.path.isdir(base_dir):
        return []
    
    snapshots = []
    for name in os.listdir(base_dir):
        if os.path.isdir(os.path.join(base_dir, name)):
            try:
                # Validate it's a date format
                parse_datetime(name)
                snapshots.append(name)
            except Exception:
                continue
    
    return sorted(snapshots)


def rotate_snapshot(
    base_dir: str,
    src: str,
    now: datetime,
    keep: int = 10,
    gzip_copy: bool = True,
    generate_diff: bool = False,
    diff_direction: str = "all",
    update_index: bool = False,  # unused placeholder
    write_ndjson: bool = True,
    gzip_ndjson: bool = True,
    write_csv: bool = True,
    gzip_csv: bool = True,
    write_diff_json: bool = True,
    gzip_diff_json: bool = True,
    write_checksums_file: bool = True,  # parameter name kept for backward compat
    write_schema_files: bool = True,
    write_robots_file: bool = False,  # deprecated here; use site.build_all
    base_url: Optional[str] = None,  # deprecated here; use site.build_all
    write_sitemap_xml: bool = False,  # deprecated here; use site.build_all
    write_feeds_files: bool = False,  # deprecated here; use site.build_all
) -> str:
    os.makedirs(base_dir, exist_ok=True)
    name = _snap_name_from_dt(now)
    root = os.path.join(base_dir, name)
    _ensure_dir(root)

    rows = _read_rows_from_src(src)

    data_json = os.path.join(root, "data.json")
    _write_json(data_json, {"rows": rows})
    if gzip_copy:
        _gzip_copy(data_json, data_json + ".gz")

    if write_ndjson:
        ndjson_path = os.path.join(root, "data.ndjson")
        _write_ndjson(ndjson_path, rows)
        if gzip_ndjson:
            _gzip_copy(ndjson_path, ndjson_path + ".gz")

    if write_csv:
        csv_path = os.path.join(root, "data.csv")
        _write_csv(csv_path, rows)
        if gzip_csv:
            _gzip_copy(csv_path, csv_path + ".gz")

    if write_schema_files:
        schema_path = os.path.join(root, "schema.json")
        _write_schema(schema_path, rows)

    if write_checksums_file:
        files_for_manifest = _collect_files_for_manifest(root)
        _integrity.write_checksums_file(root, files=files_for_manifest)  # use module to avoid name clash

    if generate_diff:
        snaps = existing_snapshots(base_dir)
        prev: Optional[str] = None
        if len(snaps) >= 2 and snaps[-1] == name:
            prev = snaps[-2]
        elif len(snaps) >= 1 and snaps[-1] != name:
            prev = snaps[-1]

        if prev:
            try:
                prev_rows = _read_rows_from_src(os.path.join(base_dir, prev, "data.json"))
                curr_rows = rows
                diff = _diff_rows(prev_rows, curr_rows)
                ddir = os.path.join(base_dir, "diffs")
                _ensure_dir(ddir)
                diff_name = f"{name}__vs__{prev}.json"
                diff_path = os.path.join(ddir, diff_name)
                with open(diff_path, "w", encoding="utf-8") as f:
                    json.dump(diff, f, ensure_ascii=False, indent=2)
                if gzip_diff_json:
                    _gzip_copy(diff_path, diff_path + ".gz")
            except Exception as e:
                log.warning("Failed to generate diff: %s", e)

    if keep and keep > 0:
        snaps = existing_snapshots(base_dir)
        extra = max(0, len(snaps) - keep)
        for old in snaps[:extra]:
            try:
                if old == name:
                    continue
                old_root = os.path.join(base_dir, old)
                for dirpath, dirnames, filenames in os.walk(old_root, topdown=False):
                    for fn in filenames:
                        try:
                            os.remove(os.path.join(dirpath, fn))
                        except Exception:
                            pass
                    for dn in dirnames:
                        try:
                            os.rmdir(os.path.join(dirpath, dn))
                        except Exception:
                            pass
                os.rmdir(old_root)
                log.info("Removed old snapshot %s due to retention policy", old)
            except Exception as e:
                log.warning("Failed to delete old snapshot %s: %s", old, e)

    return root
