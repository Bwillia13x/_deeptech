from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone, timedelta

from signal_harvester.snapshot import rotate_snapshot
from signal_harvester.site import build_all, existing_snapshots


class TestSnapshot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _write_src(self, rows, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"rows": rows}, f)

    def test_rotation_outputs_and_diffs(self):
        day1 = datetime(2025, 1, 1, tzinfo=timezone.utc)
        rows1 = [{"tweet_id": "1", "text": "Test tweet 1", "overall": 0.6}]
        src1 = os.path.join(self.base, "in1.json")
        self._write_src(rows1, src1)

        out1 = rotate_snapshot(
            base_dir=self.base,
            src=src1,
            now=day1,
            keep=10,
            generate_diff=False,
            write_ndjson=True,
            write_csv=True,
            write_checksums_file=True,
            write_schema_files=True,
        )
        self.assertTrue(os.path.isdir(out1))
        files1 = os.listdir(out1)
        for expected in ["data.json", "data.json.gz", "data.ndjson", "data.ndjson.gz", "data.csv", "data.csv.gz", "schema.json", "checksums.json"]:
            self.assertIn(expected, files1)

        with open(os.path.join(out1, "checksums.json"), "r", encoding="utf-8") as f:
            manifest = json.load(f)
        paths = [it["path"] for it in manifest.get("files", [])]
        self.assertIn("data.json", paths)

        day2 = day1 + timedelta(days=1)
        rows2 = [{"tweet_id": "1", "text": "Test tweet 1 updated", "overall": 0.9}, {"tweet_id": "2", "text": "Test tweet 2", "overall": 0.5}]
        src2 = os.path.join(self.base, "in2.json")
        self._write_src(rows2, src2)

        out2 = rotate_snapshot(
            base_dir=self.base,
            src=src2,
            now=day2,
            keep=10,
            generate_diff=True,
            write_ndjson=True,
            write_csv=True,
            write_checksums_file=True,
            write_schema_files=True,
        )
        self.assertTrue(os.path.isdir(out2))

        diffs_dir = os.path.join(self.base, "diffs")
        self.assertTrue(os.path.isdir(diffs_dir))
        diffs = sorted(os.listdir(diffs_dir))
        self.assertTrue(any(d.endswith(".json") for d in diffs))
        self.assertTrue(any(d.endswith(".json.gz") for d in diffs))

    def test_build_all_outputs(self):
        # Create two snapshots then build site
        day1 = datetime(2025, 2, 1, tzinfo=timezone.utc)
        day2 = day1 + timedelta(days=1)
        rows = [{"tweet_id": "1", "text": "Test tweet"}]
        for i, day in enumerate([day1, day2], 1):
            src = os.path.join(self.base, f"in{i}.json")
            self._write_src(rows, src)
            rotate_snapshot(
                base_dir=self.base,
                src=src,
                now=day,
                keep=10,
                generate_diff=i == 2,
                write_ndjson=True,
                write_csv=True,
                write_checksums_file=True,
                write_schema_files=True,
            )

        base_url = "https://example.test/snapshots"
        result = build_all(
            base_dir=self.base,
            base_url=base_url,
            write_robots=True,
            write_sitemap=True,
            write_latest=True,
            write_feeds=True,
        )
        self.assertTrue(result["ok"])
        outs = result["outputs"]
        self.assertIn("robots.txt", outs)
        self.assertIn("sitemap.xml", outs)
        self.assertIn("latest.json", outs)
        self.assertIn("snapshots.json", outs)
        self.assertIn("snapshots.atom", outs)

        with open(os.path.join(self.base, "robots.txt"), "r", encoding="utf-8") as f:
            robots = f.read()
        self.assertIn("Sitemap:", robots)

        with open(os.path.join(self.base, "latest.json"), "r", encoding="utf-8") as f:
            latest = json.load(f)
        snaps = existing_snapshots(self.base)
        self.assertEqual(latest.get("latest", {}).get("name"), snaps[-1])


if __name__ == "__main__":
    unittest.main()
