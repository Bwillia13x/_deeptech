from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from signal_harvester.site import build_all
from signal_harvester.snapshot import rotate_snapshot
from signal_harvester.verify import main as verify_main
from signal_harvester.verify import verify_site, verify_snapshot


class TestVerify(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _write_src(self, rows, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"rows": rows}, f)

    def test_verify_snapshot_and_site(self):
        base_url = "https://example.test/snapshots"

        day1 = datetime(2025, 2, 1, tzinfo=timezone.utc)
        rows1 = [
            {
                "username": "alice",
                "user_id": "1",
                "overall": 0.6,
                "letter_grade": "B",
                "followers_count": 100,
                "tweet_count": 10,
                "score_created_at": "2025-02-01T00:00:00Z",
            },
            {
                "username": "bob",
                "user_id": "2",
                "overall": 0.7,
                "letter_grade": "A",
                "followers_count": 200,
                "tweet_count": 20,
                "score_created_at": "2025-02-01T00:00:00Z",
            },
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
            {
                "username": "alice",
                "user_id": "1",
                "overall": 0.9,
                "letter_grade": "A",
                "followers_count": 150,
                "tweet_count": 12,
                "score_created_at": "2025-02-02T00:00:00Z",
            },
            {
                "username": "carol",
                "user_id": "3",
                "overall": 0.4,
                "letter_grade": "C",
                "followers_count": 50,
                "tweet_count": 5,
                "score_created_at": "2025-02-02T00:00:00Z",
            },
        ]
        src2 = os.path.join(self.base, "in2.json")
        self._write_src(rows2, src2)

        dir2 = rotate_snapshot(
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

        # Build site artifacts
        site_res = build_all(
            base_dir=self.base,
            base_url=base_url,
            write_robots=True,
            write_sitemap=True,
            write_latest=True,
            write_feeds=True,
        )
        self.assertTrue(site_res["ok"], f"site build failed: {site_res}")

        # Verify latest snapshot with API
        latest_name = os.path.basename(dir2)
        snap_res = verify_snapshot(self.base, snapshot_name=latest_name)
        self.assertTrue(snap_res["ok"], f"verify_snapshot failed: {snap_res}")

        # Verify site with API
        vres = verify_site(self.base, base_url=base_url)
        self.assertTrue(vres["ok"], f"verify_site failed: {vres}")

        # Verify snapshot via CLI
        rc1 = verify_main(["--base-dir", self.base, "--snapshot", latest_name])
        self.assertEqual(rc1, 0, "CLI verify snapshot failed")

        # Verify site via CLI
        rc2 = verify_main(["--base-dir", self.base, "--site", "--base-url", base_url])
        self.assertEqual(rc2, 0, "CLI verify site failed")


if __name__ == "__main__":
    unittest.main()
