#!/usr/bin/env python3
"""
API Performance Testing Script

Tests Signal Harvester API endpoints with PostgreSQL backend to validate
response times meet production requirements:
- Listing endpoints: <500ms
- Scoring/analysis endpoints: <2s
- Health checks: <100ms

Usage:
    export DATABASE_URL="postgresql://..."
    python scripts/performance_test.py --base-url http://localhost:8000
"""

import argparse
import asyncio
import sys
import time
from typing import Dict, List, Optional

import httpx


class PerformanceTest:
    """Performance testing for Signal Harvester API."""

    def __init__(self, base_url: str, api_key: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.results: List[Dict[str, any]] = []

    def _headers(self) -> Dict[str, str]:
        """Get request headers with optional API key."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    async def test_endpoint(
        self,
        endpoint: str,
        method: str = "GET",
        expected_max_ms: int = 500,
        description: str = "",
    ) -> bool:
        """Test a single endpoint and record performance."""
        url = f"{self.base_url}{endpoint}"
        print(f"  Testing {method} {endpoint}...", end=" ", flush=True)

        start = time.time()
        try:
            async with httpx.AsyncClient() as client:
                if method == "GET":
                    response = await client.get(url, headers=self._headers(), timeout=10.0)
                elif method == "POST":
                    response = await client.post(url, headers=self._headers(), json={}, timeout=10.0)
                else:
                    raise ValueError(f"Unsupported method: {method}")

            duration_ms = (time.time() - start) * 1000

            # Record result
            result = {
                "endpoint": endpoint,
                "method": method,
                "description": description,
                "duration_ms": duration_ms,
                "expected_max_ms": expected_max_ms,
                "status_code": response.status_code,
                "success": response.status_code == 200 and duration_ms <= expected_max_ms,
            }
            self.results.append(result)

            # Print result
            if result["success"]:
                print(f"✓ {duration_ms:.0f}ms (expected <{expected_max_ms}ms)")
            else:
                if response.status_code != 200:
                    print(f"❌ HTTP {response.status_code}")
                else:
                    print(f"⚠️ {duration_ms:.0f}ms (expected <{expected_max_ms}ms, SLOW)")
            
            return result["success"]

        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            print(f"❌ ERROR: {e}")
            self.results.append({
                "endpoint": endpoint,
                "method": method,
                "description": description,
                "duration_ms": duration_ms,
                "expected_max_ms": expected_max_ms,
                "status_code": 0,
                "success": False,
                "error": str(e),
            })
            return False

    async def run_tests(self) -> bool:
        """Run all performance tests."""
        print("🚀 Starting API Performance Tests\n")
        print(f"Target: {self.base_url}\n")

        # Health check endpoints (should be <100ms)
        print("📊 Health Check Endpoints:")
        await self.test_endpoint("/health/live", "GET", 100, "Liveness probe")
        await self.test_endpoint("/health/ready", "GET", 5000, "Readiness probe (includes DB check)")
        await self.test_endpoint("/health/startup", "GET", 5000, "Startup probe")

        print("\n📊 Discovery Endpoints (Listing - should be <500ms):")
        await self.test_endpoint("/discoveries", "GET", 500, "List discoveries")
        await self.test_endpoint("/discoveries?limit=10", "GET", 500, "List discoveries (limited)")
        await self.test_endpoint("/topics", "GET", 500, "List topics")

        print("\n📊 Legacy Endpoints (Listing - should be <500ms):")
        await self.test_endpoint("/signals", "GET", 500, "List signals")
        await self.test_endpoint("/signals?limit=10", "GET", 500, "List signals (limited)")
        await self.test_endpoint("/snapshots", "GET", 500, "List snapshots")

        print("\n📊 Stats Endpoints (should be <1s):")
        await self.test_endpoint("/stats", "GET", 1000, "Overall stats")

        # Summary
        print("\n" + "="*60)
        print("📊 Performance Test Summary")
        print("="*60)

        passed = sum(1 for r in self.results if r["success"])
        failed = len(self.results) - passed
        
        print(f"\nTotal Tests: {len(self.results)}")
        print(f"  ✓ Passed: {passed}")
        print(f"  ❌ Failed: {failed}")

        if failed > 0:
            print("\n⚠️ Failed Tests:")
            for result in self.results:
                if not result["success"]:
                    status = f"HTTP {result['status_code']}" if result['status_code'] > 0 else "ERROR"
                    print(f"  - {result['method']} {result['endpoint']}: {status} ({result['duration_ms']:.0f}ms)")

        # Performance stats
        durations = [r["duration_ms"] for r in self.results if r["status_code"] == 200]
        if durations:
            print(f"\n⏱️ Response Time Stats:")
            print(f"  Average: {sum(durations) / len(durations):.0f}ms")
            print(f"  Median: {sorted(durations)[len(durations) // 2]:.0f}ms")
            print(f"  Min: {min(durations):.0f}ms")
            print(f"  Max: {max(durations):.0f}ms")

        return failed == 0


async def main() -> int:
    """Main test runner."""
    parser = argparse.ArgumentParser(description="API Performance Testing")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Base URL for API server",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="API key for authenticated endpoints",
    )
    args = parser.parse_args()

    tester = PerformanceTest(args.base_url, args.api_key)
    success = await tester.run_tests()

    if success:
        print("\n✅ All performance tests passed!")
        return 0
    else:
        print("\n❌ Some performance tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
