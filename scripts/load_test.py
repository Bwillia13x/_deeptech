"""
Load Testing Script for Signal Harvester API

This script uses Locust to simulate realistic user load on the Signal Harvester API.
It tests critical endpoints with realistic access patterns and validates performance targets.

Performance Targets:
- p95 latency < 500ms for all endpoints
- p99 latency < 1000ms for critical discovery endpoints
- Cache hit rate > 80% for discovery/topics endpoints
- Support 100+ concurrent users

Usage:
    # Install locust first:
    pip install locust

    # Run with web UI:
    locust -f scripts/load_test.py --host=http://localhost:8000

    # Run headless with 100 users, 10 users/sec spawn rate, 5 min duration:
    locust -f scripts/load_test.py --host=http://localhost:8000 \\
           --users 100 --spawn-rate 10 --run-time 5m --headless

    # Run with HTML report:
    locust -f scripts/load_test.py --host=http://localhost:8000 \\
           --users 100 --spawn-rate 10 --run-time 5m --headless \\
           --html load_test_report.html

Configuration:
    Set HARVEST_API_KEY environment variable if API requires authentication.
"""

import os
import random
import time
from datetime import datetime, timedelta

from locust import HttpUser, TaskSet, between, events, task


class DiscoveryBehavior(TaskSet):
    """
    Simulates typical discovery dashboard user behavior.
    
    Access patterns:
    - 50% - Browse top discoveries (most common)
    - 20% - View trending topics
    - 15% - Drill into specific topic timeline
    - 10% - View entity profiles
    - 5% - Search/filter discoveries
    """
    
    def on_start(self):
        """Initialize user session - fetch initial data."""
        self.api_key = os.environ.get("HARVEST_API_KEY", "")
        self.headers = {"X-API-Key": self.api_key} if self.api_key else {}
        
        # Cache some IDs for realistic access patterns
        self.artifact_ids = []
        self.topic_names = []
        self.entity_ids = []
        
        # Warm up - fetch initial data to populate caches
        self._fetch_initial_data()
    
    def _fetch_initial_data(self):
        """Fetch initial data to populate local caches."""
        # Get some artifact IDs
        with self.client.get("/discoveries?limit=20", headers=self.headers, catch_response=True) as response:
            if response.status_code == 200:
                data = response.json()
                self.artifact_ids = [d["id"] for d in data.get("discoveries", [])[:10]]
                response.success()
        
        # Get some topic names
        with self.client.get("/topics/trending?limit=10", headers=self.headers, catch_response=True) as response:
            if response.status_code == 200:
                data = response.json()
                self.topic_names = [t["name"] for t in data.get("topics", [])[:5]]
                response.success()
    
    @task(50)
    def browse_discoveries(self):
        """
        Browse top discoveries - most common user action.
        Tests the primary discovery endpoint with various pagination parameters.
        """
        params = {
            "limit": random.choice([20, 50, 100]),
            "offset": random.choice([0, 0, 0, 20, 50]),  # Most users stay on first page
        }
        
        with self.client.get("/discoveries", params=params, headers=self.headers, 
                            name="/discoveries (paginated)", catch_response=True) as response:
            if response.status_code == 200:
                # Validate response time against SLA
                if response.elapsed.total_seconds() * 1000 > 500:  # 500ms SLA
                    response.failure(f"Response time {response.elapsed.total_seconds() * 1000:.0f}ms exceeds 500ms SLA")
                else:
                    response.success()
            else:
                response.failure(f"Got status code {response.status_code}")
    
    @task(20)
    def view_trending_topics(self):
        """
        View trending topics list.
        Tests caching and topic aggregation performance.
        """
        params = {"limit": random.choice([10, 20])}
        
        with self.client.get("/topics/trending", params=params, headers=self.headers,
                            name="/topics/trending", catch_response=True) as response:
            if response.status_code == 200:
                if response.elapsed.total_seconds() * 1000 > 500:
                    response.failure(f"Response time {response.elapsed.total_seconds() * 1000:.0f}ms exceeds 500ms SLA")
                else:
                    response.success()
            else:
                response.failure(f"Got status code {response.status_code}")
    
    @task(15)
    def view_topic_timeline(self):
        """
        Drill into specific topic timeline.
        Tests topic-artifact join performance and time-series queries.
        """
        if not self.topic_names:
            return
        
        topic_name = random.choice(self.topic_names)
        days_back = random.choice([7, 30, 90])
        
        params = {"days": days_back}
        
        with self.client.get(f"/topics/{topic_name}/timeline", params=params, headers=self.headers,
                            name="/topics/{name}/timeline", catch_response=True) as response:
            if response.status_code == 200:
                if response.elapsed.total_seconds() * 1000 > 500:
                    response.failure(f"Response time {response.elapsed.total_seconds() * 1000:.0f}ms exceeds 500ms SLA")
                else:
                    response.success()
            elif response.status_code == 404:
                # Topic not found is acceptable (might have been from cache)
                response.success()
            else:
                response.failure(f"Got status code {response.status_code}")
    
    @task(10)
    def view_entity_profile(self):
        """
        View researcher/entity profile.
        Tests entity lookup and relationship queries.
        """
        if not self.artifact_ids:
            return
        
        # Use artifact ID as proxy (in real scenario we'd have entity IDs)
        entity_id = random.choice(self.artifact_ids)
        
        with self.client.get(f"/entities/{entity_id}", headers=self.headers,
                            name="/entities/{id}", catch_response=True) as response:
            if response.status_code in [200, 404]:  # 404 is acceptable
                response.success()
            else:
                response.failure(f"Got status code {response.status_code}")
    
    @task(5)
    def search_discoveries_with_filters(self):
        """
        Search discoveries with filters.
        Tests complex query performance with multiple filter conditions.
        """
        # Simulate various filter combinations
        sources = ["arxiv", "github", "x", None]
        min_scores = [0.7, 0.8, 0.9, None]
        
        params = {
            "limit": 50,
            "offset": 0,
        }
        
        if random.random() > 0.5:
            params["source"] = random.choice(sources)
        
        if random.random() > 0.5:
            params["min_score"] = random.choice(min_scores)
        
        if random.random() > 0.3:
            # Add time filter
            days_back = random.choice([7, 14, 30])
            since = (datetime.utcnow() - timedelta(days=days_back)).isoformat()
            params["since"] = since
        
        with self.client.get("/discoveries", params=params, headers=self.headers,
                            name="/discoveries (filtered)", catch_response=True) as response:
            if response.status_code == 200:
                if response.elapsed.total_seconds() * 1000 > 500:
                    response.failure(f"Response time {response.elapsed.total_seconds() * 1000:.0f}ms exceeds 500ms SLA")
                else:
                    response.success()
            else:
                response.failure(f"Got status code {response.status_code}")


