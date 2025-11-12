# Signal Harvester - API Client Examples

> This guide is part of the maintained documentation set for Signal Harvester.
> For the live architecture/readiness view and roadmap, see [`signal-harvester/ARCHITECTURE_AND_READINESS.md`](signal-harvester/ARCHITECTURE_AND_READINESS.md:1).
> To confirm the system passes its integrated checks, from the `signal-harvester` directory run `make verify-all` (see [`signal-harvester/Makefile`](signal-harvester/Makefile:7)).

## Overview

The Signal Harvester API provides programmatic access to all functionality. This guide includes examples in Python and JavaScript/Node.js.

**Base URL**: `http://localhost:8000` (default)
**Authentication**: API key in `X-API-Key` header
**Content Type**: `application/json`

---

## Python Examples

### Setup

```python
import os
import httpx

API_KEY = os.getenv("HARVEST_API_KEY", "your-api-key-here")
API_URL = os.getenv("HARVEST_API_URL", "http://localhost:8000")

client = httpx.Client(
    base_url=API_URL,
    headers={"X-API-Key": API_KEY},
    timeout=30.0
)
```

### Get Top Signals

```python
def get_top_signals(limit=50, min_salience=0.0, hours=None):
    """Get top-scored signals."""
    params = {
        "limit": limit,
        "min_salience": min_salience,
    }
    if hours:
        params["hours"] = hours
    
    response = client.get("/top", params=params)
    response.raise_for_status()
    return response.json()

# Get top 10 high-priority signals from last 24 hours
signals = get_top_signals(limit=10, min_salience=60.0, hours=24)

for signal in signals:
    print(f"[{signal['salience_score']}] {signal['text'][:100]}...")
```

### Get Specific Signal

```python
def get_signal(tweet_id):
    """Get a specific signal by tweet ID."""
    response = client.get(f"/tweet/{tweet_id}")
    response.raise_for_status()
    return response.json()

# Get details about a specific signal
signal = get_signal("1234567890123456789")
print(f"Category: {signal.get('category')}")
print(f"Salience: {signal.get('salience_score')}")
print(f"Text: {signal.get('text')}")
```

### Run Pipeline

```python
def run_pipeline(notify_threshold=None, notify_limit=10, notify_hours=None):
    """Run the harvest pipeline."""
    params = {}
    if notify_threshold is not None:
        params["notify_threshold"] = notify_threshold
    if notify_limit is not None:
        params["notify_limit"] = notify_limit
    if notify_hours is not None:
        params["notify_hours"] = notify_hours
    
    response = client.post("/refresh", params=params)
    response.raise_for_status()
    return response.json()

# Run pipeline with custom notification settings
stats = run_pipeline(notify_threshold=70.0, notify_limit=5, notify_hours=12)
print(f"Fetched: {stats['fetched']}")
print(f"Analyzed: {stats['analyzed']}")
print(f"Notified: {stats['notified']}")
```

### Export Signals

```python
import csv

def export_signals_to_csv(filename="signals.csv", limit=1000, min_salience=0.0):
    """Export signals to CSV file."""
    signals = get_top_signals(limit=limit, min_salience=min_salience)
    
    with open(filename, "w", newline="", encoding="utf-8") as f:
        if not signals:
            print("No signals to export")
            return
            
        writer = csv.DictWriter(f, fieldnames=signals[0].keys())
        writer.writeheader()
        writer.writerows(signals)
    
    print(f"Exported {len(signals)} signals to {filename}")

# Export high-priority signals
export_signals_to_csv("high_priority_signals.csv", min_salience=60.0)
```

### Get Health Status

```python
def check_health():
    """Check API health status."""
    response = client.get("/health")
    response.raise_for_status()
    return response.json()

# Monitor API health
health = check_health()
print(f"Status: {health['status']}")
print(f"Version: {health['version']}")
print(f"Database: {health['database']}")
```

### Get Metrics

```python
def get_metrics():
    """Get Prometheus metrics."""
    response = client.get("/metrics/prometheus")
    response.raise_for_status()
    return response.text()

# Get raw metrics for monitoring
metrics = get_metrics()
print(metrics[:500])  # Print first 500 chars
```

### Complete Workflow Example

```python
def monitor_and_alert():
    """Complete workflow: run pipeline and alert on high-priority signals."""
    print("Running pipeline...")
    stats = run_pipeline(notify_threshold=60.0, notify_limit=10)
    
    print(f"✓ Fetched {stats['fetched']} tweets")
    print(f"✓ Analyzed {stats['analyzed']} signals")
    print(f"✓ Sent {stats['notified']} notifications")
    
    # Get high-priority signals
    print("\nFetching high-priority signals...")
    signals = get_top_signals(limit=10, min_salience=70.0)
    
    if signals:
        print(f"\n🚨 Found {len(signals)} high-priority signals:\n")
        for signal in signals:
            print(f"[{signal['salience_score']}] {signal['category']}")
            print(f"Author: @{signal.get('author_username', 'unknown')}")
            print(f"Text: {signal['text'][:150]}...")
            print(f"URL: {signal['url']}")
            print("-" * 60)
    else:
        print("No high-priority signals found.")

# Run the complete workflow
if __name__ == "__main__":
    monitor_and_alert()
```

