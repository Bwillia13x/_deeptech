from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone, timedelta

from signal_harvester.snapshot import rotate_snapshot
from signal_harvester.site import build_all, existing_snapshots
from signal_harvester.html import build_html
from signal_harvester.prune import prune_snapshots, main as prune_main


class TestPrune(unittest.TestCase):
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
        day1 = datetime(2025, 2, 1, tzinfo=timezone.utc)
        rows1 = [
            {"username": "alice", "user_id": "1", "overall": 0.6, "letter_grade": "B", "followers_count": 100, "tweet_count": 10, "score_created_at": "2025-02-01T00:00:00Z"},
            {"username": "bob", "user_id": "2", "overall": 0.7, "letter_grade": "A", "followers_count": 200, "tweet_count": 20, "score_created_at": "2025-02-01T00:00:00Z"},
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
            {"username": "alice", "user_id": "1", "overall": 0.9, "letter_grade": "A", "followers_count": 150, "tweet_count": 12, "score_created_at": "2025-02-02T00:00:00Z"},
            {"username": "carol", "user_id": "3", "overall": 0.4, "letter_grade": "C", "followers_count": 50, "tweet_count": 5, "score_created_at": "2025-02-02T00:00:00Z"},
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
            {"username": "dave", "user_id": "4", "overall": 0.2, "letter_grade": "D", "followers_count": 10, "tweet_count": 1, "score_created_at": "2025-02-03T00:00:00Z"},
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

    def test_prune_dry_run_and_apply(self):
        base_url = "https://example.test/snapshots"
        self._make_snapshots(base_url)

        # Build site and HTML before pruning
        build_all(base_dir=self.base, base_url=base_url, write_robots=True, write_sitemap=True, write_latest=True, write_feeds=True)
        build_html(base_dir=self.base, base_url=base_url, write_index=True, write_snapshot_pages=True, site_title="Signal Harvester Snapshots")

        snaps = existing_snapshots(self.base)
        self.assertEqual(len(snaps), 3)

        # Dry-run prune to keep only 1 snapshot
        res_dry = prune_snapshots(self.base, keep=1, dry_run=True, rebuild_site=True, rebuild_html=True, 
                                  site_args=["--base-url", base_url], html_args=["--base-url", base_url])
        self.assertTrue(res_dry["ok"])
        self.assertEqual(len(res_dry["planned_remove"]), 2)
        self.assertEqual(len(res_dry["removed"]), 0)  # Nothing actually removed in dry-run
        self.assertGreater(res_dry["freed_bytes"], 0)

        # Ensure nothing removed during dry run
        snaps_after_dry = existing_snapshots(self.base)
        self.assertEqual(snaps_after_dry, snaps)

        # Apply prune to keep 2 newest, rebuild artifacts
        res = prune_snapshots(self.base, keep=2, dry_run=False, rebuild_site=True, rebuild_html=True,
                              site_args=["--base-url", base_url], html_args=["--base-url", base_url])
        self.assertTrue(res["ok"])
        self.assertEqual(len(res["removed"]), 1)
        self.assertEqual(len(existing_snapshots(self.base)), 2)

        # Oldest snapshot should be gone from index.html content
        idx = os.path.join(self.base, "index.html")
        self.assertTrue(os.path.exists(idx))
        with open(idx, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn(snaps[0], content)  # oldest removed

        # CLI run (dry-run)
        rc = prune_main(["--base-dir", self.base, "--keep", "1"])  # dry-run is default
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
