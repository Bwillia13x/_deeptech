# Cross-Source Corroboration - Operations Guide

## Overview

The **Cross-Source Corroboration** system detects and scores relationships between artifacts from different sources (arXiv, GitHub, X/Twitter). This creates a citation graph that:

- **Links research papers to implementations**: Find GitHub repos implementing arXiv papers
- **Connects social discussion to research**: Track X threads discussing breakthrough papers  
- **Builds citation networks**: Discover how artifacts reference each other across platforms
- **Boosts discovery scores**: Artifacts with cross-source corroboration get higher visibility

## Relationship Types

| Type | Description | Example |
|------|-------------|---------|
| `cite` | Paper cites another paper | arXiv paper → arXiv paper |
| `reference` | Social post mentions artifact | Tweet → arXiv paper/GitHub repo |
| `implement` | Code implements research | GitHub repo → arXiv paper |
| `discuss` | Discussion about breakthrough | Tweet → arXiv paper (semantic) |
| `related` | Semantically similar | arXiv ↔ GitHub (semantic) |
| `mention` | Generic link | Any → Any |

## Detection Methods

**1. Citation Detection (Explicit)**

- Extracts arXiv IDs (e.g., `arxiv:2301.12345`, `arxiv.org/abs/2301.12345`)
- Extracts GitHub URLs (e.g., `github.com/owner/repo`)
- Extracts DOIs (e.g., `10.1234/example.2023.01`)
- **Confidence**: 0.90-0.95 for explicit matches

**2. Semantic Detection (Implicit)**

- Uses embedding similarity from Enhanced Embeddings module
- Finds cross-source artifacts discussing same topics
- Configurable similarity threshold (default: 0.80)
- **Confidence**: Semantic similarity score (0.0-1.0)

## Database Schema

Migration 7 adds the `artifact_relationships` table:

```sql
CREATE TABLE artifact_relationships (
    id INTEGER PRIMARY KEY,
    source_artifact_id INTEGER NOT NULL,
    target_artifact_id INTEGER NOT NULL,
    relationship_type TEXT NOT NULL,
    confidence REAL DEFAULT 0.0,
    detection_method TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(source_artifact_id) REFERENCES artifacts(id),
    FOREIGN KEY(target_artifact_id) REFERENCES artifacts(id)
);

-- Indexes for performance
CREATE INDEX idx_relationships_source ON artifact_relationships(source_artifact_id);
CREATE INDEX idx_relationships_target ON artifact_relationships(target_artifact_id);
CREATE INDEX idx_relationships_type ON artifact_relationships(relationship_type);
CREATE INDEX idx_relationships_confidence ON artifact_relationships(confidence);

-- Prevent duplicates
CREATE UNIQUE INDEX ux_relationships_pair 
ON artifact_relationships(source_artifact_id, target_artifact_id, relationship_type);
```

## CLI Commands

### Run Relationship Detection

```bash
# Process all artifacts with default settings
harvest correlate

# Process specific artifact
harvest correlate --artifact-id 123

# Skip semantic detection (faster, citation-only)
harvest correlate --no-semantic

# Higher similarity threshold for semantic relationships
harvest correlate --threshold 0.85

# Run without stats display
harvest correlate --no-stats
```

**Output Example:**

```
Cross-Source Corroboration
Database: var/signal_harvester.db
Processing all artifacts
Semantic similarity: enabled
Similarity threshold: 0.80

Relationship detection complete:
  - Artifacts processed: 42
  - Relationships created: 18

By Type:
  - reference: 8
  - implement: 5
  - related: 3
  - discuss: 2

By Detection Method:
  - arxiv_id_match: 6
  - github_url_match: 5
  - semantic_similarity: 7

Overall Relationship Statistics:
  - Total relationships: 18
  - High confidence (≥0.8): 13
  - Artifacts with relationships: 25
```

## API Endpoints

### Get Artifact Relationships