---

## JavaScript/Node.js Examples

### Setup

```javascript
const API_KEY = process.env.HARVEST_API_KEY || "your-api-key-here";
const API_URL = process.env.HARVEST_API_URL || "http://localhost:8000";

async function request(path, options = {}) {
  const url = `${API_URL}${path}`;
  const headers = {
    "X-API-Key": API_KEY,
    "Accept": "application/json",
    ...options.headers
  };
  
  if (options.body) {
    headers["Content-Type"] = "application/json";
  }
  
  const config = {
    method: options.method || "GET",
    headers,
    signal: options.signal
  };
  
  if (options.body) {
    config.body = JSON.stringify(options.body);
  }
  
  const response = await fetch(url, config);
  
  const isJson = response.headers.get("content-type")?.includes("application/json");
  const data = isJson ? await response.json().catch(() => undefined) : undefined;
  
  if (!response.ok) {
    const message = (data && (data.message || data.error)) || `HTTP ${response.status}`;
    throw new Error(message);
  }
  
  return data;
}
```

### Get Top Signals

```javascript
async function getTopSignals(limit = 50, minSalience = 0.0, hours = null) {
  const params = new URLSearchParams({
    limit: limit.toString(),
    min_salience: minSalience.toString(),
  });
  
  if (hours) {
    params.append("hours", hours.toString());
  }
  
  return await request(`/top?${params}`);
}

// Get top 10 high-priority signals from last 24 hours
const signals = await getTopSignals(10, 60.0, 24);

for (const signal of signals) {
  console.log(`[${signal.salience_score}] ${signal.text.substring(0, 100)}...`);
}
```

### Get Specific Signal

```javascript
async function getSignal(tweetId) {
  return await request(`/tweet/${tweetId}`);
}

// Get details about a specific signal
const signal = await getSignal("1234567890123456789");
console.log(`Category: ${signal.category}`);
console.log(`Salience: ${signal.salience_score}`);
console.log(`Text: ${signal.text}`);
```

### Run Pipeline

```javascript
async function runPipeline(notifyThreshold = null, notifyLimit = 10, notifyHours = null) {
  const params = new URLSearchParams();
  
  if (notifyThreshold !== null) {
    params.append("notify_threshold", notifyThreshold.toString());
  }
  if (notifyLimit !== null) {
    params.append("notify_limit", notifyLimit.toString());
  }
  if (notifyHours !== null) {
    params.append("notify_hours", notifyHours.toString());
  }
  
  return await request(`/refresh?${params}`, { method: "POST" });
}

// Run pipeline with custom notification settings
const stats = await runPipeline(70.0, 5, 12);
console.log(`Fetched: ${stats.fetched}`);
console.log(`Analyzed: ${stats.analyzed}`);
console.log(`Notified: ${stats.notified}`);
```

### Export to JSON

```javascript
const fs = require("fs");

async function exportSignalsToJson(filename = "signals.json", limit = 1000, minSalience = 0.0) {
  const signals = await getTopSignals(limit, minSalience);
  
  fs.writeFileSync(filename, JSON.stringify(signals, null, 2));
  console.log(`Exported ${signals.length} signals to ${filename}`);
}

// Export high-priority signals
await exportSignalsToJson("high_priority_signals.json", 1000, 60.0);
```

### Get Health Status

```javascript
async function checkHealth() {
  return await request("/health");
}

// Monitor API health
const health = await checkHealth();
console.log(`Status: ${health.status}`);
console.log(`Version: ${health.version}`);
console.log(`Database: ${health.database}`);
```

### Real-time Monitoring with WebSockets

```javascript
// Note: This is a conceptual example. Actual implementation depends on your API setup.

function monitorSignalsRealtime(callback) {
  const ws = new WebSocket(`ws://localhost:8000/ws/signals?api_key=${API_KEY}`);
  
  ws.onmessage = (event) => {
    const signal = JSON.parse(event.data);
    callback(signal);
  };
  
  ws.onerror = (error) => {
    console.error("WebSocket error:", error);
  };
  
  ws.onclose = () => {
    console.log("WebSocket closed, reconnecting in 5 seconds...");
    setTimeout(() => monitorSignalsRealtime(callback), 5000);
  };
  
  return ws;
}

