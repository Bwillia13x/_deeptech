from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Optional

from .logger import get_logger
from .snapshot import existing_snapshots
from .xscore_utils import parse_datetime, urljoin

log = get_logger(__name__)

# Allowed file extensions for snapshots
ALLOWED_SNAPSHOT_EXTS = (
    ".json",
    ".ndjson", 
    ".csv",
)


def parse_snapshot_name(name: str) -> Optional[datetime]:
    """Parse a snapshot directory name (YYYY-MM-DD) to datetime."""
    try:
        return parse_datetime(name)
    except Exception:
        return None


def _write_file(path: str, content: str) -> None:
    """Write content to file, ensuring directory exists."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def build_robots_txt(base_dir: str, base_url: str) -> str:
    """Generate robots.txt pointing to sitemap."""
    sitemap_url = urljoin(base_url, "sitemap.xml")
    content = f"User-agent: *\nAllow: /\n\nSitemap: {sitemap_url}\n"
    path = os.path.join(base_dir, "robots.txt")
    _write_file(path, content)
    return path


def build_sitemap_xml(base_dir: str, base_url: str) -> str:
    """Generate sitemap.xml with snapshots and other files."""
    urls = []
    
    # Add main files
    for file in ["latest.json", "snapshots.json", "snapshots.atom"]:
        urls.append({
            "loc": urljoin(base_url, file),
            "lastmod": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
            "changefreq": "daily",
            "priority": "0.8"
        })
    
    # Add snapshot directories
    snapshots = existing_snapshots(base_dir)
    for snap in snapshots:
        urls.append({
            "loc": urljoin(base_url, snap + "/"),
            "lastmod": parse_datetime(snap).isoformat().replace("+00:00", "Z"),
            "changefreq": "weekly", 
            "priority": "0.5"
        })
    
    # Build XML
    xml_lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml_lines.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    
    for url in urls:
        xml_lines.append('  <url>')
        xml_lines.append(f'    <loc>{url["loc"]}</loc>')
        xml_lines.append(f'    <lastmod>{url["lastmod"]}</lastmod>')
        xml_lines.append(f'    <changefreq>{url["changefreq"]}</changefreq>')
        xml_lines.append(f'    <priority>{url["priority"]}</priority>')
        xml_lines.append('  </url>')
    
    xml_lines.append('</urlset>')
    
    content = '\n'.join(xml_lines) + '\n'
    path = os.path.join(base_dir, "sitemap.xml")
    _write_file(path, content)
    return path


def build_latest_json(base_dir: str) -> str:
    """Generate latest.json pointing to the most recent snapshot."""
    snapshots = existing_snapshots(base_dir)
    latest_data: dict[str, object] = {}
    if not snapshots:
        latest_data = {"latest": None, "snapshots": []}
    else:
        latest = snapshots[-1]
        latest_data = {
            "latest": {"name": latest, "url": latest + "/"},
            "snapshots": [{"name": snap, "url": snap + "/"} for snap in snapshots]
        }
    
    content = json.dumps(latest_data, ensure_ascii=False, indent=2)
    path = os.path.join(base_dir, "latest.json")
    _write_file(path, content)
    return path


def build_snapshots_json(base_dir: str) -> str:
    """Generate snapshots.json with metadata for all snapshots (JSON Feed format)."""
    snapshots = existing_snapshots(base_dir)
    feed_items = []
    
    for snap in reversed(snapshots[-20:]):  # Last 20 snapshots
        snap_dt = parse_datetime(snap)
        item: dict[str, object] = {
            "id": snap,
            "url": snap + "/",
            "title": f"Signal Harvester Snapshot {snap}",
            "content_text": f"Signal harvester snapshot for {snap}",
            "date_published": snap_dt.isoformat().replace("+00:00", "Z"),
        }
        
        # Add schema info if available
        schema_path = os.path.join(base_dir, snap, "schema.json")
        if os.path.exists(schema_path):
            try:
                with open(schema_path, "r", encoding="utf-8") as f:
                    schema = json.load(f)
                item["schema"] = schema
            except Exception as e:
                log.warning("Failed to read schema for %s: %s", snap, e)
        
        # Add file list
        snap_path = os.path.join(base_dir, snap)
        if os.path.isdir(snap_path):
            files = []
            for file in os.listdir(snap_path):
                if file != "checksums.json":
                    files.append(file)
            item["attachments"] = [{"url": str(file), "mime_type": "application/json"} for file in sorted(files)]
        
        feed_items.append(item)
    
    feed_data = {
        "version": "https://jsonfeed.org/version/1.1",
        "title": "Signal Harvester Snapshots",
        "home_page_url": "https://github.com/yourorg/signal-harvester",
        "feed_url": "snapshots.json",
        "items": feed_items
    }
    
    content = json.dumps(feed_data, ensure_ascii=False, indent=2)
    path = os.path.join(base_dir, "snapshots.json")
    _write_file(path, content)
    return path


def build_atom_feed(base_dir: str, base_url: str) -> str:
    """Generate Atom feed for snapshots."""
    snapshots = existing_snapshots(base_dir)
    
    feed_lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    feed_lines.append('<feed xmlns="http://www.w3.org/2005/Atom">')
    feed_lines.append('  <title>Signal Harvester Snapshots</title>')
    feed_lines.append(f'  <link href="{urljoin(base_url, "snapshots.atom")}" rel="self"/>')
    feed_lines.append(f'  <link href="{base_url}"/>')
    feed_lines.append(f'  <updated>{datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")}</updated>')
    feed_lines.append(f'  <id>{base_url}</id>')
    
    for snap in reversed(snapshots[-20:]):  # Last 20 snapshots
        snap_dt = parse_datetime(snap)
        feed_lines.append('  <entry>')
        feed_lines.append(f'    <title>Snapshot {snap}</title>')
        feed_lines.append(f'    <link href="{urljoin(base_url, snap + "/")}"/>')
        feed_lines.append(f'    <id>{urljoin(base_url, snap + "/")}</id>')
        feed_lines.append(f'    <updated>{snap_dt.isoformat().replace("+00:00", "Z")}</updated>')
        feed_lines.append(f'    <summary>Signal harvester snapshot for {snap}</summary>')
        feed_lines.append('  </entry>')
    
    feed_lines.append('</feed>')
    
    content = '\n'.join(feed_lines) + '\n'
    path = os.path.join(base_dir, "snapshots.atom")
    _write_file(path, content)
    return path


def build_all(
    base_dir: str,
    base_url: str,
    write_robots: bool = True,
    write_sitemap: bool = True,
    write_latest: bool = True,
    write_feeds: bool = True,
) -> dict[str, object]:
    """Build all site artifacts and return mapping of file type to path."""
    outputs = {}
    errors = []
    
    try:
        if write_robots:
            outputs["robots.txt"] = build_robots_txt(base_dir, base_url)
    except Exception as e:
        errors.append(f"Failed to build robots.txt: {e}")
    
    try:
        if write_sitemap:
            outputs["sitemap.xml"] = build_sitemap_xml(base_dir, base_url)
    except Exception as e:
        errors.append(f"Failed to build sitemap.xml: {e}")
    
    try:
        if write_latest:
            outputs["latest.json"] = build_latest_json(base_dir)
            outputs["snapshots.json"] = build_snapshots_json(base_dir)
    except Exception as e:
        errors.append(f"Failed to build latest files: {e}")
    
    try:
        if write_feeds:
            outputs["snapshots.atom"] = build_atom_feed(base_dir, base_url)
    except Exception as e:
        errors.append(f"Failed to build feeds: {e}")
    
    result: dict[str, object] = {"ok": len(errors) == 0, "outputs": outputs}
    if errors:
        result["errors"] = errors
    
    log.info("Built site artifacts: %s", ", ".join(str(k) for k in outputs.keys()))
    return result


def main() -> None:
    """Entry point for harvest-site console script."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Build site artifacts for signal harvester snapshots")
    parser.add_argument("--base-dir", required=True, help="Base directory containing snapshots")
    parser.add_argument("--base-url", required=True, help="Public base URL")
    parser.add_argument("--no-robots", action="store_true", help="Skip robots.txt")
    parser.add_argument("--no-sitemap", action="store_true", help="Skip sitemap.xml")
    parser.add_argument("--no-latest", action="store_true", help="Skip latest.json and snapshots.json")
    parser.add_argument("--no-feeds", action="store_true", help="Skip atom feed")
    
    args = parser.parse_args()
    
    result = build_all(
        base_dir=args.base_dir,
        base_url=args.base_url,
        write_robots=not args.no_robots,
        write_sitemap=not args.no_sitemap,
        write_latest=not args.no_latest,
        write_feeds=not args.no_feeds,
    )
    
    if result["ok"]:
        outputs = result["outputs"]
        if isinstance(outputs, dict):
            print(f"Built {len(outputs)} artifacts:")
            for name, path in outputs.items():
                print(f"  {name}: {path}")
    else:
        print("Build failed with errors:")
        errors = result.get("errors", [])
        if isinstance(errors, list):
            for error in errors:
                print(f"  {error}")
        raise SystemExit(1)
