from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
import urllib.request
from datetime import datetime, timedelta, timezone

from signal_harvester.html import build_html
from signal_harvester.serve import make_server
from signal_harvester.site import build_all, existing_snapshots
from signal_harvester.snapshot import rotate_snapshot


class TestServe(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _write_src(self, rows, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"rows": rows}, f)

    def test_serve_headers(self):
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

        build_all(
            base_dir=self.base,
            base_url=base_url,
            write_robots=True,
            write_sitemap=True,
            write_latest=True,
            write_feeds=True,
        )
        build_html(
            base_dir=self.base,
            base_url=None,
            write_index=True,
            write_snapshot_pages=True,
        )

        server, url = make_server(self.base, host="127.0.0.1", port=0, no_cache=True, cors=True)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            # Wait briefly for server to start
            time.sleep(0.2)
            # latest.json should be JSON and no-store
            with urllib.request.urlopen(url + "latest.json") as resp:
                ct = resp.headers.get("Content-Type", "")
                cc = resp.headers.get("Cache-Control", "")
                ac = resp.headers.get("Access-Control-Allow-Origin", "")
                self.assertIn("application/json", ct)
                self.assertIn("no-store", cc)
                self.assertIn("*", ac)

            latest = existing_snapshots(self.base)[-1]
            # data.csv.gz should have gzip encoding
            with urllib.request.urlopen(url + f"{latest}/data.csv.gz") as resp:
                ce = resp.headers.get("Content-Encoding", "")
                ct2 = resp.headers.get("Content-Type", "")
                self.assertIn("gzip", ce.lower())
                self.assertIn("csv", ct2.lower())
        finally:
            server.shutdown()
            t.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
