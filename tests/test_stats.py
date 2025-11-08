from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone, timedelta

from signal_harvester.snapshot import rotate_snapshot
from signal_harvester.site import existing_snapshots
from signal_harvester.stats import compute_stats, main as stats_main
from signal_harvester.prune import prune_snapshots


class TestStats(unittest.TestCase):
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
            {"username": "carol", "user_id": "3", "overall": 0.3, "letter_grade": "C", "followers_count": 50, "tweet_count": 5, "score_created_at": "2025-03-03T00:00:00Z"},
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

    def test_stats_and_integration_with_prune(self):
        base_url = "https://example.test/snapshots"
        self._make_snapshots(base_url)

        snaps = existing_snapshots(self.base)
        self.assertEqual(len(snaps), 3)

        # Compute stats before prune
        stats_before = compute_stats(self.base)
        self.assertTrue(stats_before["ok"])
        self.assertEqual(stats_before["snapshot_count"], 3)
        self.assertGreater(stats_before["total_bytes"], 0)
        self.assertGreater(stats_before["total_files"], 0)
        self.assertEqual(len(stats_before["snapshots"]), 3)
        for s in stats_before["snapshots"]:
            self.assertIn("name", s)
            self.assertIn("size_bytes", s)
            self.assertIn("file_count", s)
            self.assertGreaterEqual(s["file_count"], 1)

        # Prune one oldest snapshot
        res = prune_snapshots(self.base, keep=2, dry_run=False, rebuild_site=False, rebuild_html=False)
        self.assertTrue(res["ok"])
        self.assertEqual(len(res["removed"]), 1)

        # Stats should reflect removal
        stats_after = compute_stats(self.base)
        self.assertEqual(stats_after["snapshot_count"], 2)
        self.assertEqual(len(stats_after["snapshots"]), 2)
        self.assertLess(stats_after["total_bytes"], stats_before["total_bytes"])

        # CLI run (basic)
        rc = stats_main(["--base-dir", self.base])
        self.assertEqual(rc, 0)

        # CLI run (JSON)
        rc_json = stats_main(["--base-dir", self.base, "--json"])
        self.assertEqual(rc_json, 0)


if __name__ == "__main__":
    unittest.main()