class AdminBehavior(TaskSet):
    """
    Simulates admin/operator behavior.
    
    Access patterns:
    - Health checks
    - Metrics monitoring
    - Cache statistics
    - System stats
    """
    
    def on_start(self):
        self.api_key = os.environ.get("HARVEST_API_KEY", "")
        self.headers = {"X-API-Key": self.api_key} if self.api_key else {}
    
    @task(40)
    def check_health(self):
        """Monitor system health."""
        with self.client.get("/health", name="/health", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Health check failed with status {response.status_code}")
    
    @task(30)
    def view_metrics(self):
        """View Prometheus metrics."""
        with self.client.get("/metrics/prometheus", name="/metrics/prometheus", 
                            catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Got status code {response.status_code}")
    
    @task(20)
    def view_cache_stats(self):
        """Monitor cache performance."""
        with self.client.get("/cache/stats", headers=self.headers, name="/cache/stats",
                            catch_response=True) as response:
            if response.status_code == 200:
                data = response.json()
                # Validate cache hit rate
                hit_rate = data.get("hit_rate", 0)
                if hit_rate < 0.80:  # 80% target
                    response.failure(f"Cache hit rate {hit_rate:.1%} below 80% target")
                else:
                    response.success()
            else:
                response.failure(f"Got status code {response.status_code}")
    
    @task(10)
    def view_stats(self):
        """View system statistics."""
        with self.client.get("/stats", headers=self.headers, name="/stats",
                            catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Got status code {response.status_code}")


class DiscoveryUser(HttpUser):
    """
    Simulates typical discovery dashboard user.
    Wait time: 1-5 seconds between requests (realistic browsing behavior).
    """
    tasks = [DiscoveryBehavior]
    wait_time = between(1, 5)
    weight = 8  # 80% of users


class AdminUser(HttpUser):
    """
    Simulates admin/monitoring user.
    Wait time: 5-15 seconds between requests (monitoring dashboards).
    """
    tasks = [AdminBehavior]
    wait_time = between(5, 15)
    weight = 2  # 20% of users


# Performance validation hooks
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Print test configuration on start."""
    print("\n" + "="*80)
    print("Signal Harvester Load Test")
    print("="*80)
    print(f"Host: {environment.host}")
    print(f"Users: {environment.runner.user_count if hasattr(environment.runner, 'user_count') else 'N/A'}")
    print(f"API Key: {'Set' if os.environ.get('HARVEST_API_KEY') else 'Not set'}")
    print("="*80 + "\n")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Validate performance targets on test completion."""
    stats = environment.runner.stats
    
    print("\n" + "="*80)
    print("Performance Validation Results")
    print("="*80)
    
    # Check p95 latency for critical endpoints
    critical_endpoints = [
        "/discoveries (paginated)",
        "/topics/trending",
        "/topics/{name}/timeline",
    ]
    
    all_passed = True
    for endpoint in critical_endpoints:
        if endpoint in stats.entries:
            entry = stats.entries[endpoint]
            p95 = entry.get_response_time_percentile(0.95)
            p99 = entry.get_response_time_percentile(0.99)
            
            passed_p95 = p95 < 500
            passed_p99 = p99 < 1000
            
            status = "✅ PASS" if (passed_p95 and passed_p99) else "❌ FAIL"
            print(f"{endpoint}:")
            print(f"  p95: {p95:.0f}ms (target: <500ms) - {'✅' if passed_p95 else '❌'}")
            print(f"  p99: {p99:.0f}ms (target: <1000ms) - {'✅' if passed_p99 else '❌'}")
            print(f"  Status: {status}\n")
            
            if not (passed_p95 and passed_p99):
                all_passed = False
    
    # Overall result
    if all_passed:
        print("="*80)
        print("✅ ALL PERFORMANCE TARGETS MET")
        print("="*80 + "\n")
    else:
        print("="*80)
        print("❌ PERFORMANCE TARGETS NOT MET - Review failures above")
        print("="*80 + "\n")


# Import events for hooks
from locust import events
