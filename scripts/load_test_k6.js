/**
 * K6 Load Testing Script for Signal Harvester API
 * 
 * This script tests the Signal Harvester API using k6, a modern load testing tool.
 * It validates performance targets and provides detailed metrics.
 * 
 * Performance Targets:
 * - p95 latency < 500ms for all endpoints
 * - p99 latency < 1000ms for critical discovery endpoints
 * - Cache hit rate > 80% for discovery/topics endpoints
 * - Support 100+ concurrent users
 * 
 * Installation:
 *   macOS:   brew install k6
 *   Linux:   See https://k6.io/docs/getting-started/installation
 * 
 * Usage:
 *   # Basic test with 10 VUs for 30s:
 *   k6 run scripts/load_test_k6.js
 * 
 *   # Load test with 100 users for 5 minutes:
 *   k6 run --vus 100 --duration 5m scripts/load_test_k6.js
 * 
 *   # Stress test with ramp-up:
 *   k6 run --stage 1m:10 --stage 3m:100 --stage 1m:0 scripts/load_test_k6.js
 * 
 *   # Output results to JSON:
 *   k6 run --out json=load_test_results.json scripts/load_test_k6.js
 * 
 * Environment Variables:
 *   API_BASE_URL: Base URL for API (default: http://localhost:8000)
 *   HARVEST_API_KEY: API key for authentication (if required)
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// Custom metrics
const slaViolations = new Counter('sla_violations');
const cacheHitRate = new Rate('cache_hit_rate');
const discoveryLatency = new Trend('discovery_latency');
const topicsLatency = new Trend('topics_latency');
const timelineLatency = new Trend('timeline_latency');

// Configuration
const API_BASE_URL = __ENV.API_BASE_URL || 'http://localhost:8000';
const API_KEY = __ENV.HARVEST_API_KEY || '';

// Test stages - adjust for different load profiles
export const options = {
  stages: [
    { duration: '30s', target: 10 },   // Ramp up to 10 users
    { duration: '1m', target: 50 },    // Ramp up to 50 users
    { duration: '2m', target: 100 },   // Ramp up to 100 users
    { duration: '2m', target: 100 },   // Stay at 100 users
    { duration: '30s', target: 0 },    // Ramp down to 0 users
  ],
  thresholds: {
    // SLA requirements
    'http_req_duration{endpoint:discoveries}': ['p(95)<500', 'p(99)<1000'],
    'http_req_duration{endpoint:topics}': ['p(95)<500', 'p(99)<1000'],
    'http_req_duration{endpoint:timeline}': ['p(95)<500', 'p(99)<1000'],
    
    // Overall system health
    'http_req_failed': ['rate<0.01'], // Less than 1% errors
    'http_req_duration': ['p(95)<500'], // Overall p95 under 500ms
    'cache_hit_rate': ['rate>0.80'], // Cache hit rate > 80%
    'sla_violations': ['count<10'], // Less than 10 SLA violations
  },
};

// Headers
function getHeaders() {
  const headers = {
    'Content-Type': 'application/json',
  };
  if (API_KEY) {
    headers['X-API-Key'] = API_KEY;
  }
  return headers;
}

// Test data
let artifactIds = [];
let topicNames = [];

// Setup function - runs once at the beginning
export function setup() {
  console.log('='.repeat(80));
  console.log('Signal Harvester Load Test');
  console.log('='.repeat(80));
  console.log(`API Base URL: ${API_BASE_URL}`);
  console.log(`API Key: ${API_KEY ? 'Set' : 'Not set'}`);
  console.log('='.repeat(80));
  
  // Fetch initial data to populate caches
  const headers = getHeaders();
  
  // Get some discoveries
  const discoveriesRes = http.get(`${API_BASE_URL}/discoveries?limit=20`, { headers });
  if (discoveriesRes.status === 200) {
    const data = discoveriesRes.json();
    artifactIds = data.discoveries.slice(0, 10).map(d => d.id);
  }
  
  // Get some topics
  const topicsRes = http.get(`${API_BASE_URL}/topics/trending?limit=10`, { headers });
  if (topicsRes.status === 200) {
    const data = topicsRes.json();
    topicNames = data.topics.slice(0, 5).map(t => t.name);
  }
  
  return { artifactIds, topicNames };
}

// Main test scenario
export default function(data) {
  const headers = getHeaders();
  
  // Weighted scenario selection (simulates realistic user behavior)
  const scenario = Math.random();
  
  if (scenario < 0.50) {
    // 50% - Browse top discoveries
    browseDiscoveries(headers);
  } else if (scenario < 0.70) {
    // 20% - View trending topics
    viewTrendingTopics(headers);
  } else if (scenario < 0.85) {
    // 15% - View topic timeline
    viewTopicTimeline(headers, data.topicNames);
  } else if (scenario < 0.95) {
    // 10% - View entity profile
    viewEntityProfile(headers, data.artifactIds);
  } else {
    // 5% - Search with filters
    searchDiscoveriesWithFilters(headers);
  }
  
  // Occasional admin/monitoring tasks (5% of iterations)
  if (Math.random() < 0.05) {
    checkSystemHealth(headers);
  }
  
  // Realistic think time between requests
  sleep(Math.random() * 4 + 1); // 1-5 seconds
}

function browseDiscoveries(headers) {
  const limits = [20, 50, 100];
  const offsets = [0, 0, 0, 20, 50]; // Most users stay on first page
  
  const limit = limits[Math.floor(Math.random() * limits.length)];
  const offset = offsets[Math.floor(Math.random() * offsets.length)];
  
  const res = http.get(
    `${API_BASE_URL}/discoveries?limit=${limit}&offset=${offset}`,
    { headers, tags: { endpoint: 'discoveries' } }
  );
  
  const success = check(res, {
    'discoveries: status 200': (r) => r.status === 200,
    'discoveries: has data': (r) => r.status === 200 && r.json('discoveries') !== null,
    'discoveries: SLA met': (r) => r.timings.duration < 500,
  });
  
  discoveryLatency.add(res.timings.duration);
  
  if (res.timings.duration >= 500) {
    slaViolations.add(1);
  }
  
  // Check if response came from cache (via custom header if implemented)
  if (res.headers['X-Cache-Hit']) {
    cacheHitRate.add(1);
  } else if (res.headers['X-Cache-Miss']) {
    cacheHitRate.add(0);
  }
}

function viewTrendingTopics(headers) {
  const limits = [10, 20];
  const limit = limits[Math.floor(Math.random() * limits.length)];
  
  const res = http.get(
    `${API_BASE_URL}/topics/trending?limit=${limit}`,
    { headers, tags: { endpoint: 'topics' } }
  );
  
  check(res, {
    'topics: status 200': (r) => r.status === 200,
    'topics: has data': (r) => r.status === 200 && r.json('topics') !== null,
    'topics: SLA met': (r) => r.timings.duration < 500,
  });
  
  topicsLatency.add(res.timings.duration);
  
  if (res.timings.duration >= 500) {
    slaViolations.add(1);
  }
}

function viewTopicTimeline(headers, topicNames) {
  if (!topicNames || topicNames.length === 0) return;
  
  const topic = topicNames[Math.floor(Math.random() * topicNames.length)];
  const daysOptions = [7, 30, 90];
  const days = daysOptions[Math.floor(Math.random() * daysOptions.length)];
  
  const res = http.get(
    `${API_BASE_URL}/topics/${encodeURIComponent(topic)}/timeline?days=${days}`,
    { headers, tags: { endpoint: 'timeline' } }
  );
  
  check(res, {
    'timeline: status 200 or 404': (r) => r.status === 200 || r.status === 404,
    'timeline: SLA met': (r) => r.timings.duration < 500,
  });
  
  timelineLatency.add(res.timings.duration);
  
  if (res.timings.duration >= 500) {
    slaViolations.add(1);
  }
}

function viewEntityProfile(headers, artifactIds) {
  if (!artifactIds || artifactIds.length === 0) return;
  
  const entityId = artifactIds[Math.floor(Math.random() * artifactIds.length)];
  
  const res = http.get(
    `${API_BASE_URL}/entities/${entityId}`,
    { headers, tags: { endpoint: 'entity' } }
  );
  
  check(res, {
    'entity: status 200 or 404': (r) => r.status === 200 || r.status === 404,
  });
}

function searchDiscoveriesWithFilters(headers) {
  const sources = ['arxiv', 'github', 'x', null];
  const minScores = [0.7, 0.8, 0.9, null];
  
  let params = 'limit=50&offset=0';
  
  if (Math.random() > 0.5) {
    const source = sources[Math.floor(Math.random() * sources.length)];
    if (source) params += `&source=${source}`;
  }
  
  if (Math.random() > 0.5) {
    const minScore = minScores[Math.floor(Math.random() * minScores.length)];
    if (minScore) params += `&min_score=${minScore}`;
  }
  
  const res = http.get(
    `${API_BASE_URL}/discoveries?${params}`,
    { headers, tags: { endpoint: 'discoveries_filtered' } }
  );
  
  check(res, {
    'filtered discoveries: status 200': (r) => r.status === 200,
    'filtered discoveries: SLA met': (r) => r.timings.duration < 500,
  });
  
  if (res.timings.duration >= 500) {
    slaViolations.add(1);
  }
}

function checkSystemHealth(headers) {
  // Health check
  const healthRes = http.get(`${API_BASE_URL}/health`, { tags: { endpoint: 'health' } });
  check(healthRes, {
    'health: status 200': (r) => r.status === 200,
  });
  
  // Cache stats
  if (API_KEY) {
    const cacheRes = http.get(`${API_BASE_URL}/cache/stats`, { headers, tags: { endpoint: 'cache_stats' } });
    if (cacheRes.status === 200) {
      const data = cacheRes.json();
      if (data.hit_rate !== undefined) {
        cacheHitRate.add(data.hit_rate);
      }
    }
  }
}

// Teardown function - runs once at the end
export function teardown(data) {
  console.log('='.repeat(80));
  console.log('Load Test Complete');
  console.log('='.repeat(80));
  console.log('Review the summary above for performance metrics.');
  console.log('Key metrics to check:');
  console.log('  - http_req_duration p95/p99 (should be < 500ms/1000ms)');
  console.log('  - http_req_failed rate (should be < 1%)');
  console.log('  - cache_hit_rate (should be > 80%)');
  console.log('  - sla_violations count (should be < 10)');
  console.log('='.repeat(80));
}
