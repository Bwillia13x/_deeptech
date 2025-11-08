from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Mapping, Optional, Set, Tuple, Union, cast

from .logger import configure_logging, get_logger
from .prune import PruneResult, prune_snapshots
from .remove import delete_snapshots_by_name
from .stats import StatsResult, _humanize_bytes, compute_stats

log = get_logger(__name__)





DUR_RE = re.compile(r"(?P<num>\d+(?:\.\d+)?)(?P<unit>[smhdw])", re.IGNORECASE)



# Accept multiple common timestamp formats with optional Z

def _parse_iso8601(s: str) -> datetime:

    s = s.strip()

    if s.endswith("Z"):

        s = s[:-1] + "+00:00"

    try:

        dt = datetime.fromisoformat(s)

    except Exception:

        try:

            dt = datetime.strptime(s, "%Y-%m-%d")

        except Exception as e:

            raise ValueError(f"invalid ISO-8601 timestamp: {s!r}") from e

    if dt.tzinfo is None:

        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)





def parse_duration(s: str) -> timedelta:

    if not s or not isinstance(s, str):

        raise ValueError("duration must be a non-empty string")

    total = 0.0

    matched = False

    for m in DUR_RE.finditer(s):

        matched = True

        num = float(m.group("num"))

        unit = m.group("unit").lower()

        if unit == "s":

            total += num

        elif unit == "m":

            total += num * 60

        elif unit == "h":

            total += num * 3600

        elif unit == "d":

            total += num * 86400

        elif unit == "w":

            total += num * 7 * 86400

    if not matched:

        raise ValueError(f"invalid duration: {s!r}")

    if total < 0:

        raise ValueError("duration must be non-negative")

    return timedelta(seconds=total)





def _parse_time_or_duration(s: str, now: Optional[datetime]) -> datetime:

    """

    Parse either an ISO-8601 timestamp or a duration like '48h'.

    For durations, returns (now - duration). 'now' defaults to UTC now if None.

    """

    if not s:

        raise ValueError("empty value")

    try:

        return _parse_iso8601(s)

    except Exception:

        td = parse_duration(s)

        now = now or datetime.now(timezone.utc)

        return (now - td).astimezone(timezone.utc)





# Try to extract a datetime for a snapshot

_NAME_TS_RE = re.compile(

    r"""

    (?P<year>20\d{2})

    [-_]?

    (?P<month>\d{2})

    [-_]?

    (?P<day>\d{2})

    (?:

        [Tt _-]?

        (?P<hour>\d{2})

        (?:

            [:_-]?

            (?P<minute>\d{2})

            (?:

                [:_-]?

                (?P<second>\d{2})

            )?

        )?

        (?:Z|[+-]\d{2}:?\d{2})?

    )?

    """,

    re.VERBOSE,

)





def _parse_dt_from_name(name: str) -> Optional[datetime]:

    m = _NAME_TS_RE.search(name)

    if not m:

        return None

    year = int(m.group("year"))

    month = int(m.group("month"))

    day = int(m.group("day"))

    hour = int(m.group("hour") or 0)

    minute = int(m.group("minute") or 0)

    second = int(m.group("second") or 0)

    try:

        return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)

    except Exception:

        return None





def _snapshot_dt(snap: Dict[str, object]) -> Optional[datetime]:

    # Try multiple keys commonly used for timestamps

    for key in ("created_at", "timestamp", "ts", "datetime", "snapshot_created_at"):

        if key in snap and snap[key]:

            val = snap[key]

            if isinstance(val, (int, float)):

                return datetime.fromtimestamp(float(val), tz=timezone.utc)

            if isinstance(val, str):

                try:

                    return _parse_iso8601(val)

                except Exception:

                    pass

    # Fallback to parse from name

    name = str(snap.get("name") or "")

    if name:

        return _parse_dt_from_name(name)

    return None





def _floor_hour(dt: datetime) -> Tuple[int, int, int, int]:

    return dt.year, dt.month, dt.day, dt.hour





def _floor_day(dt: datetime) -> Tuple[int, int, int]:

    return dt.year, dt.month, dt.day





def _week_key(dt: datetime) -> Tuple[int, int]:

    iso = dt.isocalendar()

    return iso[0], iso[1]  # iso_year, iso_week





def _month_key(dt: datetime) -> Tuple[int, int]:

    return dt.year, dt.month





