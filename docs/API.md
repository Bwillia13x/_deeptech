# Signal Harvester API Documentation

> This document is part of the maintained documentation set for Signal Harvester.
> For canonical architecture, readiness status, and roadmap, see [`signal-harvester/ARCHITECTURE_AND_READINESS.md`](signal-harvester/ARCHITECTURE_AND_READINESS.md:1).
> For a single end-to-end health check (including tests and builds), from the `signal-harvester` directory run `make verify-all` (see [`signal-harvester/Makefile`](signal-harvester/Makefile:7)).

## 📖 Overview

The Signal Harvester API provides REST endpoints for accessing harvested social signals, managing the pipeline, and monitoring system health.

**Base URL:** `http://localhost:8000`

**API Version:** 0.1.0

## 🔐 Authentication

Most endpoints (except health check) require API key authentication using the `X-API-Key` header.

```bash
curl -H "X-API-Key: YOUR_API_KEY" http://localhost:8000/top
```

Set the `HARVEST_API_KEY` environment variable to enable authentication.

> Frontend builds now read the same credential from the `VITE_API_KEY` env var (see `frontend/.env.example`).
> Providing this value ensures every request includes the required `X-API-Key` header automatically.

## 📊 Rate Limiting

API endpoints are rate-limited to **10 requests per minute** per client (IP + User-Agent).

**Rate limit headers:**

- `X-RateLimit-Limit`: Maximum requests allowed
- `X-RateLimit-Remaining`: Remaining requests in current window
- `X-RateLimit-Reset`: Unix timestamp when limit resets

Disable rate limiting by setting `RATE_LIMITING_ENABLED=false`.

## 🔌 Endpoints

### Health Check

Check API health and system status.

```http
GET /health
```

**Response (200 OK):**

```json
{
  "status": "healthy",
  "version": "0.1.0",
  "timestamp": "2024-01-01T12:00:00Z",
  "checks": {
    "database": "ok",
    "settings": "ok"
  }
}
```

**Tags:** `monitoring`

**No authentication required**

---

### Get Top Tweets

Retrieve highest-scoring tweets based on salience.

```http
GET /top?limit=50&min_salience=0.0&hours=24
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | 50 | Maximum tweets to return (1-200) |
| `min_salience` | float | 0.0 | Minimum salience score filter (0-100) |
| `hours` | integer | null | Filter to tweets from last N hours (1-168) |

**Response (200 OK):**

```json
[
  {
    "tweet_id": "1234567890",
    "text": "Help! The service is down and I can't login.",
    "author_username": "user123",
    "created_at": "2024-01-01T10:00:00Z",
    "like_count": 15,
    "retweet_count": 8,
    "reply_count": 5,
    "quote_count": 2,
    "category": "outage",
    "sentiment": "negative",
    "urgency": 4,
    "tags": ["outage", "login"],
    "salience": 85.5,
    "url": "https://x.com/user123/status/1234567890"
  }
]
```

**Tags:** `tweets`

**Authentication:** Required

---

### Get Tweet by ID

Retrieve detailed information about a specific tweet.

```http
GET /tweet/{tweet_id}
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `tweet_id` | string | Tweet ID (required, path parameter) |

**Response (200 OK):**

```json
{
  "tweet_id": "1234567890",
  "text": "Help! The service is down and I can't login.",
  "author_id": "987654321",
  "author_username": "user123",
  "created_at": "2024-01-01T10:00:00Z",
  "lang": "en",
  "like_count": 15,
  "retweet_count": 8,
  "reply_count": 5,
  "quote_count": 2,
  "category": "outage",
  "sentiment": "negative",
  "urgency": 4,
  "tags": ["outage", "login", "urgent"],
  "reasoning": "User reports service outage with login issues",
  "salience": 85.5,
  "notified_at": "2024-01-01T10:05:00Z",
  "url": "https://x.com/user123/status/1234567890"
}
```

**Response (404 Not Found):**

```json
{
  "detail": "Not found"
}
```

**Tags:** `tweets`

