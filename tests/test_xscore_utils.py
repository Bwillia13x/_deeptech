from __future__ import annotations

import unittest
from datetime import timezone

from signal_harvester.xscore_utils import parse_datetime, urljoin


class TestUtils(unittest.TestCase):
    def test_parse_datetime(self):
        dt1 = parse_datetime("2025-03-02")
        self.assertEqual(dt1.tzinfo, timezone.utc)
        self.assertEqual(dt1.hour, 0)
        self.assertEqual(dt1.minute, 0)

        dt2 = parse_datetime("2025-03-02T05:04:03Z")
        self.assertEqual(dt2.tzinfo, timezone.utc)
        self.assertEqual(dt2.hour, 5)
        self.assertEqual(dt2.minute, 4)
        self.assertEqual(dt2.second, 3)

        dt3 = parse_datetime(None)
        self.assertEqual(dt3.tzinfo, timezone.utc)

    def test_urljoin(self):
        self.assertEqual(urljoin("https://ex.com/a/", "b"), "https://ex.com/a/b")
        self.assertEqual(urljoin("https://ex.com/a", "/b"), "https://ex.com/a/b")


if __name__ == "__main__":
    unittest.main()