def _year_key(dt: datetime) -> int:

    return dt.year





# Type aliases for GFS tuple keys
HourlyKey = Tuple[int, int, int, int]
DailyKey = Tuple[int, int, int]
WeekKey = Tuple[int, int]
MonthKey = Tuple[int, int]
YearKey = int
GFSKey = Union[HourlyKey, DailyKey, WeekKey, MonthKey, YearKey]


def _compute_gfs_keep_names(

    snaps: List[Dict[str, object]],

    dts: List[datetime],

    keep_hourly: int,

    keep_daily: int,

    keep_weekly: int,

    keep_monthly: int,

    keep_yearly: int,

    hourly_since: Optional[datetime] = None,

    daily_since: Optional[datetime] = None,

    weekly_since: Optional[datetime] = None,

    monthly_since: Optional[datetime] = None,

    yearly_since: Optional[datetime] = None,

) -> Set[str]:

    """

    Compute a set of snapshot names to keep under GFS/calendar retention.

    Scans newest->oldest, picking the newest snapshot for each distinct

    hour/day/week/month/year bucket up to the requested counts.

    Optional per-level windows limit consideration to snapshots with dt >= *_since.

    """

    keep: Set[str] = set()

    if all(x <= 0 for x in (keep_hourly, keep_daily, keep_weekly, keep_monthly, keep_yearly)):

        return keep



    seen_hour: Set[Tuple[int, int, int, int]] = set()

    seen_day: Set[Tuple[int, int, int]] = set()

    seen_week: Set[Tuple[int, int]] = set()

    seen_month: Set[Tuple[int, int]] = set()

    seen_year: Set[int] = set()



    for idx in range(len(snaps) - 1, -1, -1):

        s = snaps[idx]

        dt = dts[idx]

        name = str(s.get("name"))



        selected = False

        if keep_hourly > 0:

            if hourly_since is None or dt >= hourly_since:

                hour_key = _floor_hour(dt)
                if hour_key not in seen_hour and len(seen_hour) < keep_hourly:

                    seen_hour.add(hour_key)

                    selected = True

        if keep_daily > 0:

            if daily_since is None or dt >= daily_since:

                day_key = _floor_day(dt)
                if day_key not in seen_day and len(seen_day) < keep_daily:

                    seen_day.add(day_key)

                    selected = True

        if keep_weekly > 0:

            if weekly_since is None or dt >= weekly_since:

                week_key = _week_key(dt)
                if week_key not in seen_week and len(seen_week) < keep_weekly:

                    seen_week.add(week_key)

                    selected = True

        if keep_monthly > 0:

            if monthly_since is None or dt >= monthly_since:

                month_key = _month_key(dt)
                if month_key not in seen_month and len(seen_month) < keep_monthly:

                    seen_month.add(month_key)

                    selected = True

        if keep_yearly > 0:

            if yearly_since is None or dt >= yearly_since:

                year_key = _year_key(dt)
                if year_key not in seen_year and len(seen_year) < keep_yearly:

                    seen_year.add(year_key)

                    selected = True



        if selected:

            keep.add(name)



    return keep





def _snap_dir_from_info(base_dir: str, info: Dict[str, object], name: str) -> str:

    candidates = []

    for key in ("dir", "snapshot_dir", "path"):

        v = info.get(key)

        if isinstance(v, str):

            candidates.append(v)

    candidates.append(os.path.join(base_dir, "snapshots", name))

    for c in candidates:

        if os.path.isdir(c):

            return c

    return candidates[-1]





def _dir_size(path: str) -> int:

    total = 0

    try:

        for root, dirs, files in os.walk(path):

            for f in files:

                fp = os.path.join(root, f)

                try:

                    total += os.path.getsize(fp)

                except OSError:

                    continue

    except Exception:

        return 0

    return total





def _snapshot_entries(stats: Mapping[str, object]) -> list[Dict[str, object]]:

    snaps = stats.get("snapshots")

    if isinstance(snaps, list):

        return [cast(Dict[str, object], s) for s in snaps if isinstance(s, dict)]

    return []



