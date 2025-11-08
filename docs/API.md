# Signal Harvester API Documentation

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
