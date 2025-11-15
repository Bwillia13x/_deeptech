import {
  ArtifactRelationship,
  GetRelationshipsResponse,
  CitationGraphResponse,
  RelationshipStats,
  RelationshipDetectionStats,
  GetRelationshipsParams,
  RelationshipDetectionParams,
} from "../types/api";

// Mock artifact data
const mockArtifacts = [
  {
    id: 1,
    title: "Attention Is All You Need",
    source: "arxiv",
    type: "paper",
    discoveryScore: 92.5,
  },
  {
    id: 2,
    title: "PyTorch Implementation of Transformer",
    source: "github",
    type: "repo",
    discoveryScore: 78.3,
  },
  {
    id: 3,
    title: "Excited about the new transformer architecture!",
    source: "x",
    type: "tweet",
    discoveryScore: 45.7,
  },
  {
    id: 4,
    title: "BERT: Pre-training of Deep Bidirectional Transformers",
    source: "arxiv",
    type: "paper",
    discoveryScore: 88.9,
  },
  {
    id: 5,
    title: "TensorFlow Transformers Library",
    source: "github",
    type: "repo",
    discoveryScore: 82.1,
  },
  {
    id: 6,
    title: "Breaking down the latest NLP breakthrough",
    source: "x",
    type: "tweet",
    discoveryScore: 52.3,
  },
];

const relationshipTypes = ["cite", "reference", "discuss", "implement", "mention", "related"] as const;
const detectionMethods = ["arxiv_id_match", "github_url_match", "semantic_similarity", "doi_pattern"] as const;

export function mockGetRelationships(
  artifactId: number,
  params: GetRelationshipsParams
): GetRelationshipsResponse {
  const { page = 1, pageSize = 20, direction = "both", minConfidence = 0.5 } = params;

  // Generate mock relationships for the artifact
  const relationships: ArtifactRelationship[] = [];
  const numRelationships = Math.floor(Math.random() * 15) + 5; // 5-20 relationships

  for (let i = 0; i < numRelationships; i++) {
    const targetArtifact = mockArtifacts[Math.floor(Math.random() * mockArtifacts.length)];
    if (targetArtifact.id === artifactId) continue; // Skip self-references

    const relationshipType = relationshipTypes[Math.floor(Math.random() * relationshipTypes.length)];
    const confidence = Math.random() * 0.5 + 0.5; // 0.5 to 1.0
    const detectionMethod = detectionMethods[Math.floor(Math.random() * detectionMethods.length)];

    relationships.push({
      id: `rel-${artifactId}-${targetArtifact.id}-${i}`,
      sourceArtifactId: direction === "incoming" ? targetArtifact.id : artifactId,
      targetArtifactId: direction === "incoming" ? artifactId : targetArtifact.id,
      sourceTitle: direction === "incoming" ? targetArtifact.title : mockArtifacts.find(a => a.id === artifactId)?.title || "",
      sourceType: direction === "incoming" ? targetArtifact.type : mockArtifacts.find(a => a.id === artifactId)?.type || "",
      sourceSource: direction === "incoming" ? targetArtifact.source : mockArtifacts.find(a => a.id === artifactId)?.source || "",
      targetTitle: targetArtifact.title,
      targetType: targetArtifact.type,
      targetSource: targetArtifact.source,
      relationshipType,
      confidence,
      detectionMethod,
      createdAt: new Date(Date.now() - Math.random() * 7 * 24 * 60 * 60 * 1000).toISOString(),
      metadata: {
        similarityScore: relationshipType === "related" ? confidence : undefined,
        arxivId: detectionMethod === "arxiv_id_match" ? "2301.12345" : undefined,
        githubRepo: detectionMethod === "github_url_match" ? "openai/transformer" : undefined,
      },
    });
  }

  // Filter by minimum confidence
  const filteredRelationships = relationships.filter(r => r.confidence >= minConfidence);

  // Sort by confidence (highest first)
  filteredRelationships.sort((a, b) => b.confidence - a.confidence);

  // Apply pagination
  const total = filteredRelationships.length;
  const startIndex = (page - 1) * pageSize;
  const endIndex = startIndex + pageSize;
  const paginatedRelationships = filteredRelationships.slice(startIndex, endIndex);

  return {
    artifactId,
    count: paginatedRelationships.length,
    relationships: paginatedRelationships,
    pagination: {
      page,
      pageSize,
      totalPages: Math.ceil(total / pageSize),
    },
  };
}

