from __future__ import annotations

import argparse
import hashlib
import json
import os
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

from .logger import configure_logging, get_logger
from .site import ALLOWED_SNAPSHOT_EXTS
from .snapshot import existing_snapshots
from .xscore_utils import urljoin

log = get_logger(__name__)


def _read_json(path: str) -> Optional[dict[str, object]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            return None
    except Exception as e:
        log.warning("failed to read JSON %s: %s", path, e)
        return None


def _compute_sha256(path: str, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk_size)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _list_snapshot_candidates(snapshot_dir: str) -> List[str]:
    root = snapshot_dir
    out: List[str] = []
    for dirpath, _, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        for fn in filenames:
            # Only include allowed extensions and common compressed variants
            if fn == "checksums.json":
                # Don't include self when verifying without a manifest
                continue
            ext = os.path.splitext(fn)[1].lower()
            if ext in ALLOWED_SNAPSHOT_EXTS or any(
                fn.endswith(suf) for suf in (".json.gz", ".ndjson.gz", ".csv.gz")
            ):
                rel_path = os.path.join(rel_dir, fn) if rel_dir != "." else fn
                out.append(rel_path.replace(os.sep, "/"))
    out.sort()
    return out


def _load_checksums_manifest(snapshot_dir: str) -> Optional[dict[str, object]]:
    p = os.path.join(snapshot_dir, "checksums.json")
    if not os.path.exists(p):
        return None
    return _read_json(p)


def _sha_field(it: dict[str, object]) -> Optional[str]:
    for k in ("sha256", "sha256_hex", "sha256sum"):
        v = it.get(k)
        if isinstance(v, str) and len(v) >= 32:
            return v
    return None


def verify_snapshot_dir(snapshot_dir: str) -> dict[str, object]:
    """
    Verify files within a snapshot directory against checksums.json if present.
    Returns a dict with ok, missing, changed, extra, stats.
    """
    manifest = _load_checksums_manifest(snapshot_dir)
    expected: Dict[str, Tuple[Optional[int], Optional[str]]] = {}
    if manifest:
        files = manifest.get("files")
        if isinstance(files, list):
            for it in files:
                if not isinstance(it, dict):
                    continue
                path = it.get("path")
                if not isinstance(path, str) or not path:
                    continue
                if path == "checksums.json":
                    # avoid self-reference
                    continue
                size = it.get("size") if isinstance(it.get("size"), int) else None
                sha = _sha_field(it)
                expected[path] = (size, sha)

    # If no manifest or empty, fall back to discovered files
    discovered = _list_snapshot_candidates(snapshot_dir)
    if not expected:
        for rel in discovered:
            expected[rel] = (None, None)

    missing: List[str] = []
    changed: List[str] = []
    ok = True

    for rel, (exp_size, exp_sha) in sorted(expected.items()):
        fspath = os.path.join(snapshot_dir, rel.replace("/", os.sep))
        if not os.path.exists(fspath):
            missing.append(rel)
            ok = False
            continue
        size = os.path.getsize(fspath)
        sha = _compute_sha256(fspath)
        mismatch = False
        if exp_size is not None and exp_size != size:
            mismatch = True
        if exp_sha and exp_sha.lower() != sha.lower():
            mismatch = True
        if mismatch and (exp_size is not None or exp_sha is not None):
            changed.append(rel)
            ok = False

    extra: List[str] = []
    if manifest:
        expected_set = set(expected.keys())
        for rel in discovered:
            if rel not in expected_set:
                extra.append(rel)

    return {
        "ok": ok,
        "missing": missing,
        "changed": changed,
        "extra": extra,
        "stats": {
            "checked": len(expected),
            "missing": len(missing),
            "changed": len(changed),
            "extra": len(extra),
        },
    }


def _load_latest_json(base_dir: str) -> tuple[Optional[dict[str, object]], Optional[str]]:
    p = os.path.join(base_dir, "latest.json")
    if not os.path.exists(p):
        return None, None
    data = _read_json(p)
    if not data:
        return None, None
    latest = data.get("latest")
    if not isinstance(latest, dict):
        return data, None
    name_value = latest.get("name")
    name = name_value if isinstance(name_value, str) else None
    return data, name


def verify_site(base_dir: str, base_url: Optional[str] = None) -> dict[str, object]:
    errors: List[str] = []
    warnings: List[str] = []
    ok = True

    latest_data, latest_name = _load_latest_json(base_dir)
    if not latest_data or not latest_name:
        errors.append("latest.json missing or invalid")
        return {"ok": False, "errors": errors, "warnings": warnings}

    # Validate latest snapshot directory exists
    latest_dir = os.path.join(base_dir, latest_name)
    if not os.path.isdir(latest_dir):
        errors.append(f"latest snapshot directory missing: {latest_dir}")
        ok = False

    # Validate files listed in latest.json exist (and checksum if provided)
    latest_entry = latest_data.get("latest")
    latest_files: list[object] = []
    if isinstance(latest_entry, dict):
        files_value = latest_entry.get("files")
        if isinstance(files_value, list):
            latest_files = files_value
    
    for it in latest_files:
        if not isinstance(it, dict):
            continue
        rel = it.get("path")
        if not rel or not isinstance(rel, str):
            continue
        fspath = os.path.join(latest_dir, rel.replace("/", os.sep))
        if not os.path.exists(fspath):
            errors.append(f"file listed in latest.json not found: {rel}")
            ok = False
            continue
        sha = _sha_field(it)
        if sha:
            actual = _compute_sha256(fspath)
            if actual.lower() != sha.lower():
                errors.append(f"checksum mismatch for {rel}")
                ok = False

    # Base URL
    bu: str | None = None
    if base_url:
        bu = base_url
    else:
        base_url_value = latest_data.get("base_url")
        if isinstance(base_url_value, str):
            bu = base_url_value
    
    # robots.txt
    robots_path = os.path.join(base_dir, "robots.txt")
    if os.path.exists(robots_path):
        try:
            with open(robots_path, "r", encoding="utf-8") as f:
                robots = f.read()
            if bu:
                expected = f"Sitemap: {urljoin(bu, 'sitemap.xml')}"
                if expected not in robots:
                    warnings.append("robots.txt missing Sitemap line for base_url")
        except Exception as e:
            warnings.append(f"failed to read robots.txt: {e}")
    else:
        warnings.append("robots.txt not found")

    # sitemap.xml
    sitemap_path = os.path.join(base_dir, "sitemap.xml")
    if os.path.exists(sitemap_path):
        try:
            tree = ET.parse(sitemap_path)
            root = tree.getroot()
            ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            urls = [el.text for el in root.findall(".//sm:loc", ns) if el.text]
            if bu:
                latest_json_url = urljoin(bu, "latest.json")
                if latest_json_url not in urls:
                    warnings.append("sitemap.xml missing latest.json URL")
                # Check presence of data.json for latest snapshot if present
                latest_data_json_url = urljoin(bu, f"{latest_name}/data.json")
                if latest_data_json_url not in urls:
                    warnings.append("sitemap.xml missing latest data.json URL")
        except Exception as e:
            errors.append(f"failed to parse sitemap.xml: {e}")
            ok = False
    else:
        warnings.append("sitemap.xml not found")

    # Feeds
    atom_path = os.path.join(base_dir, "snapshots.atom")
    jsonfeed_path = os.path.join(base_dir, "snapshots.json")
    if os.path.exists(atom_path):
        try:
            ET.parse(atom_path)
        except Exception as e:
            errors.append(f"invalid Atom feed: {e}")
            ok = False
    else:
        warnings.append("Atom feed not found")
    if os.path.exists(jsonfeed_path):
        jf = _read_json(jsonfeed_path)
        if not jf or "items" not in jf:
            errors.append("invalid JSON feed")
            ok = False
    else:
        warnings.append("JSON feed not found")

    return {"ok": ok and not errors, "errors": errors, "warnings": warnings}


def verify_snapshot(base_dir: str, snapshot_name: Optional[str] = None, latest: bool = False) -> dict[str, object]:
    snaps = existing_snapshots(base_dir)
    if not snaps:
        return {"ok": False, "errors": ["no snapshots found"]}
    if latest or not snapshot_name:
        snapshot_name = snaps[-1]
    if snapshot_name not in snaps:
        return {"ok": False, "errors": [f"snapshot not found: {snapshot_name}"]}
    snap_dir = os.path.join(base_dir, snapshot_name)
    return verify_snapshot_dir(snap_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="harvest-verify",
        description="Verify signal harvester snapshots and site artifacts."
    )
    parser.add_argument("--base-dir", required=True, help="Snapshots base directory")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--snapshot", help="Snapshot name to verify (e.g., 2025-02-01)")
    group.add_argument("--latest", action="store_true", help="Verify latest snapshot")
    parser.add_argument(
        "--site",
        action="store_true",
        help="Verify site artifacts (latest.json, sitemap, robots, feeds)"
    )
    parser.add_argument(
        "--base-url",
        help="Public base URL used for sitemap/robots validation"
    )
    parser.add_argument("--json", dest="as_json", action="store_true", help="Output JSON result")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    configure_logging(args.log_level)

    if args.site:
        res = verify_site(base_dir=args.base_dir, base_url=args.base_url)
    else:
        res = verify_snapshot(
            base_dir=args.base_dir,
            snapshot_name=args.snapshot,
            latest=args.latest or not args.snapshot
        )

    if args.as_json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        if res.get("ok"):
            print("[OK]")
        else:
            print("[FAIL]")
            for k in ("errors", "missing", "changed"):
                v = res.get(k)
                if isinstance(v, list) and v:
                    print(f"{k}:")
                    for it in v[:20]:
                        print(f"  - {it}")
    return 0 if res.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