def _estimate_plan_bytes_by_name(base_dir: str, stats_before: Dict[str, object], names: List[str]) -> Dict[str, int]:

    snaps = _snapshot_entries(stats_before)

    name_to_info = {str(s.get("name")): s for s in snaps}

    out: Dict[str, int] = {}

    for n in names:

        info = name_to_info.get(n)

        sz = 0

        if info:

            for key in ("bytes", "size_bytes", "total_bytes", "size"):

                v = info.get(key) if isinstance(info, dict) else None

                if isinstance(v, int):

                    sz = int(v)

                    break

                if isinstance(v, float):

                    sz = int(v)

                    break

            else:

                dpath = _snap_dir_from_info(base_dir, info, n)

                if os.path.isdir(dpath):

                    sz = _dir_size(dpath)

        out[n] = int(sz)

    return out





def compute_retain_plan(

    base_dir: str,

    keep_age: Optional[timedelta] = None,

    since: Optional[datetime] = None,

    keep_min: int = 0,

    now: Optional[datetime] = None,

    keep_hourly: int = 0,

    keep_daily: int = 0,

    keep_weekly: int = 0,

    keep_monthly: int = 0,

    keep_yearly: int = 0,

    # Calendar windows

    calendar_since: Optional[datetime] = None,

    hourly_since: Optional[datetime] = None,

    daily_since: Optional[datetime] = None,

    weekly_since: Optional[datetime] = None,

    monthly_since: Optional[datetime] = None,

    yearly_since: Optional[datetime] = None,

) -> Dict[str, object]:

    """

    Plan which snapshots to remove to enforce retention.

    Supports:

      - Time-based (TTL): keep_age or since

      - Calendar-based (GFS): keep_hourly/daily/weekly/monthly/yearly

      - Optional calendar windows: calendar_since (global) and/or per-level *_since

      - keep_min: minimum number of newest snapshots to always keep



    Returns dict:

      - ok: bool

      - base_dir

      - before: stats dict

      - plan_keep: int

      - planned_remove: [names]

      - retention: {...}

      - blocked_by_keep_min: bool

      - delete_by_names: bool

    """

    if keep_min < 0:

        keep_min = 0



    any_calendar = any(x and x > 0 for x in (keep_hourly, keep_daily, keep_weekly, keep_monthly, keep_yearly))

    any_ttl = (keep_age is not None) or (since is not None)



    if not any_ttl and not any_calendar:

        raise ValueError(
            "At least one of keep-age/since or calendar retention "
            "(keep-hourly/daily/weekly/monthly/yearly) must be provided"
        )



    if since is None and keep_age is not None:

        now = now or datetime.now(timezone.utc)

        since = now - keep_age

    if since is not None:

        if since.tzinfo is None:

            since = since.replace(tzinfo=timezone.utc)

        since = since.astimezone(timezone.utc)



    # Normalize calendar windows, if provided

    def _norm(dt: Optional[datetime]) -> Optional[datetime]:

        if dt is None:

            return None

        if dt.tzinfo is None:

            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)



    calendar_since = _norm(calendar_since)

    hourly_since = _norm(hourly_since)

    daily_since = _norm(daily_since)

    weekly_since = _norm(weekly_since)

    monthly_since = _norm(monthly_since)

    yearly_since = _norm(yearly_since)



    # Apply global calendar_since as a floor to each level

    def _max_dt(a: Optional[datetime], b: Optional[datetime]) -> Optional[datetime]:

        if a is None:

            return b

        if b is None:

            return a

        return a if a > b else b



    hourly_since_eff = _max_dt(calendar_since, hourly_since)

    daily_since_eff = _max_dt(calendar_since, daily_since)

    weekly_since_eff = _max_dt(calendar_since, weekly_since)

    monthly_since_eff = _max_dt(calendar_since, monthly_since)

    yearly_since_eff = _max_dt(calendar_since, yearly_since)



    stats: StatsResult = compute_stats(base_dir)

    snaps = _snapshot_entries(stats)

    count = len(snaps)



    dts_optional: List[Optional[datetime]] = [_snapshot_dt(s) for s in snaps]

    if any(dt is None for dt in dts_optional):

        missing = [snaps[i].get("name") for i, dt in enumerate(dts_optional) if dt is None]

        raise ValueError(

            f"Unable to determine timestamp for snapshots: {', '.join(map(str, missing))}. "

            "Ensure snapshot names or stats include timestamps."

        )

    dts: List[datetime] = [dt for dt in dts_optional if dt is not None]



    ttl_keep: Set[str] = set()

    if since is not None:

        for i, dt in enumerate(dts):

            if dt is not None and dt >= since:

                ttl_keep.add(str(snaps[i].get("name")))



    gfs_keep: Set[str] = _compute_gfs_keep_names(

        snaps=snaps,

        dts=dts,

        keep_hourly=max(0, int(keep_hourly)),

        keep_daily=max(0, int(keep_daily)),

        keep_weekly=max(0, int(keep_weekly)),

        keep_monthly=max(0, int(keep_monthly)),

        keep_yearly=max(0, int(keep_yearly)),

        hourly_since=hourly_since_eff,

        daily_since=daily_since_eff,

        weekly_since=weekly_since_eff,

        monthly_since=monthly_since_eff,

        yearly_since=yearly_since_eff,

    ) if any_calendar else set()



    keepmin_keep: Set[str] = set()

    if keep_min > 0 and count > 0:

        start = max(0, count - keep_min)

        keepmin_keep = {str(snaps[i].get("name")) for i in range(start, count)}



    natural_keep = ttl_keep.union(gfs_keep)

    keep_names = set(natural_keep).union(keepmin_keep)



    planned_remove = [str(snaps[i]["name"]) for i in range(count) if str(snaps[i]["name"]) not in keep_names]

    plan_keep = count - len(planned_remove)



    removed_indices = [i for i in range(count) if str(snaps[i]["name"]) in planned_remove]

    contiguous_oldest = removed_indices == list(range(0, len(removed_indices)))



    blocked = False

    if keep_min > 0 and len(natural_keep) < keep_min and count >= keep_min:

        blocked = True



    return {

        "ok": True,

        "base_dir": base_dir,

        "before": stats,

        "plan_keep": plan_keep,

        "planned_remove": planned_remove,

        "retention": {

            "keep_age_seconds": int(keep_age.total_seconds()) if keep_age is not None else None,

            "since": since.isoformat() if since is not None else None,

            "keep_min": keep_min,

            "keep_hourly": int(keep_hourly),

            "keep_daily": int(keep_daily),

            "keep_weekly": int(keep_weekly),

            "keep_monthly": int(keep_monthly),

            "keep_yearly": int(keep_yearly),

            "calendar_since": calendar_since.isoformat() if calendar_since is not None else None,

            "hourly_since": hourly_since_eff.isoformat() if hourly_since_eff is not None else None,

            "daily_since": daily_since_eff.isoformat() if daily_since_eff is not None else None,

            "weekly_since": weekly_since_eff.isoformat() if weekly_since_eff is not None else None,

            "monthly_since": monthly_since_eff.isoformat() if monthly_since_eff is not None else None,

            "yearly_since": yearly_since_eff.isoformat() if yearly_since_eff is not None else None,

        },

        "blocked_by_keep_min": blocked,

        "delete_by_names": not contiguous_oldest,

    }





