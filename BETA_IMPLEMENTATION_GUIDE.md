# Signal Harvester - Beta Implementation Guide

## 🛠️ Technical Implementation Details

This guide provides step-by-step implementation details for critical beta readiness tasks.

---

## 1. Error Tracking with Sentry

### Backend Integration

**Step 1**: Install Sentry SDK
```bash
cd signal-harvester
pip install "sentry-sdk[fastapi]>=2.0.0"
```

**Step 2**: Add to `pyproject.toml`
```toml
dependencies = [
  # ... existing dependencies
  "sentry-sdk[fastapi]>=2.0.0",
]
```

**Step 3**: Configure Sentry in `api.py`
```python
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration

# Initialize Sentry
def init_sentry():
    dsn = os.getenv("SENTRY_DSN")
    if dsn:
        sentry_sdk.init(
            dsn=dsn,
            integrations=[FastApiIntegration()],
            traces_sample_rate=1.0,  # Capture 100% of transactions for beta
            profiles_sample_rate=1.0,
            environment=os.getenv("ENVIRONMENT", "beta"),
            release=f"signal-harvester@{__version__}",
            # Add custom tags
            initial_scope={
                "tags": {"component": "api"}
            }
        )

# Call in create_app()
def create_app(settings_path: Optional[str] = None) -> FastAPI:
    init_sentry()
    # ... rest of function
```

**Step 4**: Add custom error handling
```python
from fastapi import Request
from fastapi.responses import JSONResponse

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all exception handler that reports to Sentry."""
    # Sentry will automatically capture this
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": "An unexpected error occurred. Our team has been notified.",
            "error_id": getattr(exc, "error_id", None)
        }
    )
```

### Frontend Integration

**Step 1**: Install Sentry packages
```bash
cd signal-harvester/frontend
npm install @sentry/react @sentry/tracing
```

**Step 2**: Initialize Sentry in `main.tsx`
```typescript
import * as Sentry from "@sentry/react";

Sentry.init({
  dsn: import.meta.env.VITE_SENTRY_DSN,
  integrations: [
    new Sentry.BrowserTracing({
      tracePropagationTargets: ["localhost", /^https:\/\/yourserver\.com\/api/],
    }),
    new Sentry.Replay(),
  ],
  tracesSampleRate: 1.0,
  replaysSessionSampleRate: 0.1,
  replaysOnErrorSampleRate: 1.0,
  environment: import.meta.env.VITE_ENVIRONMENT || "beta",
  release: `signal-harvester-frontend@${import.meta.env.VITE_APP_VERSION || "0.1.0"}`,
  beforeSend(event) {
    // Filter out sensitive data
    if (event.request?.headers?.["X-API-Key"]) {
      delete event.request.headers["X-API-Key"];
    }
    return event;
  }
});
```

**Step 3**: Add error boundary
```typescript
// src/components/ErrorBoundary.tsx
import React from 'react';
import * as Sentry from "@sentry/react";

export default function ErrorBoundary({ children }: { children: React.ReactNode }) {
  return (
    <Sentry.ErrorBoundary
      fallback={({ error, resetError }) => (
        <div className="flex flex-col items-center justify-center min-h-screen p-4">
          <h1 className="text-2xl font-bold mb-4">Something went wrong</h1>
          <p className="text-muted-foreground mb-4">
            We've been notified and are working on a fix.
          </p>
          <button
            onClick={resetError}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-md"
          >
            Try again
          </button>
        </div>
      )}
    >
      {children}
    </Sentry.ErrorBoundary>
  );
}

// Wrap App in main.tsx
<ErrorBoundary>
  <App />
</ErrorBoundary>
```

---

## 2. Beta User Management System

### Database Schema

