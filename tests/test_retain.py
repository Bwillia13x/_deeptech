from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone, timedelta

from signal_harvester.snapshot import rotate_snapshot
from signal_harvester.stats import compute_stats
from signal_harvester.retain import parse_duration, compute_retain_plan, apply_retain, main as retain_main


class TestRetain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _write_src(self, rows, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"rows": rows}, f)

    def _make_snapshots(self, base_url: str):
        # Create three daily snapshots 2025-03-01, 02, 03
        day1 = datetime(2025, 3, 1, tzinfo=timezone.utc)
        rows1 = [{"username": "a", "user_id": "1", "overall": 0.6, "letter_grade": "B", "followers_count": 100, "tweet_count": 10, "score_created_at": "2025-03-01T00:00:00Z"}]
        src1 = os.path.join(self.base, "in1.json")
        self._write_src(rows1, src1)
        rotate_snapshot(
            base_dir=self.base,
            src=src1,
            now=day1,
            keep=10,
            gzip_copy=True,
            generate_diff=False,
            write_ndjson=True,
            gzip_ndjson=True,
            write_csv=True,
            gzip_csv=True,
            write_checksums_file=True,
            write_schema_files=True,
        )

        day2 = day1 + timedelta(days=1)
        rows2 = [{"username": "b", "user_id": "2", "overall": 0.8, "letter_grade": "A", "followers_count": 200, "tweet_count": 20, "score_created_at": "2025-03-02T00:00:00Z"}]
        src2 = os.path.join(self.base, "in2.json")
        self._write_src(rows2, src2)
        rotate_snapshot(
            base_dir=self.base,
            src=src2,
            now=day2,
            keep=10,
            gzip_copy=True,
            generate_diff=True,
            write_ndjson=True,
            gzip_ndjson=True,
            write_csv=True,
            gzip_csv=True,
            write_diff_json=True,
            gzip_diff_json=True,
            write_checksums_file=True,
            write_schema_files=True,
        )

        day3 = day2 + timedelta(days=1)
        rows3 = [{"username": "c", "user_id": "3", "overall": 0.3, "letter_grade": "C", "followers_count": 50, "tweet_count": 5, "score_created_at": "2025-03-03T00:00:00Z"}]
        src3 = os.path.join(self.base, "in3.json")
        self._write_src(rows3, src3)
        rotate_snapshot(
            base_dir=self.base,
            src=src3,
            now=day3,
            keep=10,
            gzip_copy=True,
            generate_diff=True,
            write_ndjson=True,
            gzip_ndjson=True,
            write_csv=True,
            gzip_csv=True,
            write_diff_json=True,
            gzip_diff_json=True,
            write_checksums_file=True,
            write_schema_files=True,
        )

        return day1, day2, day3

    def _make_calendar_snapshots(self, base_url: str):
        # Build snapshots across multiple hours and days:
        #  - 2025-03-01 12:00
        #  - 2025-03-02 12:00
        #  - 2025-03-03 00:00, 01:00, 02:00
        base_t = datetime(2025, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
        dts = [
            base_t,
            base_t + timedelta(days=1),
            base_t + timedelta(days=2),
            base_t + timedelta(days=2, hours=1),
            base_t + timedelta(days=2, hours=2),
        ]
        for i, dt in enumerate(dts):
            rows = [{"username": f"user{i}", "user_id": str(i), "overall": 0.5, "letter_grade": "B", "followers_count": 100 + i, "tweet_count": 10 + i, "score_created_at": dt.isoformat()}]
            src = os.path.join(self.base, f"cal{i}.json")
            self._write_src(rows, src)
            rotate_snapshot(
                base_dir=self.base,
                src=src,
                now=dt,
                keep=20,
                gzip_copy=True,
                generate_diff=(i > 0),
                diff_direction="all" if i > 0 else None,
                write_ndjson=True,
                gzip_ndjson=True,
                write_csv=True,
                gzip_csv=True,
                write_diff_json=(i > 0),
                gzip_diff_json=(i > 0),
                write_checksums_file=True,
                write_schema_files=True,
            )
        # Return the "now" we'll use for retention planning (2025-03-03 03:00Z)
        return base_t + timedelta(days=2, hours=3)

    def test_parse_duration(self):
        self.assertEqual(parse_duration("60s"), timedelta(seconds=60))
        self.assertEqual(parse_duration("90m"), timedelta(minutes=90))
        self.assertEqual(parse_duration("12h"), timedelta(hours=12))
        self.assertEqual(parse_duration("2d"), timedelta(days=2))
        self.assertEqual(parse_duration("1w2d3h"), timedelta(weeks=1, days=2, hours=3))

    def test_retain_keep_age_dry_run_and_apply(self):
        base_url = "https://example.test/snapshots"
        day1, day2, day3 = self._make_snapshots(base_url)

        stats_before = compute_stats(self.base)
        snaps = stats_before["snapshots"]
        self.assertEqual(len(snaps), 3)

        # Use now at day3 noon; keep last 1.5 days -> keeps day2 and day3, removes day1
        now = day3 + timedelta(hours=12)
        keep_age = timedelta(days=1, hours=12)

        plan = compute_retain_plan(self.base, keep_age=keep_age, now=now, keep_min=0)
        self.assertTrue(plan["ok"])
        self.assertEqual(plan["plan_keep"], 2)
        self.assertEqual(len(plan["planned_remove"]), 1)
        self.assertFalse(plan["delete_by_names"])

        # Dry run
        res_dry = apply_retain(self.base, keep_age=keep_age, now=now, keep_min=0, dry_run=True)
        self.assertTrue(res_dry["ok"])
        self.assertTrue(res_dry["dry_run"])
        self.assertEqual(len(res_dry["planned_remove"]), 1)
        self.assertEqual(len(res_dry["removed"]), 0)

        # Apply
        res_apply = apply_retain(self.base, keep_age=keep_age, now=now, keep_min=0, dry_run=False)
        self.assertTrue(res_apply["ok"])
        self.assertFalse(res_apply["dry_run"])
        self.assertEqual(len(res_apply["removed"]), 1)

        stats_after = compute_stats(self.base)
        self.assertEqual(stats_after["snapshot_count"], 2)

        # CLI run (force), use --keep-age with explicit --now for deterministic behavior
        rc = retain_main(["--base-dir", self.base, "--keep-age", "36h", "--now", now.isoformat(), "--force"])
        self.assertEqual(rc, 0)

        # CLI run (JSON, dry-run)
        rc_json = retain_main(["--base-dir", self.base, "--keep-age", "36h", "--now", now.isoformat(), "--json"])
        self.assertEqual(rc_json, 0)

    def test_keep_min_blocks(self):
        base_url = "https://example.test/snapshots"
        day1, day2, day3 = self._make_snapshots(base_url)

        # keep_age extremely small but keep_min prevents any removal
        now = day3 + timedelta(hours=12)
        keep_age = timedelta(seconds=1)
        res = apply_retain(self.base, keep_age=keep_age, now=now, keep_min=3, dry_run=False)
        self.assertTrue(res["ok"])
        self.assertTrue(res["blocked_by_keep_min"])
        self.assertEqual(len(res["removed"]), 0)

    def test_calendar_gfs_retention_non_contiguous(self):
        base_url = "https://example.test/snapshots"
        # Create daily snapshots across multiple days
        #  - 2025-03-01, 2025-03-02, 2025-03-03, 2025-03-04, 2025-03-05
        base_t = datetime(2025, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
        dts = [
            base_t,
            base_t + timedelta(days=1),
            base_t + timedelta(days=2),
            base_t + timedelta(days=3),
            base_t + timedelta(days=4),
        ]
        for i, dt in enumerate(dts):
            rows = [{"username": f"user{i}", "user_id": str(i), "overall": 0.5, "letter_grade": "B", "followers_count": 100 + i, "tweet_count": 10 + i, "score_created_at": dt.isoformat()}]
            src = os.path.join(self.base, f"cal{i}.json")
            self._write_src(rows, src)
            rotate_snapshot(
                base_dir=self.base,
                src=src,
                now=dt,
                keep=20,
                gzip_copy=True,
                generate_diff=(i > 0),
                diff_direction="all" if i > 0 else None,
                write_ndjson=True,
                gzip_ndjson=True,
                write_csv=True,
                gzip_csv=True,
                write_diff_json=(i > 0),
                gzip_diff_json=(i > 0),
                write_checksums_file=True,
                write_schema_files=True,
            )
        
        stats_before = compute_stats(self.base)
        self.assertEqual(stats_before["snapshot_count"], 5)

        # Keep last 2 daily snapshots. Expect to keep:
        # - 2025-03-05, 2025-03-04
        # Remove:
        # - 2025-03-01, 2025-03-02, 2025-03-03
        plan = compute_retain_plan(
            base_dir=self.base,
            keep_hourly=0,
            keep_daily=2,
            keep_weekly=0,
            keep_monthly=0,
            keep_yearly=0,
            keep_min=0,
        )
        self.assertTrue(plan["ok"])
        self.assertEqual(plan["plan_keep"], 2)
        self.assertEqual(len(plan["planned_remove"]), 3)
        self.assertFalse(plan["delete_by_names"])  # This is contiguous oldest block

        # Apply (contiguous deletion via prune_snapshots)
        res_apply = apply_retain(
            base_dir=self.base,
            keep_daily=2,
            dry_run=False,
        )
        self.assertTrue(res_apply["ok"])
        self.assertEqual(len(res_apply["removed"]), 3)

        stats_after = compute_stats(self.base)
        self.assertEqual(stats_after["snapshot_count"], 2)

        # CLI run (force)
        rc = retain_main(["--base-dir", self.base, "--keep-daily", "2", "--force"])
        self.assertEqual(rc, 0)

        # CLI run (JSON, dry-run)
        rc_json = retain_main(["--base-dir", self.base, "--keep-daily", "2", "--json"])
        self.assertEqual(rc_json, 0)


if __name__ == "__main__":
    unittest.main()