def apply_retain(

    base_dir: str,

    keep_age: Optional[timedelta] = None,

    since: Optional[datetime] = None,

    keep_min: int = 0,

    now: Optional[datetime] = None,

    keep_hourly: int = 0,

    keep_daily: int = 0,

    keep_weekly: int = 0,

    keep_monthly: int = 0,

    keep_yearly: int = 0,

    dry_run: bool = True,

    rebuild_site: bool = False,

    rebuild_html: bool = False,

    site_args: Optional[List[str]] = None,

    html_args: Optional[List[str]] = None,

    ignore_missing_rebuilds: bool = True,

    *,

    # Calendar windows

    calendar_since: Optional[datetime] = None,

    hourly_since: Optional[datetime] = None,

    daily_since: Optional[datetime] = None,

    weekly_since: Optional[datetime] = None,

    monthly_since: Optional[datetime] = None,

    yearly_since: Optional[datetime] = None,

) -> Dict[str, object]:

    """

    Apply retention by pruning snapshots based on TTL and/or calendar retention.

    Uses prune_snapshots when the plan is a contiguous oldest block; otherwise

    deletes by explicit names.

    """

    plan = compute_retain_plan(

        base_dir=base_dir,

        keep_age=keep_age,

        since=since,

        keep_min=keep_min,

        now=now,

        keep_hourly=keep_hourly,

        keep_daily=keep_daily,

        keep_weekly=keep_weekly,

        keep_monthly=keep_monthly,

        keep_yearly=keep_yearly,

        calendar_since=calendar_since,

        hourly_since=hourly_since,

        daily_since=daily_since,

        weekly_since=weekly_since,

        monthly_since=monthly_since,

        yearly_since=yearly_since,

    )

    keep = int(cast(int, plan["plan_keep"]))

    planned_remove = list(cast(List[str], plan["planned_remove"]))

    delete_by_names = bool(plan.get("delete_by_names"))



    before_stats = cast(Dict[str, object], plan["before"])

    plan_bytes_by_name = _estimate_plan_bytes_by_name(base_dir, before_stats, planned_remove) if planned_remove else {}

    plan_bytes = sum(plan_bytes_by_name.values()) if plan_bytes_by_name else 0



    removed: List[str] = []

    op_result: Optional[Union[PruneResult, Dict[str, object]]] = None



    if planned_remove and not dry_run:

        if delete_by_names:

            op_result = delete_snapshots_by_name(

                base_dir,

                planned_remove,

                dry_run=False,

                rebuild_site=rebuild_site,

                rebuild_html=rebuild_html,

                site_args=site_args,

                html_args=html_args,

                ignore_missing_rebuilds=ignore_missing_rebuilds,

            )

            if isinstance(op_result, dict):

                removed_value = op_result.get("removed", [])

                if isinstance(removed_value, list):

                    removed = [str(r) for r in removed_value]

        else:

            res = prune_snapshots(

                base_dir,

                keep=keep,

                dry_run=False,

                rebuild_site=rebuild_site,

                rebuild_html=rebuild_html,

                site_args=site_args,

                html_args=html_args,

                ignore_missing_rebuilds=ignore_missing_rebuilds,

            )

            op_result = res

            removed = [str(r) for r in res["removed"]]



    after_stats = compute_stats(base_dir) if not dry_run else None

    reclaimed_bytes = 0

    if after_stats:

        before_total = before_stats.get("total_bytes")

        after_total = after_stats.get("total_bytes")

        try:

            if isinstance(before_total, (int, float)) and isinstance(after_total, (int, float)):

                reclaimed_bytes = int(before_total) - int(after_total)

        except Exception:

            reclaimed_bytes = 0

        if reclaimed_bytes < 0:

            reclaimed_bytes = 0



    return {

        "ok": True,

        "base_dir": base_dir,

        "dry_run": dry_run,

        "retention": plan["retention"],

        "before": before_stats,

        "after": after_stats,

        "plan_keep": keep,

        "planned_remove": planned_remove,

        "plan_bytes": int(plan_bytes),

        "plan_bytes_by_name": plan_bytes_by_name,

        "removed": removed,

        "reclaimed_bytes": int(reclaimed_bytes),

        "blocked_by_keep_min": plan["blocked_by_keep_min"],

        "delete_by_names": delete_by_names,

        "operation_result": op_result,

    }