**Step 1**: Create migration for beta users
```python
# migrations/versions/20251108_0002_beta_users.py
"""Add beta users table."""

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.create_table(
        'beta_users',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('email', sa.String(255), nullable=False, unique=True),
        sa.Column('invite_code', sa.String(64), nullable=False, unique=True),
        sa.Column('status', sa.String(20), nullable=False, default='pending'),  # pending, active, expired
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('activated_at', sa.DateTime, nullable=True),
        sa.Column('metadata', sa.Text, nullable=True),  # JSON string
    )
    op.create_index('idx_beta_users_email', 'beta_users', ['email'])
    op.create_index('idx_beta_users_invite_code', 'beta_users', ['invite_code'])
    op.create_index('idx_beta_users_status', 'beta_users', ['status'])


def downgrade() -> None:
    op.drop_table('beta_users')
```

**Step 2**: Apply migration
```bash
alembic upgrade head
```

### Beta Management Module

**Step 3**: Create `beta.py` module
```python
# src/signal_harvester/beta.py
from __future__ import annotations

import json
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .db import get_connection


@dataclass
class BetaUser:
    id: int
    email: str
    invite_code: str
    status: str
    created_at: datetime
    activated_at: Optional[datetime]
    metadata: dict


def generate_invite_code(length: int = 32) -> str:
    """Generate a secure invite code."""
    return secrets.token_urlsafe(length)


def create_beta_user(email: str, metadata: Optional[dict] = None) -> BetaUser:
    """Create a new beta user with invite code."""
    invite_code = generate_invite_code()
    metadata_json = json.dumps(metadata or {})
    
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO beta_users (email, invite_code, metadata)
            VALUES (?, ?, ?)
            RETURNING id, email, invite_code, status, created_at, activated_at, metadata
            """,
            (email, invite_code, metadata_json)
        )
        row = cursor.fetchone()
        
    return BetaUser(
        id=row[0],
        email=row[1],
        invite_code=row[2],
        status=row[3],
        created_at=datetime.fromisoformat(row[4]),
        activated_at=datetime.fromisoformat(row[5]) if row[5] else None,
        metadata=json.loads(row[6])
    )


def get_beta_user_by_invite(invite_code: str) -> Optional[BetaUser]:
    """Get beta user by invite code."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM beta_users WHERE invite_code = ?",
            (invite_code,)
        )
        row = cursor.fetchone()
        
    if not row:
        return None
        
    return BetaUser(
        id=row[0],
        email=row[1],
        invite_code=row[2],
        status=row[3],
        created_at=datetime.fromisoformat(row[4]),
        activated_at=datetime.fromisoformat(row[5]) if row[5] else None,
        metadata=json.loads(row[6])
    )


def activate_beta_user(invite_code: str) -> bool:
    """Activate a beta user."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE beta_users 
            SET status = 'active', activated_at = CURRENT_TIMESTAMP 
            WHERE invite_code = ? AND status = 'pending'
            RETURNING id
            """,
            (invite_code,)
        )
        return cursor.fetchone() is not None


def list_beta_users(status: Optional[str] = None) -> list[BetaUser]:
    """List beta users, optionally filtered by status."""
    with get_connection() as conn:
        if status:
            cursor = conn.execute(
                "SELECT * FROM beta_users WHERE status = ? ORDER BY created_at DESC",
                (status,)
            )
        else:
            cursor = conn.execute("SELECT * FROM beta_users ORDER BY created_at DESC")
        
        rows = cursor.fetchall()
        
    return [
        BetaUser(
            id=row[0],
            email=row[1],
            invite_code=row[2],
            status=row[3],
            created_at=datetime.fromisoformat(row[4]),
            activated_at=datetime.fromisoformat(row[5]) if row[5] else None,
            metadata=json.loads(row[6])
        )
        for row in rows
    ]
```

### CLI Commands

**Step 4**: Add beta management commands to `cli/core.py`
```python
# src/signal_harvester/cli/core.py

@app.command("beta-invite")
def beta_invite(
    email: str = typer.Argument(..., help="Email address to invite"),
    name: Optional[str] = typer.Option(None, "--name", help="User name"),
) -> None:
    """Create a beta invite for a user."""
    from ..beta import create_beta_user
    
    user = create_beta_user(email, metadata={"name": name})
    console.print(f"✅ Created beta invite for {email}")
    console.print(f"Invite code: {user.invite_code}")
    console.print(f"Status: {user.status}")


@app.command("beta-list")
def beta_list(
    status: Optional[str] = typer.Option(None, "--status", help="Filter by status"),
) -> None:
    """List beta users."""
    from ..beta import list_beta_users
    
    users = list_beta_users(status)
    
    if not users:
        console.print("No beta users found")
        return
        
    table = Table(title="Beta Users")
    table.add_column("Email", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Created", style="yellow")
    table.add_column("Activated", style="magenta")
    
    for user in users:
        table.add_row(
            user.email,
            user.status,
            user.created_at.strftime("%Y-%m-%d"),
            user.activated_at.strftime("%Y-%m-%d") if user.activated_at else "-"
        )
    
    console.print(table)
```

