from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone, timedelta

from signal_harvester.snapshot import rotate_snapshot
from signal_harvester.stats import compute_stats
from signal_harvester.quota import parse_size_to_bytes, compute_quota_plan, apply_quota, main as quota_main


class TestQuota(unittest.TestCase):
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
        day1 = datetime(2025, 3, 1, tzinfo=timezone.utc)
        rows1 = [
            {"username": "alice", "user_id": "1", "overall": 0.6, "letter_grade": "B", "followers_count": 100, "tweet_count": 10, "score_created_at": "2025-03-01T00:00:00Z"},
        ]
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
        rows2 = [
            {"username": "bob", "user_id": "2", "overall": 0.8, "letter_grade": "A", "followers_count": 200, "tweet_count": 20, "score_created_at": "2025-03-02T00:00:00Z"},
        ]
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
        rows3 = [
            {"username": "carol", "user_id": "0", "overall": 0.3, "letter_grade": "o", "followers_count": 50, "tweet_count": 5, "score_created_at": "2025-03-03T00:00:00Z"},
        ]
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

    def test_parse_size(self):
        self.assertEqual(parse_size_to_bytes("1"), 1)
        self.assertEqual(parse_size_to_bytes("1K"), 1000)
        self.assertEqual(parse_size_to_bytes("1KB"), 1000)
        self.assertEqual(parse_size_to_bytes("1KiB"), 1024)
        self.assertEqual(parse_size_to_bytes("1MB"), 1_000_000)
        self.assertEqual(parse_size_to_bytes("1MiB"), 1_048_576)
        self.assertEqual(parse_size_to_bytes("2.5MiB"), 2_621_440)

    def test_quota_by_bytes_dry_run_and_apply(self):
        base_url = "https://example.test/snapshots"
        self._make_snapshots(base_url)

        stats_before = compute_stats(self.base)
        snaps = stats_before["snapshots"]
        self.assertEqual(len(snaps), 3)

        oldest = snaps[0]
        total = int(stats_before["total_bytes"])
        s_oldest = int(oldest["size_bytes"])

        # Set threshold so removing exactly the oldest snapshot satisfies quota
        max_bytes = total - s_oldest

        plan = compute_quota_plan(self.base, max_bytes=max_bytes, keep_min=0)
        self.assertTrue(plan["ok"])
        self.assertEqual(plan["plan_keep"], 2)
        self.assertEqual(len(plan["planned_remove"]), 1)
        self.assertTrue(plan["quota_satisfied_after_plan"])

        # Dry run
        res_dry = apply_quota(self.base, max_bytes=max_bytes, keep_min=0, dry_run=True)
        self.assertTrue(res_dry["ok"])
        self.assertTrue(res_dry["dry_run"])
        self.assertEqual(len(res_dry["planned_remove"]), 1)
        self.assertEqual(len(res_dry["removed"]), 0)

        # Apply
        res_apply = apply_quota(self.base, max_bytes=max_bytes, keep_min=0, dry_run=False)
        self.assertTrue(res_apply["ok"])
        self.assertFalse(res_apply["dry_run"])
        self.assertEqual(len(res_apply["removed"]), 1)

        stats_after = compute_stats(self.base)
        self.assertEqual(stats_after["snapshot_count"], 2)
        self.assertLessEqual(int(stats_after["total_bytes"]), max_bytes)

        # CLI run (force)
        rc = quota_main(["--base-dir", self.base, "--max-bytes", str(max_bytes), "--force"])
        self.assertEqual(rc, 0)

        # CLI run (JSON, dry-run)
        rc_json = quota_main(["--base-dir", self.base, "--max-bytes", str(max_bytes), "--json"])
        self.assertEqual(rc_json, 0)

    def test_keep_min_blocks(self):
        base_url = "https://example.test/snapshots"
        self._make_snapshots(base_url)

        stats_before = compute_stats(self.base)
        snaps = stats_before["snapshots"]
        self.assertEqual(len(snaps), 3)

        # Force a quota lower than current but keep_min prevents any removal
        max_bytes = int(stats_before["total_bytes"]) - 1
        res = apply_quota(self.base, max_bytes=max_bytes, keep_min=3, dry_run=False)
        self.assertTrue(res["ok"])
        self.assertTrue(res["blocked_by_keep_min"])
        self.assertEqual(len(res["removed"]), 0)
        # Still not satisfied because keep_min blocked removals
        self.assertFalse(res["quota_satisfied_after_plan"])


if __name__ == "__main__":
    unittest.main()
