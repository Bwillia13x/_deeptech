from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone

from signal_harvester.xscore_utils import urljoin
from signal_harvester.site import build_all
from signal_harvester.snapshot import rotate_snapshot


class TestSiteBuilder(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_helpers(self):
        self.assertEqual(urljoin("https://ex.com/foo", "bar"), "https://ex.com/foo/bar")
        self.assertEqual(urljoin("https://ex.com/foo/", "/bar"), "https://ex.com/foo/bar")
        self.assertEqual(urljoin("https://ex.com/foo/", ""), "https://ex.com/foo/")

    def test_build_all(self):
        # prepare single snapshot
        src = os.path.join(self.base, "src.json")
        with open(src, "w", encoding="utf-8") as f:
            json.dump({"rows": [{"tweet_id": "1"}]}, f)
        rotate_snapshot(
            base_dir=self.base,
            src=src,
            now=datetime(2025, 3, 5, tzinfo=timezone.utc),
            keep=5,
            generate_diff=False,
            write_checksums_file=True,
        )

        base_url = "https://example.test/snapshots"
        result = build_all(self.base, base_url, True, True, True, True)
        self.assertTrue(result["ok"])
        outs = result["outputs"]
        for k in ["robots.txt", "sitemap.xml", "latest.json", "snapshots.json", "snapshots.atom"]:
            self.assertIn(k, outs)
            self.assertTrue(os.path.exists(outs[k]))


if __name__ == "__main__":
    unittest.main()