def main(argv: Optional[List[str]] = None) -> int:

    parser = argparse.ArgumentParser(

        prog="harvest-retain",

        description="Prune snapshots to enforce TTL and/or calendar (GFS) retention."

    )

    parser.add_argument("--base-dir", required=True, help="Snapshots base directory")



    # TTL options

    group = parser.add_mutually_exclusive_group(required=False)

    group.add_argument("--keep-age", help="Keep snapshots newer than this age (e.g., 30d, 12h, 1w2d)")

    group.add_argument("--since", help="Keep snapshots with timestamp >= this ISO time (e.g., 2025-03-01T00:00:00Z)")



    # Calendar (GFS) options

    parser.add_argument("--keep-hourly", type=int, default=0, help="Keep the latest N hourly snapshots (one per "
                                     "distinct hour)")

    parser.add_argument("--keep-daily", type=int, default=0, help="Keep the latest N daily snapshots (one per "
                                    "day)")

    parser.add_argument("--keep-weekly", type=int, default=0, help="Keep the latest N weekly snapshots (one per "
                                     "ISO week)")

    parser.add_argument("--keep-monthly", type=int, default=0, help="Keep the latest N monthly snapshots (one per "
                                      "month)")

    parser.add_argument("--keep-yearly", type=int, default=0, help="Keep the latest N yearly snapshots (one per "
                                     "year)")



    # Calendar windows (accept ISO-8601 or duration like 48h)

    parser.add_argument("--calendar-since", help="Apply calendar selection only to snapshots with "
                                      "timestamp >= this (ISO or duration)")

    parser.add_argument("--hourly-since", help="Apply hourly selection only to snapshots with "
                                  "timestamp >= this (ISO or duration)")

    parser.add_argument("--daily-since", help="Apply daily selection only to snapshots with "
                                 "timestamp >= this (ISO or duration)")

    parser.add_argument("--weekly-since", help="Apply weekly selection only to snapshots with "
                                  "timestamp >= this (ISO or duration)")

    parser.add_argument("--monthly-since", help="Apply monthly selection only to snapshots with "
                                   "timestamp >= this (ISO or duration)")

    parser.add_argument("--yearly-since", help="Apply yearly selection only to snapshots with "
                                  "timestamp >= this (ISO or duration)")



    parser.add_argument("--keep-min", type=int, default=0, help="Minimum number of snapshots to always keep (newest)")

    parser.add_argument("--now", help="Override 'now' for tests or reproducibility (ISO-8601, default UTC now)")



    # Output and apply

    parser.add_argument("--json", action="store_true", help="Output JSON to stdout")

    parser.add_argument("--force", action="store_true", help="Apply changes (default is dry-run)")



    # Rebuild controls

    parser.add_argument("--rebuild-site", action="store_true", help="Rebuild site index after pruning")

    parser.add_argument("--rebuild-html", action="store_true", help="Rebuild HTML after pruning")

    parser.add_argument("--site-arg", action="append", default=[], help="Extra arg for site rebuild "
                                  "(repeatable)")

    parser.add_argument("--html-arg", action="append", default=[], help="Extra arg for HTML rebuild "
                                   "(repeatable)")

    parser.add_argument("--ignore-missing-rebuilds", action="store_true", default=True,
                        help="Skip rebuild steps if modules are missing")



    parser.add_argument("--log-level", default="INFO")

    args = parser.parse_args(argv)



    configure_logging(args.log_level)



    now: Optional[datetime] = None

    if args.now:

        try:

            now = _parse_iso8601(args.now)

        except Exception as e:

            log.error("Invalid --now: %s", e)

            print("[FAIL] invalid --now:", e)

            return 2



    keep_age_td: Optional[timedelta] = None

    since_dt: Optional[datetime] = None

    if args.keep_age:

        try:

            keep_age_td = parse_duration(args.keep_age)

        except ValueError as e:

            log.error("Invalid --keep-age: %s", e)

            print("[FAIL] invalid --keep-age:", e)

            return 2

    if args.since:

        try:

            since_dt = _parse_iso8601(args.since)

        except ValueError as e:

            log.error("Invalid --since: %s", e)

            print("[FAIL] invalid --since:", e)

            return 2



    # Calendar windows parsing

    def _parse_opt_time_or_duration(val: Optional[str]) -> Optional[datetime]:

        if not val:

            return None

        try:

            return _parse_time_or_duration(val, now)

        except Exception as e:

            raise ValueError(str(e))



    try:

        cal_since_dt = _parse_opt_time_or_duration(args.calendar_since)

        hourly_since_dt = _parse_opt_time_or_duration(args.hourly_since)

        daily_since_dt = _parse_opt_time_or_duration(args.daily_since)

        weekly_since_dt = _parse_opt_time_or_duration(args.weekly_since)

        monthly_since_dt = _parse_opt_time_or_duration(args.monthly_since)

        yearly_since_dt = _parse_opt_time_or_duration(args.yearly_since)

    except ValueError as e:

        print("[FAIL] invalid calendar window:", e)

        return 2



    # Validate at least one policy provided

    keep_args = [
        args.keep_hourly,
        args.keep_daily,
        args.keep_weekly,
        args.keep_monthly,
        args.keep_yearly
    ]
    if not (keep_age_td or since_dt or any(x > 0 for x in keep_args)):

        print(
            "[FAIL] must provide keep-age/since and/or at least one of "
            "--keep-hourly/--keep-daily/--keep-weekly/--keep-monthly/--keep-yearly"
        )

        return 2



    dry_run = not args.force



    try:

        res = apply_retain(

            base_dir=args.base_dir,

            keep_age=keep_age_td,

            since=since_dt,

            keep_min=args.keep_min,

            now=now,

            keep_hourly=args.keep_hourly,

            keep_daily=args.keep_daily,

            keep_weekly=args.keep_weekly,

            keep_monthly=args.keep_monthly,

            keep_yearly=args.keep_yearly,

            dry_run=dry_run,

            rebuild_site=args.rebuild_site,

            rebuild_html=args.rebuild_html,

            site_args=args.site_arg or [],

            html_args=args.html_arg or [],

            ignore_missing_rebuilds=args.ignore_missing_rebuilds,

            calendar_since=cal_since_dt,

            hourly_since=hourly_since_dt,

            daily_since=daily_since_dt,

            weekly_since=weekly_since_dt,

            monthly_since=monthly_since_dt,

            yearly_since=yearly_since_dt,

        )

    except Exception as e:

        log.exception("Retention application failed")

        print("[FAIL] retention failed:", e)

        return 2



    before = cast(Dict[str, object], res["before"])

    after = cast(Optional[Dict[str, object]], res["after"])

    planned = cast(List[str], res["planned_remove"])

    removed = cast(List[str], res["removed"])

    blocked = bool(res["blocked_by_keep_min"])

    retention = cast(Dict[str, object], res["retention"])

    plan_bytes = int(cast(int, res.get("plan_bytes") or 0))

    reclaimed_bytes = int(cast(int, res.get("reclaimed_bytes") or 0))



    if args.json:

        print(json.dumps(res, indent=2, default=str))

        return 0



    def ttl_str() -> str:

        parts = []

        if retention.get("keep_age_seconds") is not None:

            secs = int(cast(int, retention["keep_age_seconds"]))

            parts.append(f"keep_age={secs}s")

        if retention.get("since") is not None:

            parts.append(f"since={cast(str, retention['since'])}")

        return ", ".join(parts) if parts else "none"



    def cal_counts_str() -> str:

        c = retention

        parts = []

        for key in ("keep_hourly", "keep_daily", "keep_weekly", "keep_monthly", "keep_yearly"):

            v = int(cast(int, c.get(key) or 0))

            if v > 0:

                parts.append(f"{key.replace('keep_', '')}={v}")

        return ", ".join(parts) if parts else "none"



    def cal_windows_str() -> str:

        c = retention

        parts = []

        m = [

            ("H", "hourly_since"),

            ("D", "daily_since"),

            ("W", "weekly_since"),

            ("M", "monthly_since"),

            ("Y", "yearly_since"),

        ]

        for label, key in m:

            v = c.get(key)

            if v:

                parts.append(f"{label}>={cast(str, v)}")

        if c.get("calendar_since"):

            parts.insert(0, f"global>={cast(str, c['calendar_since'])}")

        return ", ".join(parts) if parts else "none"



    before_count = int(cast(int, before['snapshot_count']))
    before_size = _humanize_bytes(int(cast(int, before['total_bytes'])))
    before_files = int(cast(int, before['total_files']))
    print(f"[OK] Before: {before_count} snapshots, total size {before_size}, files {before_files}")

    print(f"TTL: {ttl_str()} | Calendar: {cal_counts_str()} | keep_min={int(cast(int, retention['keep_min']))}")

    win_s = cal_windows_str()

    if win_s != "none":

        print(f"Calendar windows: {win_s}")



    if not planned:

        if blocked:

            print("[WARN] Nothing pruned due to keep_min.")

        else:

            print("[OK] Retention already satisfied; nothing to prune.")

        return 0



    plan_bytes_str = _humanize_bytes(plan_bytes) if plan_bytes > 0 else "unknown"

    print(f"Plan: remove {len(planned)} snapshots (~{plan_bytes_str}) -> keep {int(cast(int, res['plan_keep']))}")

    if dry_run:

        print("[DRY-RUN] Would remove:", ", ".join(planned))

        return 0



    print("[APPLY] Removed:", ", ".join(removed))

    if reclaimed_bytes > 0:

        print(f"[APPLY] Reclaimed approx {_humanize_bytes(reclaimed_bytes)}")

    if after:

        print(

            f"[OK] After: {int(cast(int, after['snapshot_count']))} snapshots, "

            f"total size {_humanize_bytes(int(cast(int, after['total_bytes'])))}, "

            f"files {int(cast(int, after['total_files']))}"

        )



    if blocked:

        print("[WARN] Some removals were blocked by keep_min.")

    return 0





if __name__ == "__main__":

    raise SystemExit(main())