---

## 3. Feature Flags System

**Step 1**: Create feature flags module
```python
# src/signal_harvester/feature_flags.py
from __future__ import annotations

import json
import os
from typing import Any, Dict


class FeatureFlags:
    """Simple feature flag system using environment variables."""
    
    def __init__(self):
        self.flags: Dict[str, bool] = {}
        self._load_flags()
    
    def _load_flags(self) -> None:
        """Load feature flags from environment."""
        # Default flags
        self.flags = {
            "beta_mode": os.getenv("BETA_MODE", "true").lower() == "true",
            "new_ui": os.getenv("FEATURE_NEW_UI", "false").lower() == "true",
            "advanced_analytics": os.getenv("FEATURE_ADVANCED_ANALYTICS", "false").lower() == "true",
            "slack_integration": os.getenv("FEATURE_SLACK", "true").lower() == "true",
            "export_csv": os.getenv("FEATURE_EXPORT", "true").lower() == "true",
        }
        
        # Override from JSON if provided
        flags_json = os.getenv("FEATURE_FLAGS")
        if flags_json:
            try:
                self.flags.update(json.loads(flags_json))
            except json.JSONDecodeError:
                pass
    
    def is_enabled(self, flag: str) -> bool:
        """Check if a feature flag is enabled."""
        return self.flags.get(flag, False)
    
    def all_flags(self) -> Dict[str, bool]:
        """Get all feature flags."""
        return self.flags.copy()


# Global instance
_feature_flags = FeatureFlags()

def is_enabled(flag: str) -> bool:
    """Check if a feature flag is enabled."""
    return _feature_flags.is_enabled(flag)

def all_flags() -> Dict[str, bool]:
    """Get all feature flags."""
    return _feature_flags.all_flags()
```

**Step 2**: Use feature flags in API
```python
# src/signal_harvester/api.py
from .feature_flags import is_enabled

@app.get("/features")
def get_features() -> Dict[str, Any]:
    """Get enabled features for the frontend."""
    return {
        "beta_mode": is_enabled("beta_mode"),
        "new_ui": is_enabled("new_ui"),
        "advanced_analytics": is_enabled("advanced_analytics"),
        "slack_integration": is_enabled("slack_integration"),
        "export_csv": is_enabled("export_csv"),
    }
```

---

## 4. End-to-End Testing with Cypress

**Step 1**: Install Cypress
```bash
cd signal-harvester/frontend
npm install --save-dev cypress
```

**Step 2**: Add scripts to `package.json`
```json
{
  "scripts": {
    "test:e2e": "cypress open",
    "test:e2e:headless": "cypress run"
  }
}
```