**Authentication:** Required

---

### Run Pipeline

Execute the complete harvest pipeline.

```http
POST /refresh?notify_threshold=80.0&notify_limit=10&notify_hours=24
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `notify_threshold` | float | null | Minimum salience for notifications (0-100) |
| `notify_limit` | integer | 10 | Maximum notifications to send (0-50) |
| `notify_hours` | integer | null | Only consider recent tweets from last N hours (1-168) |

**Response (200 OK):**

```json
{
  "fetched": 25,
  "analyzed": 25,
  "scored": 25,
  "notified": 3
}
```

**Tags:** `pipeline`

**Authentication:** Required

**Rate Limited:** Yes

---

## 📚 Data Models

### Tweet Object

```typescript
{
  tweet_id: string,              // Unique tweet identifier
  text: string,                  // Tweet content
  author_id: string,             // Author ID
  author_username: string,       // Author handle
  created_at: string,            // ISO 8601 timestamp
  lang: string,                  // Language code
  like_count: number,            // Number of likes
  retweet_count: number,         // Number of retweets
  reply_count: number,           // Number of replies
  quote_count: number,           // Number of quotes
  category: string,              // Classification category
  sentiment: string,             // Sentiment analysis
  urgency: number,               // Urgency score (0-5)
  tags: string[],                // Array of tags
  reasoning: string,             // Analysis reasoning
  salience: number,              // Salience score (0-100)
  notified_at: string,           // Notification timestamp
  url: string                    // Direct URL to tweet
}
```

### Categories

- `outage` - Service outage or downtime
- `security` - Security vulnerability or breach
- `bug` - Software bug or error
- `question` - User question or inquiry
- `praise` - Positive feedback
- `other` - Uncategorized content

### Sentiments

- `positive` - Positive sentiment
- `neutral` - Neutral sentiment
- `negative` - Negative sentiment

---

## 📡 Signals & Snapshots API

The Signals & Snapshots API provides modern endpoints for managing signals (social media items) and their snapshots with full pagination, filtering, and bulk operations support.

### List Signals

Get paginated list of signals with optional filters.

```http
GET /signals?page=1&pageSize=20&search=bug&status=active&sort=createdAt&order=desc
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | integer | 1 | Page number (≥1) |
| `pageSize` | integer | 20 | Items per page (1-100) |
| `search` | string | null | Search in text and username |
| `status` | string | null | Filter by status: active, inactive, paused, error |
| `source` | string | null | Filter by source (e.g., "x") |
| `sort` | string | createdAt | Sort field: name, status, lastSeenAt, createdAt, updatedAt |
| `order` | string | desc | Sort order: asc, desc |

**Response (200 OK):**

```json
{
  "items": [
    {
      "id": "1234567890",
      "name": "user123",
      "source": "x",
      "status": "active",
      "tags": ["bug", "urgent"],
      "lastSeenAt": "2024-01-01T10:00:00Z",
      "createdAt": "2024-01-01T09:00:00Z",
      "updatedAt": "2024-01-01T10:30:00Z"
    }
  ],
  "total": 150,
  "page": 1,
  "pageSize": 20
}
```

**Tags:** `signals`

---

### Get Signal Statistics

Get aggregated statistics for all signals.

```http
GET /signals/stats
```

**Response (200 OK):**

```json
{
  "total": 150,
  "active": 100,
  "paused": 20,
  "error": 10,
  "inactive": 20
}
```

**Tags:** `signals`

---

### Get Signal by ID

Retrieve detailed information about a specific signal.

```http
GET /signals/{signal_id}
```

**Response (200 OK):**

```json
{
  "id": "1234567890",
  "name": "user123",
  "source": "x",
  "status": "active",
  "tags": ["bug", "urgent"],
  "lastSeenAt": "2024-01-01T10:00:00Z",
  "createdAt": "2024-01-01T09:00:00Z",
  "updatedAt": "2024-01-01T10:30:00Z"
}
```

**Response (404 Not Found):**

