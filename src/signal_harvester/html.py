from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from typing import Dict, List, Optional, Tuple, TypedDict

from .logger import configure_logging, get_logger
from .snapshot import existing_snapshots
from .xscore_utils import urljoin


class HTMLBuildResult(TypedDict):
    ok: bool
    files: list[str]

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


def _human_bytes(n: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    s = float(n)
    for u in units:
        if s < 1024 or u == units[-1]:
            if u == "B":
                return f"{int(s)} {u}"
            return f"{s:.1f} {u}"
        s /= 1024
    return f"{int(n)} B"


def _fmt_date(name: str) -> str:
    # Expect YYYY-MM-DD
    try:
        d = dt.datetime.strptime(name, "%Y-%m-%d").date()
        return d.isoformat()
    except Exception:
        return name


def _file_exists(path: str) -> bool:
    try:
        return os.path.exists(path)
    except Exception:
        return False


def _gather_snapshot_links(base_dir: str, snap_name: str) -> dict[str, str]:
    # Return mapping label -> relative path that exists
    rels = {
        "JSON": f"{snap_name}/data.json",
        "NDJSON": f"{snap_name}/data.ndjson",
        "NDJSON.gz": f"{snap_name}/data.ndjson.gz",
        "CSV": f"{snap_name}/data.csv",
        "CSV.gz": f"{snap_name}/data.csv.gz",
        "Diff JSON": f"{snap_name}/diff.json",
        "Diff JSON.gz": f"{snap_name}/diff.json.gz",
        "Checksums": f"{snap_name}/checksums.json",
    }
    out: Dict[str, str] = {}
    for label, rel in rels.items():
        if _file_exists(os.path.join(base_dir, rel.replace("/", os.sep))):
            out[label] = rel
    return out


def _sum_manifest_size(path: str) -> int | None:
    data = _read_json(path)
    if not data:
        return None
    files = data.get("files")
    if files is None or not isinstance(files, list):
        return None
    total = 0
    any_sizes = False
    for it in files:
        if isinstance(it, dict) and isinstance(it.get("size"), int):
            total += it["size"]
            any_sizes = True
    return total if any_sizes else None


def _render_index_html(
    title: str,
    base_url: Optional[str],
    latest_name: Optional[str],
    snapshots: List[str],
    rows: List[Tuple[str, Dict[str, str], Optional[int]]],
) -> str:
    def href(rel: str) -> str:
        return urljoin(base_url, rel) if base_url else rel

    feed_atom = href("snapshots.atom")
    feed_json = href("snapshots.json")
    sitemap = href("sitemap.xml")
    latest_json = href("latest.json")

    head = f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="alternate" type="application/atom+xml" title="Snapshots Atom" href="{feed_atom}">
<link rel="alternate" type="application/feed+json" title="Snapshots JSON" href="{feed_json}">
<style>
:root {{
  --fg: #222;
  --muted: #666;
  --bg: #fff;
  --accent: #0d6efd;
  --row: #f8f9fa;
}}
html, body {{ 
        margin: 0; padding: 0; background: var(--bg); color: var(--fg); 
        font-family: system-ui, -apple-system, Segoe UI, Roboto, "Helvetica Neue", Arial, 
                    "Noto Sans", "Liberation Sans", "Apple Color Emoji", "Segoe UI Emoji", 
                    "Segoe UI Symbol", "Noto Color Emoji", sans-serif; 
    }}
a {{ color: var(--accent); text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.container {{ max-width: 1100px; margin: 0 auto; padding: 1.5rem; }}
h1 {{ font-size: 1.5rem; margin: 0 0 0.5rem 0; }}
p.meta {{ color: var(--muted); margin: 0.25rem 0 1rem 0; }}
table {{ width: 100%; border-collapse: collapse; }}
th, td {{ padding: 0.5rem; border-bottom: 1px solid #e9ecef; vertical-align: top; }}
tbody tr:nth-child(even) {{ background: var(--row); }}
.badge {{ 
        display: inline-block; padding: 0.15rem 0.4rem; font-size: 0.8rem; 
        border: 1px solid #ddd; border-radius: 6px; color: #333; background: #f1f3f5; 
    }}
.small {{ color: var(--muted); font-size: 0.9rem; }}
footer {{ margin-top: 1.5rem; color: var(--muted); font-size: 0.9rem; }}
</style>
<body>
<div class="container">
<header>
  <h1>{title}</h1>
  <p class="meta">
    Latest: {latest_name or "-"} ·
    <a href="{latest_json}">latest.json</a> ·
    <a href="{feed_atom}">Atom</a> ·
    <a href="{feed_json}">JSON Feed</a> ·
    <a href="{sitemap}">sitemap.xml</a>
  </p>
</header>
<section>
<table>
  <thead>
    <tr><th>Date</th><th>Files</th><th class="small">Total size</th></tr>
  </thead>
  <tbody>
"""

    body_parts = []
    for snap, links, total_size in rows:
        link_strs = []
        for label, rel in links.items():
            link_strs.append(f'<a href="{href(rel)}">{label}</a>')
        files_html = " · ".join(link_strs) if link_strs else '<span class="small">no files</span>'
        total_html = _human_bytes(total_size) if total_size is not None else "-"
        badge = ' <span class="badge">latest</span>' if latest_name == snap else ""
        snap_href = href(snap + "/")
        fmt_snap = _fmt_date(snap)
        date_link = f'<a href="{snap_href}">{fmt_snap}</a>{badge}'
        row_html = f'<tr><td>{date_link}</td><td>{files_html}</td><td class="small">{total_html}</td></tr>'
        body_parts.append(f'    {row_html}')
        fmt_snap = _fmt_date(snap)
        date_link = f'<a href="{snap_href}">{fmt_snap}</a>{badge}'


    foot = """  </tbody>
</table>
</section>
<footer>
  Generated by signal-harvester-html.
</footer>
</div>
</body>
</html>
"""
    return head + "\n".join(body_parts) + foot


def _render_snapshot_html(title: str, snap_name: str, base_url: str | None, links: dict[str, str]) -> str:
    def href(rel: str) -> str:
        return urljoin(base_url, rel) if base_url else rel

    items = []
    for label, rel in links.items():
        items.append(f'<li><a href="{href(rel)}">{label}</a></li>')

    return f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · {snap_name}</title>
<style>
body {{ margin: 0; padding: 1.5rem; font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; }}
a {{ color: #0d6efd; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.container {{ max-width: 800px; margin: 0 auto; }}
h1 {{ font-size: 1.4rem; margin: 0 0 1rem 0; }}
</style>
<body>
<div class="container">
  <p><a href="../">⬅ Back</a></p>
  <h1>{title} · {snap_name}</h1>
  <ul>
    {"".join(items) if items else '<li><em>No files</em></li>'}
  </ul>
</div>
</body>
</html>
"""


def build_html(
    base_dir: str,
    base_url: str | None = None,
    write_index: bool = True,
    write_snapshot_pages: bool = True,
    site_title: str = "Signal Harvester Snapshots",
) -> HTMLBuildResult:
    snaps = existing_snapshots(base_dir)
    latest_name = snaps[-1] if snaps else None

    rows: List[Tuple[str, Dict[str, str], Optional[int]]] = []
    for snap in snaps:
        links = _gather_snapshot_links(base_dir, snap)
        total_size = None
        manifest_path = os.path.join(base_dir, snap, "checksums.json")
        if _file_exists(manifest_path):
            total_size = _sum_manifest_size(manifest_path)
        rows.append((snap, links, total_size))

    written: List[str] = []
    ok = True

    if write_index:
        index_html = _render_index_html(site_title, base_url, latest_name, snaps, rows)
        out_path = os.path.join(base_dir, "index.html")
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(index_html)
            written.append("index.html")
        except Exception as e:
            ok = False
            log.error("failed to write %s: %s", out_path, e)

    if write_snapshot_pages:
        for snap, links, _ in rows:
            html = _render_snapshot_html(site_title, snap, base_url, links)
            out_dir = os.path.join(base_dir, snap)
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, "index.html")
            try:
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(html)
                written.append(f"{snap}/index.html")
            except Exception as e:
                ok = False
                log.error("failed to write %s: %s", out_path, e)

    return {"ok": ok, "files": written}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="harvest-html",
        description="Generate minimal HTML index and snapshot pages for signal harvester snapshots."
    )
    parser.add_argument("--base-dir", required=True, help="Snapshots base directory")
    parser.add_argument("--base-url", help="Public base URL for absolute links")
    parser.add_argument("--no-index", action="store_true", help="Do not write top-level index.html")
    parser.add_argument("--no-snapshot-pages", action="store_true", help="Do not write per-snapshot index.html pages")
    parser.add_argument("--title", default="Signal Harvester Snapshots", help="Site title")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    configure_logging(args.log_level)

    res = build_html(
        base_dir=args.base_dir,
        base_url=args.base_url,
        write_index=not args.no_index,
        write_snapshot_pages=not args.no_snapshot_pages,
        site_title=args.title,
    )
    if res.get("ok"):
        print("[OK] HTML written:", ", ".join(res.get("files", [])))
        return 0
    else:
        print("[FAIL] HTML generation failed")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
