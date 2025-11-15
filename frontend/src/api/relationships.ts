import { http } from "../lib/http";
import { isMockMode } from "../lib/env";
import {
  ArtifactRelationship,
  GetRelationshipsParams,
  GetRelationshipsResponse,
  CitationGraphResponse,
  RelationshipStats,
  RelationshipDetectionStats,
  RelationshipDetectionParams,
} from "../types/api";
import {
  mockGetRelationships,
  mockGetCitationGraph,
  mockGetRelationshipStats,
  mockRunRelationshipDetection,
} from "../mocks/relationships";

// API routes
const routes = {
  relationships: (artifactId: number) => `/artifacts/${artifactId}/relationships`,
  citationGraph: (artifactId: number) => `/artifacts/${artifactId}/citation-graph`,
  relationshipStats: "/relationships/stats",
  runDetection: "/relationships/detect",
};

/**
 * Get relationships for an artifact with optional filtering
 */
export async function getArtifactRelationships(
  artifactId: number,
  params: GetRelationshipsParams = {}
): Promise<GetRelationshipsResponse> {
  if (isMockMode) {
    await new Promise((r) => setTimeout(r, 300));
    return mockGetRelationships(artifactId, params);
  }

  const query: Record<string, any> = {};
  if (params.direction) query.direction = params.direction;
  if (params.relationshipType) query.relationship_type = params.relationshipType;
  if (params.minConfidence) query.min_confidence = params.minConfidence;
  if (params.page) query.page = params.page;
  if (params.pageSize) query.page_size = params.pageSize;

  return http.get<GetRelationshipsResponse>(routes.relationships(artifactId), { query });
}

/**
 * Get citation graph for an artifact
 */
export async function getCitationGraph(
  artifactId: number,
  depth = 2,
  minConfidence = 0.5
): Promise<CitationGraphResponse> {
  if (isMockMode) {
    await new Promise((r) => setTimeout(r, 500));
    return mockGetCitationGraph(artifactId, depth, minConfidence);
  }

  return http.get<CitationGraphResponse>(routes.citationGraph(artifactId), {
    query: { depth, min_confidence: minConfidence },
  });
}

/**
 * Get relationship statistics
 */
export async function getRelationshipStats(): Promise<RelationshipStats> {
  if (isMockMode) {
    await new Promise((r) => setTimeout(r, 200));
    return mockGetRelationshipStats();
  }

  return http.get<RelationshipStats>(routes.relationshipStats);
}

/**
 * Run relationship detection
 */
export async function runRelationshipDetection(
  params: RelationshipDetectionParams = {}
): Promise<RelationshipDetectionStats> {
  if (isMockMode) {
    await new Promise((r) => setTimeout(r, 1000));
    return mockRunRelationshipDetection(params);
  }

  const query: Record<string, any> = {};
  if (params.artifactId !== undefined) query.artifact_id = params.artifactId;
  if (params.enableSemantic !== undefined) query.enable_semantic = params.enableSemantic;
  if (params.semanticThreshold !== undefined) query.semantic_threshold = params.semanticThreshold;

  return http.post<RelationshipDetectionStats>(routes.runDetection, { query });
}