```json
{
  "detail": "Signal not found"
}
```

**Tags:** `signals`

---

### Create Signal

Create a new signal.

```http
POST /signals
Content-Type: application/json

{
  "name": "new_signal",
  "source": "x",
  "status": "active",
  "tags": ["test"]
}
```

**Response (201 Created):**

```json
{
  "id": "9876543210",
  "name": "new_signal",
  "source": "x",
  "status": "active",
  "tags": ["test"],
  "createdAt": "2024-01-01T11:00:00Z",
  "updatedAt": "2024-01-01T11:00:00Z"
}
```

**Tags:** `signals`

---

### Update Signal

Update an existing signal with partial data.

```http
PATCH /signals/{signal_id}
Content-Type: application/json

{
  "status": "paused",
  "tags": ["updated"]
}
```

**Response (200 OK):**

```json
{
  "id": "1234567890",
  "name": "user123",
  "source": "x",
  "status": "paused",
  "tags": ["updated"],
  "lastSeenAt": "2024-01-01T10:00:00Z",
  "createdAt": "2024-01-01T09:00:00Z",
  "updatedAt": "2024-01-01T11:15:00Z"
}
```

**Tags:** `signals`

---

### Delete Signal

Delete a signal by ID.

```http
DELETE /signals/{signal_id}
```

**Response (204 No Content)**

**Tags:** `signals`

---

### List Snapshots

Get paginated list of snapshots with optional filters.

```http
GET /snapshots?page=1&pageSize=20&status=ready&signalId=123
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | integer | 1 | Page number (≥1) |
| `pageSize` | integer | 20 | Items per page (1-100) |
| `search` | string | null | Search query |
| `status` | string | null | Filter by status: ready, processing, failed |
| `signalId` | string | null | Filter by signal ID |

**Response (200 OK):**

```json
{
  "items": [
    {
      "id": "snap_123",
      "signalId": "1234567890",
      "signalName": "user123",
      "status": "ready",
      "sizeKb": 256,
      "createdAt": "2024-01-01T12:00:00Z"
    }
  ],
  "total": 50,
  "page": 1,
  "pageSize": 20
}
```

**Tags:** `snapshots`

---

### Get Snapshot by ID

Retrieve detailed information about a specific snapshot.

```http
GET /snapshots/{snapshot_id}
```

**Response (200 OK):**

```json
{
  "id": "snap_123",
  "signalId": "1234567890",
  "signalName": "user123",
  "status": "ready",
  "sizeKb": 256,
  "createdAt": "2024-01-01T12:00:00Z"
}
```

**Response (404 Not Found):**

```json
{
  "detail": "Snapshot not found"
}
```

**Tags:** `snapshots`

---

### Create Snapshot

Create a new snapshot for a signal.

```http
POST /snapshots
Content-Type: application/json

{
  "signalId": "1234567890",
  "filePath": "/data/snapshots/signal_123.json",
  "sizeKb": 512
}
```

**Request Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `signalId` | string | Yes | ID of the signal to snapshot |
| `filePath` | string | No | Path where snapshot file is stored |
| `sizeKb` | integer | No | Size of snapshot in kilobytes |

**Response (201 Created):**

```json
{
  "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "signalId": "1234567890",
  "signalName": "user123",
  "status": "processing",
  "sizeKb": 512,
  "filePath": "/data/snapshots/signal_123.json",
  "createdAt": "2024-01-01T12:30:00Z"
}
```

**Response (404 Not Found):**

```json
{
  "detail": "Signal not found"
}
```

**Tags:** `snapshots`

**Notes:**

- Snapshot status will be `ready` if `filePath` is provided, otherwise `processing`
- Signal must exist in the database before creating a snapshot
- Snapshots are automatically assigned a UUID identifier

---

## 🔄 Bulk Operations API

The Bulk Operations API provides endpoints for performing batch updates and deletions with real-time progress tracking via Server-Sent Events (SSE).

### Bulk Update Signal Status

Update status for multiple signals matching the provided scope.

```http
POST /signals/bulk/status
Content-Type: application/json

