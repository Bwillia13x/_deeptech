# Signal Harvester - User Guide

> This guide is part of the maintained documentation set for Signal Harvester.
> For the canonical architecture, readiness posture, and prioritized roadmap, refer to [`signal-harvester/ARCHITECTURE_AND_READINESS.md`](signal-harvester/ARCHITECTURE_AND_READINESS.md:1).
> To validate an installation end-to-end, from the `signal-harvester` directory run `make verify-all` (see [`signal-harvester/Makefile`](signal-harvester/Makefile:7)).

## 📚 Table of Contents

1. [Introduction](#introduction)
2. [Getting Started](#getting-started)
3. [Understanding Signals](#understanding-signals)
4. [Dashboard](#dashboard)
5. [Managing Signals](#managing-signals)
6. [Working with Snapshots](#working-with-snapshots)
7. [Settings & Configuration](#settings--configuration)
8. [Best Practices](#best-practices)
9. [Troubleshooting](#troubleshooting)
10. [FAQ](#faq)

---

## Introduction

Signal Harvester is a social media intelligence platform that monitors X (Twitter) for customer signals, analyzes them using AI, and surfaces the most important items for your attention.

### What is a "Signal"?

A signal is a social media post that indicates:
- **Bug reports** - Users reporting issues or crashes
- **Churn risk** - Users expressing frustration or looking for alternatives
- **Feature requests** - Users asking for new functionality
- **Support issues** - Users needing help with your product

### How It Works

1. **Fetch**: Collects posts from X/Twitter based on your search queries
2. **Analyze**: Uses AI (OpenAI, Anthropic, or heuristic) to classify content
3. **Score**: Calculates salience score based on urgency, sentiment, and impact
4. **Notify**: Sends alerts for high-priority items via Slack
5. **Surface**: Displays results in a clean, actionable interface

---

## Getting Started

### Quick Start (5 minutes)

1. **Sign In**: Use your beta invite code to create an account
2. **Configure API**: Add your X/Twitter API bearer token in Settings
3. **Add Queries**: Define what you want to monitor in the configuration
4. **Run Pipeline**: Click "Run Pipeline" to start harvesting
5. **View Results**: Check your Dashboard and Signals pages

### First-Time Setup

When you first log in, you'll see an onboarding tour that guides you through:
- Dashboard overview
- Signals management
- Snapshots and backups
- Settings configuration

**Tip**: You can always retake the tour from Settings → Onboarding.

### Navigation

- **Dashboard**: Overview of your signals and metrics
- **Signals**: View and manage all harvested signals
- **Snapshots**: Create and manage data backups
- **Settings**: Configure API keys and preferences

---

## Understanding Signals

### Signal Statuses

Signals can have different statuses:

- **Active**: Currently being monitored
- **Paused**: Temporarily not monitoring
- **Error**: Problem with the signal (check configuration)
- **Inactive**: Manually disabled

### Salience Score

Each signal is scored from 0-100 based on:
- **Question indicators** (25%): Asking for help, reporting issues
- **Negative sentiment** (30%): Frustration, complaints, anger
- **Urgency** (25%): Time-sensitive language, "ASAP", "broken"
- **Impact** (20%): Multiple users affected, widespread issue

**Score Ranges**:
- **80-100**: Critical - Immediate attention needed
- **60-79**: High - Review within 24 hours
- **40-59**: Medium - Review within a week
- **0-39**: Low - Monitor or archive

### Signal Categories

The AI automatically categorizes signals as:
- **Bug Report**: Technical issues, crashes, errors
- **Churn Risk**: Cancellation threats, competitor mentions
- **Feature Request**: "I wish", "should have", "need"
- **Support Issue**: How-to questions, confusion
- **General Feedback**: Comments, suggestions, praise

---

## Dashboard

### Overview

The Dashboard gives you a quick view of your signal landscape:

**Metrics Cards**:
- **Total Signals**: All signals being monitored
- **Active**: Currently active and monitoring
- **Paused**: Temporarily stopped
- **Errors**: Signals with configuration issues

**Recent Activity**:
- Shows latest harvested signals
- Displays trending topics
- Highlights high-salience items

### Using the Dashboard

1. **Check Metrics Daily**: Review the counts to spot anomalies
2. **Monitor Recent Activity**: See what's new at a glance
3. **Identify Trends**: Look for patterns in the data
4. **Take Action**: Click through to Signals for details

**Best Practice**: Start your day with the Dashboard to prioritize your response efforts.

---

## Managing Signals

### Viewing Signals

The Signals page shows all your harvested signals with:
- Search and filtering capabilities
- Sort by date, salience score, or status
- Bulk actions for multiple signals
- Detailed view for each signal

### Creating a Signal

1. Click "Create Signal" in the top-right
2. Enter the tweet URL or ID
3. Select a category (or let AI auto-detect)
4. Add notes if needed
5. Save

### Editing Signals

1. Click on a signal row to open details
2. Modify category, status, or notes
3. Save changes

**Tip**: Use consistent categories for better reporting.

### Bulk Actions

Select multiple signals to:
- **Pause/Resume**: Temporarily stop/start monitoring
- **Delete**: Remove signals (use with caution)
- **Export**: Download as CSV for analysis
- **Change Category**: Reclassify multiple signals

### Searching and Filtering

**Search**: Find signals by text content, username, or tweet ID

**Filter by**:
- Status (active, paused, error, inactive)
- Category (bug, churn, feature, support)
- Date range
- Salience score range
- Source (which query found it)

**Example**: Find all high-priority bug reports from the last 7 days.

---

## Working with Snapshots

### What are Snapshots?

Snapshots are point-in-time backups of your signals data. They're useful for:
- Historical analysis and trends
- Recovery from data issues
- Reporting and compliance
- Before/after comparisons

### Creating a Snapshot

1. Navigate to Snapshots page
2. Click "Create Snapshot"
3. Enter a name/description
4. Click "Create"

**Best Practice**: Create snapshots:
- Before making configuration changes
- Weekly for historical records
- Before bulk operations
- After major events (product launches, campaigns)

### Restoring from Snapshot

1. Find the snapshot in the list
2. Click "Restore"
3. Confirm the restore operation
4. Wait for restoration to complete

**Warning**: Restoring replaces current data with snapshot data. Create a new snapshot first if you want to preserve current state.

### Snapshot Retention

The system automatically manages snapshots based on:
- **Age**: Delete snapshots older than X days
- **Count**: Keep only the N most recent
- **Size**: Limit total storage used

Configure retention policies in your configuration file.

---

## Settings & Configuration

### API Configuration

**X/Twitter API**:
- Bearer token (required)
- Rate limit handling
- Query configuration

**LLM Providers** (choose one):
- **OpenAI**: GPT-4, GPT-4o-mini
- **Anthropic**: Claude 3.5 Haiku
- **xAI**: Grok
- **Heuristic**: Rule-based (no API key needed)

**Slack Notifications** (optional):
- Webhook URL
- Notification thresholds
- Channel configuration

### Search Queries

Define what to monitor using X/Twitter search syntax:

**Basic Example**:
```yaml
queries:
  - name: "brand_mentions"
    query: "(@YourBrand OR #YourBrand) -is:retweet -is:reply"
    enabled: true
```

**Advanced Example**:
```yaml
queries:
  - name: "bug_reports"
    query: "(@YourBrand) (bug OR crash OR broken OR error) -is:retweet lang:en"
    enabled: true
  
  - name: "churn_risk"
    query: "(@YourBrand) (cancel OR unsubscribe OR switch OR alternative) -is:retweet"
    enabled: true
```

**Query Tips**:
- Use `-is:retweet` to exclude retweets
- Use `-is:reply` to exclude replies
- Add `lang:en` for language filtering
- Use OR for multiple terms
- Use quotes for exact phrases

### Scoring Configuration

Adjust salience score weights in `config/settings.yaml`:

```yaml
scoring:
  weights:
    question: 0.25      # "how do I", "why doesn't this work"
    negative_sentiment: 0.30  # Frustration, complaints
    urgency: 0.25       # "ASAP", "urgent", "broken"
    impact: 0.20        # Multiple users, widespread
```

**Adjust weights based on your priorities**:
- Higher `negative_sentiment` for customer satisfaction focus
- Higher `urgency` for technical issue detection
- Higher `impact` for identifying widespread problems

### Notification Settings

Configure when to send Slack alerts:

```yaml
notifications:
  slack:
    enabled: true
    webhook_url: "YOUR_WEBHOOK_URL"
    threshold: 60.0  # Minimum salience score to notify
    max_items: 10    # Maximum notifications per batch
    hours: 24        # Only consider recent signals
```

---

## Best Practices

### Signal Management

1. **Review Daily**: Check high-salience signals every morning
2. **Categorize Consistently**: Use standard categories for reporting
3. **Act Quickly**: Respond to 80+ scores within 4 hours
4. **Track Resolutions**: Mark signals as resolved when addressed
5. **Learn Patterns**: Identify recurring issues for prevention

### Query Optimization

1. **Start Simple**: Begin with brand mentions, then add complexity
2. **Test Queries**: Use X's search directly to verify results
3. **Monitor Volume**: Adjust queries if too many/few results
4. **Use Exclusions**: Filter out noise with `-term`
5. **Review Regularly**: Update queries as products/features change

### Performance

1. **Rate Limits**: Respect X API rate limits (450 requests/15 min)
2. **Batch Operations**: Use bulk actions instead of individual edits
3. **Snapshot Strategy**: Create snapshots before major changes
4. **Data Retention**: Set appropriate retention for your needs
5. **API Keys**: Rotate keys regularly for security

### Team Collaboration

1. **Shared Dashboard**: Review signals in team meetings
2. **Assignment**: Assign signals to team members for follow-up
3. **Documentation**: Document resolutions for knowledge base
4. **Feedback Loop**: Share insights with product/engineering teams
5. **Reporting**: Generate weekly/monthly reports for stakeholders

---

## Troubleshooting

### Common Issues

**Problem**: No signals appearing
- **Check**: API key is valid and has proper permissions
- **Check**: Queries are enabled in configuration
- **Check**: Rate limits haven't been exceeded
- **Solution**: Run pipeline manually and check logs

**Problem**: All signals have low salience scores
- **Check**: Scoring weights are configured
- **Check**: LLM API key is working (if using AI analysis)
- **Solution**: Adjust weights or switch to heuristic scoring

**Problem**: Too many signals (overwhelming)
- **Solution**: Refine queries to be more specific
- **Solution**: Increase minimum salience threshold
- **Solution**: Add more exclusion terms

**Problem**: Missing important signals
- **Solution**: Lower salience threshold
- **Solution**: Simplify queries to catch more
- **Solution**: Check if being rate-limited

**Problem**: Slack notifications not working
- **Check**: Webhook URL is correct
- **Check**: Threshold is not too high
- **Check**: Slack channel exists and bot has access
- **Solution**: Test webhook with curl

**Problem**: Database errors
- **Check**: Disk space available
- **Check**: File permissions on database
- **Solution**: Create snapshot and restart
- **Solution**: Restore from last good snapshot

### Getting Help

**Beta Support**:
- Email: beta-support@signal-harvester.com
- Slack: #signal-harvester-beta
- Response time: Within 24 hours

**When Reporting Issues**:
1. Describe what you were trying to do
2. Include error messages (screenshots helpful)
3. Note steps to reproduce
4. Include your configuration (remove API keys)
5. Share relevant logs

---

## FAQ

### General

**Q: How often does Signal Harvester check for new signals?**
A: By default, every 5 minutes (300 seconds). Configure with `harvest daemon --interval <seconds>`.

**Q: Can I monitor multiple brands/companies?**
A: Yes! Create separate queries for each brand in your configuration.

**Q: What happens if I hit X API rate limits?**
A: The system automatically backs off and retries. You'll see warnings in logs but no data loss.

**Q: How secure is my data?**
A: All data stays in your database. API keys are encrypted at rest. We never share your data.

### Signals

**Q: Can I manually add a signal?**
A: Yes! Use the "Create Signal" button and enter the tweet URL or ID.

**Q: What's the difference between active and paused signals?**
A: Active signals are continuously monitored. Paused signals keep historical data but stop checking for updates.

**Q: Can I export my signals?**
A: Yes! Use the export feature on the Signals page or CLI command `harvest export`.

**Q: How do I delete old signals?**
A: Use bulk delete on the Signals page, or set up automatic retention policies.

### AI Analysis

**Q: Do I need an OpenAI/Anthropic API key?**
A: No, you can use the heuristic analyzer which doesn't require any API key. However, AI provides better accuracy.

**Q: How much does AI analysis cost?**
A: Costs vary by provider. GPT-4o-mini is ~$0.15 per 1M tokens. Claude Haiku is ~$0.25 per 1M tokens.

**Q: Can I switch AI providers?**
A: Yes! Change the provider in your configuration and restart. The system will use the new provider for new signals.

### Snapshots

**Q: How many snapshots should I keep?**
A: For most users, 10-20 snapshots provide good coverage. The system can auto-manage this.

**Q: Can I automate snapshot creation?**
A: Yes! Use the scheduler service or set up a cron job with `harvest snapshot`.

**Q: What's the difference between snapshot and export?**
A: Snapshots are full database backups for restoration. Exports are CSV files for analysis.

### Beta Program

**Q: How long is the beta period?**
A: Approximately 4-6 weeks, ending in December 2024.

**Q: Will there be a free tier after beta?**
A: Yes! We're planning a generous free tier for small teams and individuals.

**Q: Can I invite my team members?**
A: During beta, email us at beta-support@signal-harvester.com with their email addresses.

**Q: What happens to my data after beta?**
A: All your data, configuration, and snapshots will be preserved when we transition to production.

---

## Next Steps

1. **Complete Onboarding**: Take the guided tour if you haven't already
2. **Configure APIs**: Add your X/Twitter API key in Settings
3. **Set Up Queries**: Define what you want to monitor
4. **Run First Pipeline**: Harvest your initial signals
5. **Explore**: Navigate through Dashboard, Signals, and Snapshots
6. **Join Community**: Connect with other beta users in Slack

---

**Need help?** Reach out to beta-support@signal-harvester.com or join #signal-harvester-beta on Slack.

**Happy signal harvesting! 🚀**