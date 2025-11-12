/**
 * Simplified K6 Load Testing Script for Signal Harvester API
 * 
 * Tests the currently available Signal Harvester API endpoints with realistic load.
 * 
 * Performance Targets:
 * - p95 latency < 500ms for all endpoints
 * - p99 latency < 1000ms for critical endpoints
 * - Support 100+ concurrent users
 * - Error rate < 1%
 * 
 * Usage:
 *   # Quick test (10 users, 1 minute):
 *   k6 run scripts/load_test_simple_k6.js
 * 
 *   # Load test (50 users, 3 minutes):
 *   k6 run --vus 50 --duration 3m scripts/load_test_simple_k6.js
 * 
 *   # Stress test with ramp-up to 100 users:
 *   k6 run --stage 1m:20 --stage 2m:50 --stage 2m:100 --stage 1m:0 scripts/load_test_simple_k6.js
 * 
 *   # Output results to JSON:
 *   k6 run --out json=results/load_test_$(date +%Y%m%d_%H%M%S).json scripts/load_test_simple_k6.js
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// Custom metrics
const slaViolations = new Counter('sla_violations');
const topSignalsLatency = new Trend('top_signals_latency');
const healthCheckLatency = new Trend('health_check_latency');
const signalDetailLatency = new Trend('signal_detail_latency');

// Configuration
const API_BASE_URL = __ENV.API_BASE_URL || 'http://localhost:8000';
const API_KEY = __ENV.HARVEST_API_KEY || '';

// Test stages - moderate load profile
export const options = {
    stages: [
        { duration: '30s', target: 10 },   // Warm up to 10 users
        { duration: '1m', target: 30 },    // Ramp up to 30 users
        { duration: '2m', target: 30 },    // Stay at 30 users
        { duration: '30s', target: 0 },    // Ramp down to 0 users
    ],
    thresholds: {
        // SLA requirements
        'http_req_duration{endpoint:top}': ['p(95)<500', 'p(99)<1000'],
        'http_req_duration{endpoint:health}': ['p(95)<100', 'p(99)<200'],
        'http_req_duration{endpoint:detail}': ['p(95)<200', 'p(99)<500'],

        // Overall system health
        'http_req_failed': ['rate<0.01'], // Less than 1% errors
        'http_req_duration': ['p(95)<500'], // Overall p95 under 500ms
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

// Test data - signal IDs to query
let signalIds = [];

// Setup function - runs once at the beginning
export function setup() {
    console.log('='.repeat(80));
    console.log('Signal Harvester Load Test - SQLite Baseline');
    console.log('='.repeat(80));
    console.log(`API Base URL: ${API_BASE_URL}`);
    console.log(`API Key: ${API_KEY ? 'Set' : 'Not set'}`);
    console.log('Target: 30 concurrent users for 2 minutes');
    console.log('='.repeat(80));

    // Fetch some signal IDs for detail queries
    const headers = getHeaders();
    const res = http.get(`${API_BASE_URL}/top?limit=20`, { headers });
    
    if (res.status === 200) {
        const signals = res.json();
        if (Array.isArray(signals)) {
            signalIds = signals.slice(0, 10).map(s => s.tweet_id);
            console.log(`Loaded ${signalIds.length} signal IDs for testing`);
        }
    } else {
        console.warn(`Failed to fetch signals: ${res.status}`);
    }

    return { signalIds };
}

// Main test scenario
export default function (data) {
    const headers = getHeaders();

    // Weighted scenario selection (simulates realistic user behavior)
    const scenario = Math.random();

    if (scenario < 0.60) {
        // 60% - Browse top signals
        browseTopSignals(headers);
    } else if (scenario < 0.85) {
        // 25% - View signal details
        viewSignalDetail(headers, data.signalIds);
    } else {
        // 15% - Check system health
        checkHealth(headers);
    }

    // Realistic think time between requests (1-5 seconds)
    sleep(Math.random() * 4 + 1);
}

function browseTopSignals(headers) {
    const limits = [10, 20, 50, 100];
    const limit = limits[Math.floor(Math.random() * limits.length)];

    const res = http.get(
        `${API_BASE_URL}/top?limit=${limit}`,
        { headers, tags: { endpoint: 'top' } }
    );

    const success = check(res, {
        'top signals: status 200': (r) => r.status === 200,
        'top signals: has data': (r) => r.status === 200 && Array.isArray(r.json()),
        'top signals: SLA met': (r) => r.timings.duration < 500,
    });

    topSignalsLatency.add(res.timings.duration);

    if (res.timings.duration >= 500) {
        slaViolations.add(1);
    }

    if (!success) {
        console.error(`Top signals request failed: ${res.status}`);
    }
}

function viewSignalDetail(headers, signalIds) {
    if (!signalIds || signalIds.length === 0) {
        // Fallback to top signals if no IDs available
        browseTopSignals(headers);
        return;
    }

    const signalId = signalIds[Math.floor(Math.random() * signalIds.length)];

    const res = http.get(
        `${API_BASE_URL}/tweet/${encodeURIComponent(signalId)}`,
        { headers, tags: { endpoint: 'detail' } }
    );

    const success = check(res, {
        'signal detail: status 200 or 404': (r) => r.status === 200 || r.status === 404,
        'signal detail: SLA met': (r) => r.timings.duration < 200,
    });

    signalDetailLatency.add(res.timings.duration);

    if (res.timings.duration >= 200) {
        slaViolations.add(1);
    }
}

function checkHealth(headers) {
    const res = http.get(
        `${API_BASE_URL}/health`, 
        { tags: { endpoint: 'health' } }
    );

    check(res, {
        'health: status 200': (r) => r.status === 200,
        'health: fast response': (r) => r.timings.duration < 100,
    });

    healthCheckLatency.add(res.timings.duration);
}

// Teardown function - runs once at the end
export function teardown(data) {
    console.log('='.repeat(80));
    console.log('Load Test Complete');
    console.log('='.repeat(80));
    console.log('Review the summary above for performance metrics.');
    console.log('');
    console.log('Key metrics to check:');
    console.log('  ✓ http_req_duration p95 < 500ms');
    console.log('  ✓ http_req_duration p99 < 1000ms');
    console.log('  ✓ http_req_failed rate < 1%');
    console.log('  ✓ sla_violations count < 10');
    console.log('');
    console.log('If thresholds are met, SQLite baseline is acceptable.');
    console.log('PostgreSQL migration should maintain or improve these metrics.');
    console.log('='.repeat(80));
}