{
  "ids": ["1001", "1002", "1003"],
  "status": "paused"
}
```

**Or with filters:**

```json
{
  "filters": {
    "search": "bug",
    "status": "active"
  },
  "status": "paused"
}
```

**Response (200 OK):**

```json
{
  "jobId": "550e8400-e29b-41d4-a716-446655440000",
  "total": 3
}
```

**Tags:** `signals`, `bulk`

---

### Bulk Delete Signals

Delete multiple signals matching the provided scope.

```http
POST /signals/bulk/delete
Content-Type: application/json

{
  "ids": ["1001", "1002", "1003"]
}
```

**Or with filters:**

```json
{
  "filters": {
    "status": "error",
    "source": "x"
  }
}
```

**Response (200 OK):**

```json
{
  "jobId": "550e8400-e29b-41d4-a716-446655440000",
  "total": 10
}
```

**Tags:** `signals`, `bulk`

---

### Get Bulk Job Status

Get the current status of a bulk operation job.

```http
GET /bulk-jobs/{job_id}
```

**Response (200 OK):**

```json
{
  "jobId": "550e8400-e29b-41d4-a716-446655440000",
  "status": "running",
  "total": 10,
  "done": 7,
  "fail": 0
}
```

**Status values:**

- `running` - Job in progress
- `completed` - Job finished successfully
- `cancelled` - Job was cancelled
- `failed` - Job encountered an error

**Tags:** `bulk`

---

### Cancel Bulk Job

Cancel a running bulk operation job.

```http
POST /bulk-jobs/{job_id}/cancel
```

**Response (204 No Content)**

**Tags:** `bulk`

---

### Stream Bulk Job Updates (SSE)

Server-Sent Events stream for real-time bulk job progress updates.

```http
GET /bulk-jobs/{job_id}/stream
```

**Response (200 OK):**

```
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive

data: {"jobId":"550e8400-e29b-41d4-a716-446655440000","status":"running","total":10,"done":0,"fail":0}

data: {"jobId":"550e8400-e29b-41d4-a716-446655440000","status":"running","total":10,"done":5,"fail":0}

data: {"jobId":"550e8400-e29b-41d4-a716-446655440000","status":"completed","total":10,"done":10,"fail":0}
```

**JavaScript Example:**

```javascript
const eventSource = new EventSource(`/bulk-jobs/${jobId}/stream`);

eventSource.onmessage = (event) => {
  const status = JSON.parse(event.data);
  console.log(`Progress: ${status.done}/${status.total}`);
  
  if (status.status !== 'running') {
    eventSource.close();
  }
};
```

**Tags:** `bulk`

---

## 🚨 Error Responses

### 401 Unauthorized

```json
{
  "detail": "Invalid API key"
}
```

**When:** API key is missing or invalid

### 404 Not Found

```json
{
  "detail": "Not found"
}
```

**When:** Tweet ID not found

### 429 Too Many Requests

```json
{
  "detail": "Rate limit exceeded. Retry after 45 seconds."
}
```

**Headers:**

```
Retry-After: 45
```

**When:** Rate limit exceeded

## 💡 Examples

### Python Client

```python
import requests

API_KEY = "your_api_key_here"
BASE_URL = "http://localhost:8000"

headers = {"X-API-Key": API_KEY}

# Get top tweets
response = requests.get(
    f"{BASE_URL}/top",
    headers=headers,
    params={"limit": 10, "min_salience": 75.0}
)
tweets = response.json()

# Get specific tweet
response = requests.get(
    f"{BASE_URL}/tweet/1234567890",
    headers=headers
)
tweet = response.json()

# Run pipeline
response = requests.post(
    f"{BASE_URL}/refresh",
    headers=headers,
    params={"notify_threshold": 80.0, "notify_limit": 5}
)
stats = response.json()
print(f"Fetched: {stats['fetched']}, Analyzed: {stats['analyzed']}")
```

### cURL Examples

```bash
# Health check
curl http://localhost:8000/health