export function mockGetCitationGraph(
  artifactId: number,
  depth = 2,
  minConfidence = 0.5
): CitationGraphResponse {
  const nodes: CitationGraphResponse["nodes"] = [];
  const edges: CitationGraphResponse["edges"] = [];
  const addedNodes = new Set<number>();

  // Start with the root artifact
  const rootArtifact = mockArtifacts.find(a => a.id === artifactId) || mockArtifacts[0];
  nodes.push({
    id: rootArtifact.id,
    title: rootArtifact.title,
    source: rootArtifact.source,
    type: rootArtifact.type,
    discoveryScore: rootArtifact.discoveryScore,
  });
  addedNodes.add(rootArtifact.id);

  // Generate nodes and edges based on depth
  const queue: Array<{ artifactId: number; currentDepth: number }> = [{ artifactId: rootArtifact.id, currentDepth: 0 }];

  while (queue.length > 0 && queue[0].currentDepth < depth) {
    const { artifactId: currentId, currentDepth } = queue.shift()!;

    // Add 2-4 connected nodes for each node
    const numConnections = Math.floor(Math.random() * 3) + 2;
    
    for (let i = 0; i < numConnections; i++) {
      const targetArtifact = mockArtifacts[Math.floor(Math.random() * mockArtifacts.length)];
      
      if (!addedNodes.has(targetArtifact.id)) {
        nodes.push({
          id: targetArtifact.id,
          title: targetArtifact.title,
          source: targetArtifact.source,
          type: targetArtifact.type,
          discoveryScore: targetArtifact.discoveryScore,
        });
        addedNodes.add(targetArtifact.id);
      }

      const confidence = Math.random() * 0.5 + minConfidence;
      const relationshipType = relationshipTypes[Math.floor(Math.random() * relationshipTypes.length)];
      const detectionMethod = detectionMethods[Math.floor(Math.random() * detectionMethods.length)];

      edges.push({
        source: currentId,
        target: targetArtifact.id,
        relationshipType,
        confidence,
        detectionMethod,
      });

      // Add to queue for next depth level
      if (currentDepth + 1 < depth) {
        queue.push({ artifactId: targetArtifact.id, currentDepth: currentDepth + 1 });
      }
    }
  }

  return {
    rootArtifactId: artifactId,
    depth,
    minConfidence,
    nodes,
    edges,
    nodeCount: nodes.length,
    edgeCount: edges.length,
  };
}

export function mockGetRelationshipStats(): RelationshipStats {
  return {
    totalRelationships: 1257,
    byType: {
      cite: 342,
      reference: 456,
      discuss: 189,
      implement: 143,
      mention: 89,
      related: 38,
    },
    byMethod: {
      arxiv_id_match: 456,
      github_url_match: 234,
      semantic_similarity: 387,
      doi_pattern: 180,
    },
    averageConfidence: 0.87,
    artifactsWithRelationships: 789,
    lastUpdated: new Date().toISOString(),
  };
}

export function mockRunRelationshipDetection(
  params: RelationshipDetectionParams
): RelationshipDetectionStats {
  // Simulate processing time
  const processed = params.artifactId ? 1 : 150;
  const relationshipsCreated = params.artifactId ? Math.floor(Math.random() * 8) + 2 : 87;

  return {
    processed,
    relationshipsCreated,
    byType: {
      cite: Math.floor(relationshipsCreated * 0.25),
      reference: Math.floor(relationshipsCreated * 0.35),
      discuss: Math.floor(relationshipsCreated * 0.15),
      implement: Math.floor(relationshipsCreated * 0.15),
      mention: Math.floor(relationshipsCreated * 0.05),
      related: Math.floor(relationshipsCreated * 0.05),
    },
    byMethod: {
      arxiv_id_match: Math.floor(relationshipsCreated * 0.36),
      github_url_match: Math.floor(relationshipsCreated * 0.22),
      semantic_similarity: Math.floor(relationshipsCreated * 0.31),
      doi_pattern: Math.floor(relationshipsCreated * 0.11),
    },
  };
}