**Step 3**: Create first test
```typescript
// frontend/cypress/e2e/signals.cy.ts
describe('Signals Workflow', () => {
  beforeEach(() => {
    // Seed test data
    cy.request('POST', 'http://localhost:8000/refresh', {}, {
      headers: { 'X-API-Key': 'test-key' }
    })
  })

  it('should display signals', () => {
    cy.visit('/signals')
    
    // Should show signals table
    cy.get('[data-testid="signals-table"]').should('exist')
    
    // Should show at least one signal
    cy.get('[data-testid="signal-row"]').should('have.length.greaterThan', 0)
  })

  it('should create a new signal', () => {
    cy.visit('/signals/new')
    
    // Fill form
    cy.get('input[name="tweet_url"]').type('https://twitter.com/test/status/123456')
    cy.get('select[name="category"]').select('bug_report')
    cy.get('textarea[name="notes"]').type('Test signal from E2E test')
    
    // Submit
    cy.get('button[type="submit"]').click()
    
    // Should redirect to signals list
    cy.url().should('include', '/signals')
    
    // Should show success message
    cy.get('[data-testid="toast-success"]').should('exist')
  })

  it('should create and view snapshot', () => {
    cy.visit('/snapshots')
    
    // Create snapshot
    cy.get('button[data-testid="create-snapshot"]').click()
    cy.get('input[name="name"]').type('E2E Test Snapshot')
    cy.get('button[type="submit"]').click()
    
    // Should show in list
    cy.get('[data-testid="snapshot-name"]').should('contain', 'E2E Test Snapshot')
    
    // Click to view detail
    cy.get('[data-testid="view-snapshot"]').first().click()
    
    // Should show snapshot detail
    cy.url().should('include', '/snapshots/')
    cy.get('[data-testid="snapshot-detail"]').should('exist')
  })
})
```

**Step 4**: Configure Cypress
```typescript
// frontend/cypress.config.ts
import { defineConfig } from 'cypress'

export default defineConfig({
  e2e: {
    baseUrl: 'http://localhost:5173', // Vite dev server
    setupNodeEvents(on, config) {
      // Implement node event listeners here
    },
    env: {
      apiUrl: 'http://localhost:8000',
      apiKey: 'test-key'
    }
  },
})
```

---

## 5. Structured Logging Configuration

**Step 1**: Update logger configuration
```python
# src/signal_harvester/logger.py
import json
import logging
import sys
from typing import Any


def configure_logging(level: Optional[str] = None) -> None:
    """Configure structured logging."""
    log_level = getattr(logging, (level or os.getenv("LOG_LEVEL", "INFO")).upper())
    log_format = os.getenv("LOG_FORMAT", "text")  # "text" or "json"
    
    if log_format == "json":
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
    
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers = [handler]
    
    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


class JsonFormatter(logging.Formatter):
    """JSON formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        
        # Add extra data if present
        if hasattr(record, "extra"):
            log_obj.update(record.extra)
        
        return json.dumps(log_obj)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)
```

**Step 2**: Use structured logging in code
```python
# Example usage
log.info(
    "Pipeline completed",
    extra={
        "tweets_fetched": stats["fetched"],
        "tweets_analyzed": stats["analyzed"],
        "duration_ms": duration,
        "pipeline_id": pipeline_id
    }
)
```

---

## 6. API Documentation with Examples

**Step 1**: Create API examples directory
```bash
mkdir -p docs/api-examples
cd docs/api-examples
```

**Step 2**: Create Python example
```python
# docs/api-examples/python_client.py
"""Example Python client for Signal Harvester API."""

import os
import httpx

API_KEY = os.getenv("HARVEST_API_KEY")
API_URL = os.getenv("HARVEST_API_URL", "http://localhost:8000")

def get_top_signals(limit: int = 50, min_salience: float = 0.0):
    """Get top-scored signals."""
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/top",
            headers={"X-API-Key": API_KEY},
            params={"limit": limit, "min_salience": min_salience}
        )
        response.raise_for_status()
        return response.json()

def refresh_pipeline():
    """Run the pipeline to fetch and analyze new tweets."""
    with httpx.Client() as client:
        response = client.post(
            f"{API_URL}/refresh",
            headers={"X-API-Key": API_KEY}
        )
        response.raise_for_status()
        return response.json()

def get_tweet(tweet_id: str):
    """Get a specific tweet by ID."""
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/tweet/{tweet_id}",
            headers={"X-API-Key": API_KEY}
        )
        response.raise_for_status()
        return response.json()

# Example usage
if __name__ == "__main__":
    print("Running pipeline...")
    stats = refresh_pipeline()
    print(f"Pipeline stats: {stats}")
    
    print("\nGetting top signals...")
    signals = get_top_signals(limit=10, min_salience=50.0)
    print(f"Found {len(signals)} high-priority signals")
    
    for signal in signals[:3]:  # Show first 3
        print(f"- {signal['tweet_id']}: {signal['salience_score']}")
```