# Get top tweets
curl -H "X-API-Key: $API_KEY" \
  "http://localhost:8000/top?limit=20&min_salience=70.0"

# Get specific tweet
curl -H "X-API-Key: $API_KEY" \
  http://localhost:8000/tweet/1234567890

# Run pipeline
curl -X POST -H "X-API-Key: $API_KEY" \
  "http://localhost:8000/refresh?notify_threshold=80.0&notify_limit=10"
```

## ⚠️ Error Codes & Troubleshooting

The API uses standard HTTP status codes and returns structured error responses for all failures.

### Error Response Format

All error responses follow this structure:

```json
{
  "detail": "Human-readable error message",
  "error_code": "SPECIFIC_ERROR_CODE",
  "timestamp": "2025-11-11T12:00:00Z"
}
```

### HTTP Status Codes

#### 400 Bad Request

**Cause:** Invalid request parameters or malformed input.

**Common Scenarios:**

- Invalid query parameters (e.g., `limit=-1`, `min_salience=150`)
- Malformed JSON in request body
- Missing required fields in POST/PUT requests
- Invalid date/time formats

**Example Response:**

```json
{
  "detail": "Validation error: limit must be between 1 and 200",
  "error_code": "INVALID_PARAMETER"
}
```

**Troubleshooting:**

1. Verify parameter types match API specification
2. Check parameter value ranges (e.g., `limit` 1-200, `salience` 0-100)
3. Ensure required fields are present in request body
4. Validate JSON syntax if sending POST/PUT requests

---

#### 401 Unauthorized

**Cause:** Missing or invalid API key.

**Common Scenarios:**

- `X-API-Key` header not provided
- API key does not match `HARVEST_API_KEY` environment variable
- API key contains extra whitespace or special characters

**Example Response:**

```json
{
  "detail": "Invalid or missing API key",
  "error_code": "UNAUTHORIZED"
}
```

**Troubleshooting:**

1. Verify `X-API-Key` header is present in request
2. Check `HARVEST_API_KEY` environment variable is set correctly
3. Ensure no trailing whitespace in API key
4. Test with health endpoint (`/health`) which doesn't require auth
5. Restart API server if environment variable was recently changed

**cURL Test:**

```bash
# Should fail
curl -v http://localhost:8000/top

# Should succeed (replace YOUR_KEY)
curl -H "X-API-Key: YOUR_KEY" http://localhost:8000/top
```

---

#### 403 Forbidden

**Cause:** Valid authentication but insufficient permissions for requested resource.

**Common Scenarios:**

- Attempting to access admin-only endpoints
- API key valid but lacks required scope
- Rate limit exceeded (see 429 for rate limiting)

**Example Response:**

```json
{
  "detail": "Insufficient permissions to access this resource",
  "error_code": "FORBIDDEN"
}
```

**Troubleshooting:**

1. Verify API key has required permissions/scope
2. Check if endpoint requires elevated privileges
3. Contact administrator to grant necessary permissions

---

#### 404 Not Found

**Cause:** Requested resource does not exist.

**Common Scenarios:**

- Tweet ID not found in database
- Snapshot ID does not exist
- Discovery artifact ID invalid
- Endpoint URL misspelled or deprecated

**Example Response:**

```json
{
  "detail": "Tweet with ID '1234567890' not found",
  "error_code": "RESOURCE_NOT_FOUND"
}
```

**Troubleshooting:**

1. Verify resource ID exists using list endpoints (e.g., `/top`, `/discoveries`)
2. Check for typos in endpoint URL
3. Ensure resource hasn't been deleted via retention policies
4. For tweets: verify ID is a valid Twitter/X tweet ID format
5. For discoveries: check artifact was successfully fetched and scored

**Debug Commands:**

```bash
# List all tweets to find valid IDs
curl -H "X-API-Key: $API_KEY" "http://localhost:8000/top?limit=200"

# List all discoveries
curl -H "X-API-Key: $API_KEY" "http://localhost:8000/discoveries?limit=100"