```bash
# Get all relationships for artifact
curl http://localhost:8000/artifacts/123/relationships

# Get outgoing relationships only
curl "http://localhost:8000/artifacts/123/relationships?direction=outgoing"

# Filter by confidence
curl "http://localhost:8000/artifacts/123/relationships?min_confidence=0.8"
```

**Response:**

```json
{
  "artifact_id": 123,
  "direction": "both",
  "min_confidence": 0.5,
  "count": 3,
  "relationships": [
    {
      "id": 1,
      "source_artifact_id": 123,
      "target_artifact_id": 456,
      "relationship_type": "reference",
      "confidence": 0.95,
      "detection_method": "arxiv_id_match",
      "metadata": {"arxiv_id": "2301.12345"},
      "created_at": "2025-11-11T10:30:00Z",
      "target_title": "Attention Is All You Need",
      "target_source": "arxiv",
      "target_type": "preprint"
    }
  ]
}
```

### Get Citation Graph

```bash
# Get multi-level citation graph
curl "http://localhost:8000/artifacts/123/citation-graph?depth=2"

# Limit to high-confidence relationships
curl "http://localhost:8000/artifacts/123/citation-graph?depth=2&min_confidence=0.8"
```

**Response:**

```json
{
  "root_artifact_id": 123,
  "depth": 2,
  "min_confidence": 0.5,
  "node_count": 8,
  "edge_count": 12,
  "nodes": [
    {
      "id": 123,
      "title": "New Transformer Architecture",
      "source": "arxiv",
      "type": "preprint"
    },
    {
      "id": 456,
      "title": "transformers library",
      "source": "github",
      "type": "repo"
    }
  ],
  "edges": [
    {
      "source": 123,
      "target": 456,
      "relationship_type": "implement",
      "confidence": 0.92,
      "detection_method": "semantic_similarity"
    }
  ]
}
```

### Get Relationship Statistics

```bash
curl http://localhost:8000/relationships/stats
```

**Response:**

```json
{
  "total_relationships": 142,
  "high_confidence_count": 98,
  "artifacts_with_relationships": 75,
  "by_type": [
    {
      "relationship_type": "reference",
      "count": 52,
      "avg_confidence": 0.91
    },
    {
      "relationship_type": "implement",
      "count": 38,
      "avg_confidence": 0.87
    }
  ]
}
```

### Run Detection via API

```bash
# Authenticated endpoint (requires API key)
curl -X POST http://localhost:8000/relationships/detect \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json"

# With custom parameters
curl -X POST "http://localhost:8000/relationships/detect?semantic_threshold=0.85" \
  -H "X-API-Key: your-api-key"
```

## Monitoring & Quality Metrics

### Daily Monitoring

```bash
# Check relationship statistics
harvest correlate --stats

# Or via API
curl http://localhost:8000/relationships/stats | jq
```

**Key Metrics:**

- **Total Relationships**: Should grow as new artifacts are added
- **High Confidence Count**: Target ≥70% of relationships with confidence ≥0.8
- **Artifacts with Relationships**: Target ≥60% of artifacts have at least one relationship
- **Average Confidence by Type**:
  - `cite`, `reference`, `implement`: Should average ≥0.85 (explicit detection)
  - `related`, `discuss`: Should average ≥0.75 (semantic detection)

### Weekly Quality Review

```sql
-- Check relationship distribution by source pairs
SELECT 
    a1.source AS source_source,
    a2.source AS target_source,
    ar.relationship_type,
    COUNT(*) AS count,
    AVG(ar.confidence) AS avg_confidence
FROM artifact_relationships ar
JOIN artifacts a1 ON ar.source_artifact_id = a1.id
JOIN artifacts a2 ON ar.target_artifact_id = a2.id
WHERE ar.created_at >= datetime('now', '-7 days')
GROUP BY a1.source, a2.source, ar.relationship_type
ORDER BY count DESC;

-- Find low-confidence relationships for review
SELECT 
    ar.*,
    a1.title AS source_title,
    a2.title AS target_title
FROM artifact_relationships ar
JOIN artifacts a1 ON ar.source_artifact_id = a1.id
JOIN artifacts a2 ON ar.target_artifact_id = a2.id
WHERE ar.confidence < 0.6
ORDER BY ar.created_at DESC
LIMIT 20;
```