// Use the real-time monitor
const ws = monitorSignalsRealtime((signal) => {
  console.log(`New high-priority signal: [${signal.salience_score}] ${signal.text}`);
});
```

### Complete Workflow Example

```javascript
async function monitorAndAlert() {
  console.log("Running pipeline...");
  const stats = await runPipeline(60.0, 10);
  
  console.log(`✓ Fetched ${stats.fetched} tweets`);
  console.log(`✓ Analyzed ${stats.analyzed} signals`);
  console.log(`✓ Sent ${stats.notified} notifications`);
  
  // Get high-priority signals
  console.log("\nFetching high-priority signals...");
  const signals = await getTopSignals(10, 70.0);
  
  if (signals.length > 0) {
    console.log(`\n🚨 Found ${signals.length} high-priority signals:\n`);
    
    for (const signal of signals) {
      console.log(`[${signal.salience_score}] ${signal.category}`);
      console.log(`Author: @${signal.author_username || "unknown"}`);
      console.log(`Text: ${signal.text.substring(0, 150)}...`);
      console.log(`URL: ${signal.url}`);
      console.log("-".repeat(60));
    }
  } else {
    console.log("No high-priority signals found.");
  }
}

// Run the complete workflow
monitorAndAlert().catch(console.error);
```

---

## API Reference

### Authentication

All endpoints require authentication via `X-API-Key` header.

```python
headers = {"X-API-Key": "your-api-key"}
```

### Endpoints

#### GET /top

Get top-scored signals.

**Parameters**:
- `limit` (int, optional): Max results (1-200, default: 50)
- `min_salience` (float, optional): Minimum score (0-100, default: 0)
- `hours` (int, optional): Filter to last N hours (1-168)

**Response**: Array of signal objects

#### GET /tweet/{tweet_id}

Get a specific signal by tweet ID.

**Response**: Signal object

#### POST /refresh

Run the harvest pipeline.

**Parameters**:
- `notify_threshold` (float, optional): Min score for notifications
- `notify_limit` (int, optional): Max notifications to send
- `notify_hours` (int, optional): Only recent signals

**Response**: Statistics object

#### GET /health

Check API health status.

**Response**: Health status object

#### GET /metrics/prometheus

Get Prometheus metrics (for monitoring).

**Response**: Plain text metrics

### Error Responses

All errors return JSON with error details:

```json
{
  "error": "Error type",
  "message": "Human-readable message",
  "status": 400
}
```

**Common Error Codes**:
- `400`: Bad request (invalid parameters)
- `401`: Unauthorized (invalid API key)
- `403`: Forbidden (insufficient permissions)
- `404`: Not found (resource doesn't exist)
- `429`: Rate limited (too many requests)
- `500`: Server error (internal problem)

### Rate Limiting

API is rate-limited to 10 requests per minute per client.

**Headers**:
- `X-RateLimit-Limit`: Maximum requests allowed
- `X-RateLimit-Remaining`: Requests remaining
- `X-RateLimit-Reset`: When limit resets (timestamp)

### Pagination

List endpoints support pagination:

**Parameters**:
- `page` (int): Page number (default: 1)
- `pageSize` (int): Items per page (default: 10)

**Response includes**:
- `items`: Array of results
- `total`: Total count
- `page`: Current page
- `pageSize`: Items per page

---

## Tips & Best Practices

### Python

1. **Use environment variables** for API keys
2. **Handle errors gracefully** with try/except
3. **Use context managers** for resource cleanup
4. **Implement retry logic** for reliability
5. **Log API calls** for debugging

### JavaScript

1. **Use async/await** for cleaner code
2. **Implement error boundaries** in React apps
3. **Cache responses** when appropriate
4. **Abort requests** on component unmount
5. **Use environment variables** for configuration

### General

1. **Respect rate limits**: Implement exponential backoff
2. **Cache when possible**: Don't fetch unchanged data
3. **Handle errors**: Always check response status
4. **Monitor usage**: Track API calls and costs
5. **Secure keys**: Never commit API keys to git

---

## Troubleshooting

**Problem**: Authentication errors (401)
- **Solution**: Check API key is correct and included in headers

**Problem**: Rate limit errors (429)
- **Solution**: Implement retry logic with exponential backoff

**Problem**: Connection timeouts
- **Solution**: Increase timeout value or check network connectivity

**Problem**: SSL/certificate errors
- **Solution**: Verify API URL is correct (http vs https)

**Problem**: JSON parse errors
- **Solution**: Check if response is actually JSON

---

## Support

- **API Documentation**: http://localhost:8000/docs
- **OpenAPI Spec**: http://localhost:8000/openapi.json
- **Beta Support**: beta-support@signal-harvester.com
- **Slack**: #signal-harvester-beta

---

**Happy coding! 🚀**