# Check database directly
harvest stats
```

---

#### 422 Unprocessable Entity

**Cause:** Request syntax is valid but semantic validation failed.

**Common Scenarios:**

- Pydantic validation errors (type mismatches)
- Invalid enum values (e.g., `category="invalid"`)
- Business logic constraints violated (e.g., `end_date < start_date`)
- Invalid JSON structure that parses but doesn't match schema

**Example Response:**

```json
{
  "detail": [
    {
      "type": "int_parsing",
      "loc": ["query", "limit"],
      "msg": "Input should be a valid integer",
      "input": "abc"
    }
  ]
}
```

**Troubleshooting:**

1. Review validation error details in `detail` array
2. Check `loc` field to identify problematic parameter
3. Verify data types match API schema (see `/docs` for schema)
4. For enums, check allowed values (e.g., `sentiment`: positive/negative/neutral)
5. Validate date ranges and logical constraints

**Common Validation Errors:**

| Field | Expected Type | Valid Values/Range |
|-------|---------------|-------------------|
| `limit` | integer | 1-200 |
| `min_salience` | float | 0.0-100.0 |
| `hours` | integer | 1-168 (7 days) |
| `sentiment` | string | positive, negative, neutral |
| `category` | string | outage, bug, feature_request, question, praise, other |

---

#### 429 Too Many Requests

**Cause:** Rate limit exceeded.

**Common Scenarios:**

- More than 10 requests per minute from same IP + User-Agent
- Bulk operations hitting API too quickly
- Automated scripts without rate limiting

**Example Response:**

```json
{
  "detail": "Rate limit exceeded. Please wait before retrying.",
  "error_code": "RATE_LIMIT_EXCEEDED"
}
```

**Response Headers:**

```
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1699704125
Retry-After: 45
```

**Troubleshooting:**

1. Check `Retry-After` header for wait time in seconds
2. Implement exponential backoff in client code
3. Monitor `X-RateLimit-Remaining` header proactively
4. For development, disable rate limiting: `RATE_LIMITING_ENABLED=false`
5. For production, request rate limit increase or batch operations

**Client Implementation:**

```python
import time
import requests

def api_call_with_retry(url, headers, max_retries=3):
    for attempt in range(max_retries):
        response = requests.get(url, headers=headers)
        
        if response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 60))
            print(f"Rate limited. Waiting {retry_after}s...")
            time.sleep(retry_after)
            continue
        
        return response
    
    raise Exception("Max retries exceeded")
```

---

#### 500 Internal Server Error

**Cause:** Unexpected server error.

**Common Scenarios:**

- Database connection failures
- LLM API errors (OpenAI, Anthropic, xAI)
- Unhandled exceptions in pipeline code
- Configuration errors (invalid settings.yaml)
- Out of memory or disk space

**Example Response:**

```json
{
  "detail": "An internal error occurred. Please contact support.",
  "error_code": "INTERNAL_ERROR",
  "request_id": "abc123-def456"
}
```

**Troubleshooting:**

1. Check application logs: `tail -f logs/app.log`
2. Verify database accessibility: `harvest stats`
3. Test LLM API connectivity: `curl https://api.openai.com/v1/models -H "Authorization: Bearer $OPENAI_API_KEY"`
4. Validate settings.yaml: `python -c "import yaml; yaml.safe_load(open('config/settings.yaml'))"`
5. Check disk space: `df -h var/`
6. Review Sentry error tracking if configured
7. Restart API server: `docker-compose restart signal-harvester`

**Debug Commands:**

```bash
# Check database integrity
harvest verify

# Test pipeline components
harvest fetch --limit 1
harvest analyze --limit 1

# View recent errors
grep ERROR logs/app.log | tail -20

# Check system resources
docker stats signal-harvester
```

---

#### 503 Service Unavailable

**Cause:** Service temporarily unavailable or overloaded.

**Common Scenarios:**

- Database locked (SQLite BUSY error)
- External API dependencies down (X API, LLM providers)
- Server startup/shutdown in progress
- Resource exhaustion (CPU, memory, connections)