**Step 3**: Create JavaScript example
```javascript
// docs/api-examples/javascript_client.js
"""Example JavaScript/Node.js client for Signal Harvester API."""

const API_KEY = process.env.HARVEST_API_KEY;
const API_URL = process.env.HARVEST_API_URL || 'http://localhost:8000';

async function getTopSignals(limit = 50, minSalience = 0.0) {
  const response = await fetch(
    `${API_URL}/top?limit=${limit}&min_salience=${minSalience}`,
    {
      headers: {
        'X-API-Key': API_KEY,
        'Accept': 'application/json'
      }
    }
  );
  
  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }
  
  return response.json();
}

async function refreshPipeline() {
  const response = await fetch(`${API_URL}/refresh`, {
    method: 'POST',
    headers: {
      'X-API-Key': API_KEY,
      'Accept': 'application/json'
    }
  });
  
  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }
  
  return response.json();
}

// Example usage
async function main() {
  console.log('Running pipeline...');
  const stats = await refreshPipeline();
  console.log('Pipeline stats:', stats);
  
  console.log('\nGetting top signals...');
  const signals = await getTopSignals(10, 50.0);
  console.log(`Found ${signals.length} high-priority signals`);
  
  signals.slice(0, 3).forEach(signal => {
    console.log(`- ${signal.tweet_id}: ${signal.salience_score}`);
  });
}

if (require.main === module) {
  main().catch(console.error);
}

module.exports = { getTopSignals, refreshPipeline };
```

---

## 7. Beta Analytics Dashboard

**Step 1**: Create analytics module
```python
# src/signal_harvester/analytics.py
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List

from .db import get_connection


@dataclass
class DailyMetrics:
    date: str
    tweets_fetched: int
    tweets_analyzed: int
    notifications_sent: int
    active_users: int
    api_requests: int


def get_daily_metrics(days: int = 30) -> List[DailyMetrics]:
    """Get daily metrics for the last N days."""
    with get_connection() as conn:
        # This is a simplified example - adjust based on your schema
        cursor = conn.execute(
            """
            SELECT 
                DATE(created_at) as date,
                COUNT(*) as tweets_fetched,
                SUM(CASE WHEN analysis IS NOT NULL THEN 1 ELSE 0 END) as tweets_analyzed
            FROM tweets
            WHERE created_at >= DATE('now', '-{days} days')
            GROUP BY DATE(created_at)
            ORDER BY date DESC
            """.format(days=days)
        )
        
        rows = cursor.fetchall()
        
    return [
        DailyMetrics(
            date=row[0],
            tweets_fetched=row[1],
            tweets_analyzed=row[2],
            notifications_sent=0,  # Would need notifications table
            active_users=0,  # Would need user tracking
            api_requests=0,  # Would need API request logging
        )
        for row in rows
    ]


def get_beta_metrics() -> Dict[str, Any]:
    """Get beta-specific metrics."""
    from .beta import list_beta_users
    
    users = list_beta_users()
    
    return {
        "total_users": len(users),
        "active_users": len([u for u in users if u.status == "active"]),
        "pending_invites": len([u for u in users if u.status == "pending"]),
        "activation_rate": (
            len([u for u in users if u.status == "active"]) / len(users) * 100
            if users else 0
        ),
    }
```

**Step 2**: Add analytics endpoint
```python
# src/signal_harvester/api.py
from .analytics import get_daily_metrics, get_beta_metrics

@app.get("/analytics/daily")
def get_daily_analytics(
    days: int = Query(30, ge=1, le=365),
    api_key: str = Depends(require_api_key),
) -> List[Dict[str, Any]]:
    """Get daily analytics metrics."""
    metrics = get_daily_metrics(days)
    return [m.__dict__ for m in metrics]

@app.get("/analytics/beta")
def get_beta_analytics(
    api_key: str = Depends(require_api_key),
) -> Dict[str, Any]:
    """Get beta program analytics."""
    return get_beta_metrics()
```

---

## 8. Environment Configuration for Beta

