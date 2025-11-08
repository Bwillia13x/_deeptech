from __future__ import annotations

import importlib
from typing import Dict, List, Optional

from .logger import get_logger

log = get_logger(__name__)


def _call_module_main(module_name: str, args: Optional[List[str]] = None, allow_missing: bool = True) -> int:
    """
    Try to import module and invoke its main(argv) with provided args list.
    Returns non-zero on failure to run. If allow_missing=True, a missing module
    (ModuleNotFoundError) is treated as success (rc=0) and logged at INFO.
    """
    try:
        mod = importlib.import_module(module_name)
    except ModuleNotFoundError as e:
        if allow_missing:
            log.info("Rebuild module not installed; skipping: %s", module_name)
            return 0
        log.warning("Rebuild module import failed (missing): %s (%s)", module_name, e)
        return 1
    except Exception as e:
        log.warning("Rebuild module import failed: %s (%s)", module_name, e)
        return 1

    main = getattr(mod, "main", None)
    if not callable(main):
        log.warning("Rebuild module has no callable main(): %s", module_name)
        return 1

    try:
        rc = main(args or [])
        return int(rc or 0)
    except SystemExit as se:
        code = getattr(se, "code", 1)
        return int(code or 0)
    except Exception:
        log.exception("Rebuild main() execution failed for %s", module_name)
        return 1


def run_rebuilds(
    base_dir: str,
    rebuild_site: bool = False,
    rebuild_html: bool = False,
    dry_run: bool = False,
    site_args: Optional[List[str]] = None,
    html_args: Optional[List[str]] = None,
    ignore_missing: bool = True,
) -> Dict[str, object]:
    """
    Best-effort rebuilds of site and/or HTML artifacts.
    Attempts to call signal_harvester.site and signal_harvester.html main functions with --base-dir + extra args.
    Does not raise on failure; returns a result dict with exit codes and errors.

    ignore_missing=True treats missing modules as non-errors (rc=0).
    """
    actions: List[str] = []
    errors: List[str] = []
    results: Dict[str, int] = {}
    site_args = list(site_args or [])
    html_args = list(html_args or [])

    if dry_run:
        if rebuild_site:
            actions.append("site")
        if rebuild_html:
            actions.append("html")
        return {
            "ok": True,
            "base_dir": base_dir,
            "dry_run": True,
            "actions": actions,
            "results": {},
            "errors": [],
            "site_args": site_args,
            "html_args": html_args,
            "ignore_missing": ignore_missing,
        }

    if rebuild_site:
        actions.append("site")
        argv = ["--base-dir", base_dir] + site_args
        rc = _call_module_main("signal_harvester.site", argv, allow_missing=ignore_missing)
        results["site"] = rc
        if rc != 0:
            errors.append(f"signal_harvester.site returned {rc}")
    if rebuild_html:
        actions.append("html")
        argv = ["--base-dir", base_dir] + html_args
        rc = _call_module_main("signal_harvester.html", argv, allow_missing=ignore_missing)
        results["html"] = rc
        if rc != 0:
            errors.append(f"signal_harvester.html returned {rc}")

    ok = len(errors) == 0
    if not actions:
        ok = True
    return {
        "ok": ok,
        "base_dir": base_dir,
        "dry_run": False,
        "actions": actions,
        "results": results,
        "errors": errors,
        "site_args": site_args,
        "html_args": html_args,
        "ignore_missing": ignore_missing,
    }