**Example Response:**

```json
{
  "detail": "Service temporarily unavailable. Please retry.",
  "error_code": "SERVICE_UNAVAILABLE"
}
```

**Troubleshooting:**

1. Check health endpoint: `curl http://localhost:8000/health`
2. Verify external dependencies:
   - X API: `curl -H "Authorization: Bearer $X_BEARER_TOKEN" https://api.twitter.com/2/tweets/search/recent`
   - OpenAI: `curl https://api.openai.com/v1/models -H "Authorization: Bearer $OPENAI_API_KEY"`
3. Check for database locks: `lsof var/app.db`
4. Monitor system resources: `docker stats`
5. Review recent deployments or configuration changes
6. Implement retry logic with exponential backoff
7. Check for ongoing maintenance windows

**Database Lock Resolution:**

```bash
# Check for long-running queries/locks
sqlite3 var/app.db "PRAGMA busy_timeout;"

# Kill stuck processes (last resort)
pkill -f "harvest pipeline"

# Restart services
docker-compose restart
```

---

### Endpoint-Specific Errors

#### GET /discoveries

**Additional Errors:**

- **404**: No discoveries found matching filters
- **422**: Invalid `source` value (must be: arxiv, github, x, facebook, linkedin)
- **422**: `min_score` outside range 0-100

#### POST /signals/bulk/status

**Additional Errors:**

- **422**: Empty `tweet_ids` array
- **422**: `new_status` invalid (must be: pending, analyzed, exported, archived)
- **404**: None of provided tweet IDs found in database

#### GET /artifacts/{id}/citation-graph

**Additional Errors:**

- **404**: Artifact ID not found
- **422**: `max_depth` outside range 1-5
- **422**: `min_confidence` outside range 0.0-1.0

#### POST /experiments

**Additional Errors:**

- **422**: Duplicate experiment name
- **422**: Invalid scoring weights (must sum to reasonable total)
- **422**: `baseline_id` references non-existent experiment

---

### Error Monitoring

**Sentry Integration:**

If `SENTRY_DSN` is configured, all 500 errors are automatically reported to Sentry with:

- Full stack trace
- Request context (URL, headers, parameters)
- User context (IP, User-Agent)
- Server context (hostname, environment)

**Log Analysis:**

```bash
# Count errors by status code
grep "status_code=" logs/app.log | awk -F'status_code=' '{print $2}' | sort | uniq -c

# Find recent 500 errors
grep "500" logs/app.log | tail -20

# Track specific error codes
grep "RATE_LIMIT_EXCEEDED" logs/app.log | wc -l
```

**Prometheus Metrics:**

If Prometheus is enabled, track error rates:

```promql
# Error rate by status code
rate(http_requests_total{status=~"5.."}[5m])

# 429 rate limiting events
rate(http_requests_total{status="429"}[5m])
```

## 🔧 Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HARVEST_API_KEY` | null | API key for authentication |
| `RATE_LIMITING_ENABLED` | true | Enable/disable rate limiting |
| `DATABASE_PATH` | var/app.db | Database file path |
| `LOG_LEVEL` | INFO | Logging level |
| `LOG_FORMAT` | console | Log format (console/json) |

### Settings File

Configure queries and scoring weights in `config/settings.yaml`:

```yaml
app:
  fetch:
    max_results: 50
  llm:
    provider: "openai"
  scoring:
    weights:
      urgency: 4.0
      category_boosts:
        outage: 2.0

queries:
  - name: "brand_monitoring"
    query: "(@YourBrand) (help OR support OR bug) -is:retweet"
    enabled: true
```

## 📖 OpenAPI/Swagger UI

Access interactive API documentation at:

```
http://localhost:8000/docs
```

Access ReDoc documentation at:

```
http://localhost:8000/redoc
```

## 🤝 Support

- Check [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues
- Review [DEPLOYMENT.md](DEPLOYMENT.md) for deployment help
- Open an issue on GitHub for bugs/feature requests