## Integration with Discovery Pipeline

Relationship detection can be integrated into the discovery pipeline:

```python
# In pipeline_discovery.py
from .relationship_detection import run_relationship_detection

async def run_discovery_pipeline(settings: Settings) -> dict[str, Any]:
    """Run complete discovery pipeline with correlation."""
    
    # Fetch artifacts
    fetch_stats = await fetch_artifacts(settings)
    
    # Score discoveries
    scoring_stats = run_discovery_scoring(settings.app.database_path)
    
    # Detect relationships
    correlation_stats = run_relationship_detection(
        db_path=settings.app.database_path,
        enable_semantic=True,
        semantic_threshold=0.80,
    )
    
    return {
        "fetch": fetch_stats,
        "scoring": scoring_stats,
        "correlation": correlation_stats,
    }
```

## Performance Considerations

**Batch Processing:**

- Citation detection is fast (regex-based)
- Semantic detection uses cached embeddings (see Enhanced Embeddings)
- For large datasets (>1000 artifacts), run correlation in batches:

```bash
# Process in chunks
for artifact_id in $(seq 1 100); do
    harvest correlate --artifact-id $artifact_id
done
```

**Optimization Tips:**

1. **Pre-warm embedding cache** before running semantic detection
2. **Run citation detection first** (fast, high-confidence)
3. **Use higher semantic thresholds** (0.85+) for production to reduce noise
4. **Schedule correlation during off-peak hours** if processing large batches

## Troubleshooting

### No Relationships Detected

```bash
# Check if artifacts have content
sqlite3 var/signal_harvester.db "
SELECT COUNT(*), source 
FROM artifacts 
WHERE (title IS NOT NULL AND title != '') 
   OR (text IS NOT NULL AND text != '')
GROUP BY source;
"

# Verify pattern matching works
python -c "
from signal_harvester.relationship_detection import extract_arxiv_ids
print(extract_arxiv_ids('Check out arxiv:2301.12345'))
"
```

### Low Confidence Scores

- **Check embedding quality**: Ensure Enhanced Embeddings Redis cache is working
- **Review artifact text**: Ensure artifacts have meaningful titles and descriptions
- **Adjust thresholds**: Lower `semantic_threshold` temporarily to see all candidates

### Performance Issues

```bash
# Check embedding cache hit rate
curl http://localhost:8000/embeddings/stats | jq '.hit_rate'

# If < 70%, warm up cache first:
harvest embeddings --warm-cache
```

## Example Use Cases

### 1. Finding Implementations of Research Papers

```bash
# Find GitHub repos implementing arXiv paper 2301.12345
sqlite3 var/signal_harvester.db "
SELECT 
    a.title,
    a.url,
    ar.confidence,
    ar.detection_method
FROM artifact_relationships ar
JOIN artifacts a ON ar.source_artifact_id = a.id
WHERE ar.target_artifact_id = (
    SELECT id FROM artifacts 
    WHERE source = 'arxiv' AND source_id = '2301.12345'
)
AND ar.relationship_type = 'implement'
ORDER BY ar.confidence DESC;
"
```

### 2. Tracking Social Discussion of Papers

```bash
# Find tweets discussing a specific paper
curl "http://localhost:8000/artifacts/123/relationships?direction=incoming" \
  | jq '.relationships[] | select(.source_source == "x")'
```

### 3. Building Research Network Graphs

