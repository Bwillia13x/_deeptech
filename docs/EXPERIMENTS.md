# Experiments & Backtesting Guide

## Overview

The Signal Harvester experiments system enables A/B testing of discovery scoring algorithms, validation of improvements, and systematic measurement of precision/recall metrics.

## Core Concepts

### Experiments

An **experiment** is a configuration for testing a specific scoring approach:

- **Scoring weights**: Custom weights for novelty, impact, quality, etc.
- **Baseline comparison**: Optional reference to compare against
- **Configuration**: Source filters, thresholds, lookback windows

### Experiment Runs

An **experiment run** captures the results of executing an experiment:

- **Confusion matrix**: TP, FP, TN, FN counts
- **Metrics**: Precision, recall, F1 score, accuracy
- **Metadata**: Artifact counts, timestamps, execution details

### Ground Truth Labels

**Labels** annotate artifacts as true/false positives for validation:

- **Label types**: `true_positive`, `false_positive`, `relevant`, `irrelevant`
- **Confidence**: 0.0-1.0 score for label certainty
- **Annotator tracking**: Who applied the label and when

## Metrics Definitions

### Precision

```
Precision = TP / (TP + FP)
```

Measures accuracy of positive predictions. High precision = few false alarms.

### Recall

```
Recall = TP / (TP + FN)
```

Measures coverage of actual positives. High recall = few missed discoveries.

### F1 Score

```
F1 = 2 * (Precision * Recall) / (Precision + Recall)
```

Harmonic mean balancing precision and recall.

### Accuracy

```
Accuracy = (TP + TN) / Total
```

Overall correctness across all predictions.

## CLI Usage

### Run Backtest with Metrics

```bash
# Basic backtest - count discoveries over time
harvest backtest --days 7 --min-score 80.0

# Backtest with precision/recall metrics
harvest backtest --days 7 --min-score 75.0 --metrics

# Create experiment from backtest
harvest backtest --days 7 --experiment "baseline_v1" --metrics

# Compare with baseline
harvest backtest --days 7 --experiment "improved_v2" --compare 1 --metrics
```

### Annotate Artifacts

```bash
# Label single artifact
harvest annotate 123 true_positive --confidence 0.95 --notes "Clear breakthrough"

# Label with annotator tracking
harvest annotate 456 false_positive --annotator "john@example.com"

# Import labels from CSV
harvest annotate --import labels.csv

# Export labels to CSV
harvest annotate --export labeled_artifacts.csv
```

CSV format:

```csv
artifactId,label,confidence,annotator,notes
123,true_positive,0.95,john@example.com,Significant advance
456,false_positive,0.8,jane@example.com,Incremental only
```

## API Endpoints

### Create Experiment

```http
POST /experiments?name=baseline_v1&min_score_threshold=75.0&lookback_days=7
Content-Type: application/json

{
  "scoring_weights": {
    "novelty": 0.4,
    "impact": 0.3,
    "quality": 0.3
  }
}
```

### List Experiments

```http
GET /experiments
GET /experiments?status=completed
```

### Get Experiment Details

```http
GET /experiments/1
```

### Get Experiment Runs

```http
GET /experiments/1/runs
```

### Compare Experiments

```http
GET /experiments/compare?experiment_a=1&experiment_b=2
```

Response:

```json
{
  "experimentA": {
    "precision": 0.75,
    "recall": 0.68,
    "f1Score": 0.71
  },
  "experimentB": {
    "precision": 0.82,
    "recall": 0.74,
    "f1Score": 0.78
  },
  "deltas": {
    "precision": +0.07,
    "recall": +0.06,
    "f1Score": +0.07
  },
  "winner": "experimentB"
}
```

### Add Label

```http
POST /labels?artifact_id=123&label=true_positive&confidence=0.9
X-API-Key: your_api_key
```

### Get Labels

```http
GET /labels
GET /labels?label=true_positive
```

## Workflow Example

### 1. Annotate Training Set

```bash
# Review top discoveries and label them
harvest discoveries --limit 100 | jq -r '.[] | .id'

# Label significant ones
harvest annotate 101 true_positive --confidence 0.95
harvest annotate 102 true_positive --confidence 0.85
harvest annotate 103 false_positive --confidence 0.9
# ... continue labeling
```

### 2. Create Baseline Experiment

```bash
# Run backtest with current configuration
harvest backtest --days 14 --experiment "baseline_current" --metrics
```

Output:

```
Backtest summary (last 14 days):
  • Day 1: 15 discoveries, avg score 85.32 | TP=8 FP=2 FN=3
  • Day 2: 18 discoveries, avg score 83.45 | TP=10 FP=3 FN=2
  ...

Overall Metrics:
  Precision: 0.781
  Recall:    0.724
  F1 Score:  0.751
  Accuracy:  0.812

✓ Created experiment 'baseline_current' (ID: 1, Run: 1)
```

### 3. Test Alternative Configuration

```bash
# Modify weights in config/settings.yaml
# discovery_scoring:
#   novelty_weight: 0.5  # increased from 0.4
#   impact_weight: 0.3   # decreased from 0.4

# Run new experiment
harvest backtest --days 14 --experiment "high_novelty_v1" --compare 1 --metrics
```

Output:

```
...
Comparison with baseline experiment 1:
  F1 Score delta: +0.042
  Precision delta: +0.028
  Recall delta: +0.051
  Winner: experimentB
```

### 4. Iterate and Validate

```bash
# Export all experiments for analysis
curl http://localhost:8000/experiments | jq '.'

# Review best performers
curl "http://localhost:8000/experiments/compare?experiment_a=1&experiment_b=3"
```

## Best Practices

### Labeling Strategy

1. **Diverse sampling**: Label artifacts across score ranges, sources, topics
2. **Inter-annotator agreement**: Have multiple people label same artifacts
3. **Confidence scores**: Use lower confidence for borderline cases
4. **Regular updates**: Re-label as understanding evolves

### Experiment Design

1. **Single variable changes**: Change one weight/parameter at a time
2. **Sufficient data**: Aim for 100+ labeled artifacts minimum
3. **Time windows**: Test across multiple time periods
4. **Baseline tracking**: Always compare against established baseline

### Interpreting Results

- **F1 > 0.75**: Good performance for discovery tasks
- **Precision/Recall tradeoff**: High precision = conservative, high recall = comprehensive
- **Statistical significance**: Need sufficient sample size (>50 artifacts)
- **Temporal stability**: Verify performance across different time windows

## Troubleshooting

### No metrics shown in backtest

**Issue**: `harvest backtest --metrics` shows no precision/recall

**Solution**: Add ground truth labels first with `harvest annotate`

### Low precision

**Issue**: Many false positives in results

**Solutions**:

- Increase `min_score_threshold`
- Increase quality/credibility weights
- Review and relabel borderline cases

### Low recall

**Issue**: Missing important discoveries

**Solutions**:

- Decrease `min_score_threshold`
- Increase novelty/emergence weights
- Check source coverage

### Inconsistent metrics across runs

**Issue**: Metrics vary significantly between runs

**Solutions**:

- Increase labeled dataset size
- Check for data leakage (train/test overlap)
- Verify label quality and consistency

## Database Schema

### experiments

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| name | TEXT | Unique experiment name |
| description | TEXT | Optional description |
| config_json | TEXT | JSON scoring configuration |
| baseline_id | INTEGER | Reference to baseline experiment |
| created_at | TEXT | ISO 8601 timestamp |
| updated_at | TEXT | ISO 8601 timestamp |
| status | TEXT | draft, running, completed |

### experiment_runs

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| experiment_id | INTEGER | Foreign key to experiments |
| artifact_count | INTEGER | Total artifacts evaluated |
| true_positives | INTEGER | TP count |
| false_positives | INTEGER | FP count |
| true_negatives | INTEGER | TN count |
| false_negatives | INTEGER | FN count |
| precision | REAL | Calculated precision |
| recall | REAL | Calculated recall |
| f1_score | REAL | Calculated F1 score |
| accuracy | REAL | Calculated accuracy |
| started_at | TEXT | Run start timestamp |
| completed_at | TEXT | Run completion timestamp |
| status | TEXT | running, completed, failed |
| metadata_json | TEXT | Additional run metadata |

### discovery_labels

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| artifact_id | INTEGER | Foreign key to artifacts |
| label | TEXT | Label value (true_positive, etc.) |
| confidence | REAL | Label confidence (0.0-1.0) |
| annotator | TEXT | Who applied label |
| notes | TEXT | Optional notes |
| created_at | TEXT | Created timestamp |
| updated_at | TEXT | Updated timestamp |

## Further Reading

- [Discovery Scoring](OPERATIONS.md#discovery-scoring): How artifacts are scored
- [API Reference](API.md): Complete API documentation
- [Architecture](ARCHITECTURE_AND_READINESS.md): System design overview