**Step 1**: Update `.env.example`
```bash
# Beta Configuration
BETA_MODE=true
ENVIRONMENT=beta

# Error Tracking
SENTRY_DSN=https://your-sentry-dsn@sentry.io/project-id
SENTRY_ENVIRONMENT=beta

# Analytics (optional)
GOOGLE_ANALYTICS_ID=GA-XXXXXXXX
MIXPANEL_TOKEN=your-mixpanel-token

# Feature Flags
FEATURE_NEW_UI=false
FEATURE_ADVANCED_ANALYTICS=false
FEATURE_EXPORT_CSV=true

# API Keys for Beta
HARVEST_API_KEY=your-beta-api-key

# LLM Configuration
LLM_PROVIDER=openai  # More stable for beta
OPENAI_MODEL=gpt-4o-mini  # Cost-effective for beta
```

**Step 2**: Create beta deployment script
```bash
#!/bin/bash
# scripts/deploy-beta.sh

set -e

echo "🚀 Deploying Signal Harvester Beta..."

# Load environment variables
if [ -f .env.beta ]; then
    source .env.beta
else
    echo "❌ .env.beta not found"
    exit 1
fi

# Build and deploy
docker-compose -f docker-compose.beta.yml build
docker-compose -f docker-compose.beta.yml up -d

# Run database migrations
docker-compose -f docker-compose.beta.yml exec signal-harvester alembic upgrade head

# Create beta admin user (if needed)
# docker-compose -f docker-compose.beta.yml exec signal-harvester harvest beta-invite admin@example.com

echo "✅ Beta deployment complete!"
echo "📊 Monitor at: https://your-beta-domain.com"
echo "🐛 Error tracking: https://sentry.io/your-project"
```

---

## 🎯 Beta Launch Checklist

### Pre-Launch (Day Before)
- [ ] All tests passing (32/32)
- [ ] Error tracking configured and tested
- [ ] Beta user management implemented
- [ ] Feature flags system in place
- [ ] Analytics dashboard deployed
- [ ] Documentation complete
- [ ] Beta environment stable
- [ ] Monitoring alerts configured
- [ ] Support channel ready
- [ ] Beta user list finalized

### Launch Day
- [ ] Deploy to beta environment
- [ ] Send invites to first batch (10 users)
- [ ] Monitor error rates closely
- [ ] Check performance metrics
- [ ] Respond to user questions
- [ ] Collect initial feedback
- [ ] Verify all features working

### Post-Launch (First Week)
- [ ] Daily monitoring of metrics
- [ ] Daily check-ins with users
- [ ] Triage and prioritize feedback
- [ ] Fix critical bugs immediately
- [ ] Prepare weekly beta report
- [ ] Plan next iteration

---

## 📈 Success Metrics

### Technical Metrics
- Error rate < 1%
- API response time < 200ms p95
- System uptime > 99.5%
- Zero critical security issues

### User Metrics
- Onboarding completion > 80%
- Feature adoption > 60%
- User satisfaction > 4/5
- Support tickets < 5 per user

### Beta Program Metrics
- 50-100 beta users
- > 70% weekly active
- > 50% provide feedback
- > 30% interested in paid version

---

## 🚨 Troubleshooting

### Common Issues

**Issue**: Sentry not reporting errors
- Check SENTRY_DSN environment variable
- Verify network connectivity to Sentry
- Check Sentry project settings

**Issue**: Beta users can't activate invites
- Verify invite code is correct
- Check database connection
- Verify user status is 'pending'

**Issue**: Analytics not showing data
- Check database queries
- Verify data exists in database
- Check date ranges

**Issue**: Cypress tests failing
- Verify API is running
- Check test data setup
- Verify API key configuration

---

## 🎉 Next Steps

1. **Implement this guide** step by step
2. **Test each component** thoroughly
3. **Deploy to beta environment**
4. **Invite first batch of users**
5. **Monitor and iterate**

**Estimated Timeline**: 2-3 weeks to full beta readiness

**Resources Needed**:
- 1-2 developers
- Beta tester recruitment
- Sentry account (free tier works)
- Hosting for beta environment
- Analytics service (optional)

**Risk Level**: 🟢 LOW - All components are well-established patterns
**Confidence**: 🟢 HIGH - Proven technologies and approaches