```bash
# Get full citation network for visualization
curl "http://localhost:8000/artifacts/123/citation-graph?depth=3" \
  | jq '.nodes, .edges' > citation_network.json

# Visualize with D3.js, Cytoscape, or Gephi
```

## Quality Thresholds

| Metric | Target | Action if Below |
|--------|--------|-----------------|
| High Confidence % | ≥70% | Review semantic threshold |
| Avg Confidence (explicit) | ≥0.85 | Check pattern extraction |
| Avg Confidence (semantic) | ≥0.75 | Verify embeddings quality |
| Artifacts with Relationships | ≥60% | Add more sources or lower thresholds |
| Relationships per Artifact | 2-10 | Normal range; investigate outliers |

## Migration Guide

If upgrading from a version without cross-source corroboration:

```bash
# 1. Run database migrations
harvest migrate

# 2. Verify migration applied
sqlite3 var/signal_harvester.db "
SELECT name FROM sqlite_master 
WHERE type='table' AND name='artifact_relationships';
"

# 3. Run initial correlation detection
harvest correlate --no-semantic  # Fast, citation-only first pass

# 4. Run full semantic detection
harvest correlate --threshold 0.80

# 5. Verify results
harvest correlate --stats
```

## Best Practices

1. **Run correlation after scoring**: Ensures discovery scores benefit from cross-source signals
2. **Use high thresholds in production**: 0.80+ for semantic similarity reduces false positives
3. **Monitor relationship quality**: Weekly review of low-confidence relationships
4. **Leverage graph depth wisely**: Depth 2-3 is optimal; higher depths may include noise
5. **Integrate with discovery scoring**: Cross-source boost already built into scoring algorithm

## Architecture

### Module Structure

```
src/signal_harvester/
├── relationship_detection.py   # Core detection logic (540 lines)
│   ├── extract_arxiv_ids()     # Pattern extraction
│   ├── extract_dois()
│   ├── extract_github_repos()
│   ├── compute_semantic_similarity()
│   ├── detect_citation_relationships()
│   ├── detect_semantic_relationships()
│   ├── run_relationship_detection()
│   └── get_citation_graph()
│
├── db.py                       # Database operations
│   ├── create_artifact_relationship()
│   ├── get_artifact_relationships()
│   └── get_relationship_stats()
│
├── embeddings.py               # Embedding service (used for semantic detection)
│   └── get_artifact_embedding()
│
├── cli/discovery_commands.py   # CLI interface
│   └── correlate_artifacts()
│
└── api.py                      # REST API endpoints
    ├── GET /artifacts/{id}/relationships
    ├── GET /artifacts/{id}/citation-graph
    ├── GET /relationships/stats
    └── POST /relationships/detect
```

### Data Flow

```
1. Artifact ingestion (arXiv, GitHub, X)
   ↓
2. Text extraction and preprocessing
   ↓
3. Citation detection (regex patterns)
   ├── arXiv IDs → link to arXiv artifacts
   ├── GitHub URLs → link to GitHub artifacts
   └── DOIs → link to academic papers
   ↓
4. Semantic detection (embeddings)
   ├── Compute embeddings (cached in Redis)
   ├── Cross-source similarity computation
   └── Filter by threshold (default 0.80)
   ↓
5. Relationship storage
   ├── Deduplicate via unique index
   └── Update confidence if higher
   ↓
6. Graph construction
   ├── Multi-level traversal
   └── Confidence filtering
```

## Test Coverage

**Test Suite**: `tests/test_relationship_detection.py`

- **Total Tests**: 26
- **Pass Rate**: 100% (26/26 passing)

**Coverage Areas**:

- Pattern extraction (arXiv IDs, DOIs, GitHub URLs)
- Citation relationship detection
- Semantic similarity computation
- Database operations (create, retrieve, stats)
- Graph construction and traversal
- Edge cases (empty text, duplicates, confidence updates)

Run tests:

```bash
pytest tests/test_relationship_detection.py -v
```
