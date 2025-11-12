import { http } from "../lib/http";
import { isMockMode } from "../lib/env";
import {
  Discovery,
  DiscoveriesListParams,
  TrendingTopic,
  TrendingTopicsParams,
  Entity,
  RefreshParams,
  Paginated,
  TopicTimelinePoint
} from "../types/api";
import { mockListDiscoveries, mockGetTrendingTopics, mockGetEntity, mockGetTopicTimeline } from "../mocks/discoveries";

// API routes
const routes = {
  discoveries: "/discoveries",
  trendingTopics: "/topics/trending",
  entity: (id: string) => `/entities/${encodeURIComponent(id)}`,
  topicTimeline: (topic: string) => `/topics/${encodeURIComponent(topic)}/timeline`,
  refresh: "/refresh",
};

/**
 * List discoveries with optional filtering and sorting
 */
export async function listDiscoveries(params: DiscoveriesListParams = {}): Promise<Discovery[]> {
  if (isMockMode) {
    await new Promise((r) => setTimeout(r, 400));
    return mockListDiscoveries(params);
  }

  return http.get<Discovery[]>(routes.discoveries, { query: params as any });
}

/**
 * Get trending topics by artifact count and discovery score
 */
export async function getTrendingTopics(params: TrendingTopicsParams = {}): Promise<TrendingTopic[]> {
  if (isMockMode) {
    await new Promise((r) => setTimeout(r, 300));
    return mockGetTrendingTopics(params);
  }

  return http.get<TrendingTopic[]>(routes.trendingTopics, { query: params as any });
}

/**
 * Get entity (person, lab, org) with accounts and artifacts
 */
export async function getEntity(id: string): Promise<Entity> {
  if (isMockMode) {
    await new Promise((r) => setTimeout(r, 200));
    const entity = mockGetEntity(id);
    if (!entity) throw new Error("Entity not found");
    return entity;
  }

  return http.get<Entity>(routes.entity(id));
}

/**
 * Get timeline data for a specific topic
 */
export async function getTopicTimeline(params: { topic: string; days?: number }): Promise<TopicTimelinePoint[]> {
  if (isMockMode) {
    await new Promise((r) => setTimeout(r, 300));
    return mockGetTopicTimeline(params);
  }

  return http.get<TopicTimelinePoint[]>(routes.topicTimeline(params.topic), {
    query: { days: params.days } as any
  });
}

/**
 * Refresh the discovery pipeline (fetch -> analyze -> score)
 */
export async function refreshPipeline(params: RefreshParams = {}): Promise<{
  message: string;
  stats: {
    fetched?: number;
    analyzed?: number;
    scored?: number;
  };
}> {
  if (isMockMode) {
    await new Promise((r) => setTimeout(r, 2000)); // Simulate longer processing
    return {
      message: "Pipeline refresh completed",
      stats: {
        fetched: 45,
        analyzed: 42,
        scored: 42,
      },
    };
  }

  return http.post<{ message: string; stats: any }>(routes.refresh, params);
}

/**
 * Get discovery statistics
 */
export async function getDiscoveryStats(): Promise<{
  totalArtifacts: number;
  totalDiscoveries: number;
  avgDiscoveryScore: number;
  topTopics: { name: string; count: number }[];
  sources: { source: string; count: number }[];
}> {
  if (isMockMode) {
    await new Promise((r) => setTimeout(r, 300));
    return {
      totalArtifacts: 1250,
      totalDiscoveries: 87,
      avgDiscoveryScore: 67.3,
      topTopics: [
        { name: "quantum computing", count: 23 },
        { name: "machine learning", count: 18 },
        { name: "robotics", count: 15 },
      ],
      sources: [
        { source: "arxiv", count: 650 },
        { source: "github", count: 420 },
        { source: "x", count: 180 },
      ],
    };
  }

  // In real implementation, this would be a dedicated endpoint
  const discoveries = await listDiscoveries({ limit: 1000 });
  const topics = await getTrendingTopics({ limit: 10 });

  const totalArtifacts = discoveries.length;
  const totalDiscoveries = discoveries.filter(d => d.discoveryScore > 70).length;
  const avgDiscoveryScore = discoveries.reduce((sum, d) => sum + d.discoveryScore, 0) / discoveries.length || 0;

  return {
    totalArtifacts,
    totalDiscoveries,
    avgDiscoveryScore,
    topTopics: topics.slice(0, 5).map(t => ({ name: t.name, count: t.artifactCount })),
    sources: [], // Would need aggregation
  };
}

/**
 * Get dashboard analytics data
 */
export async function getDashboardAnalytics(days: number = 30): Promise<any> {
  if (isMockMode) {
    await new Promise((r) => setTimeout(r, 600));
    return {
      source_distribution: {
        sources: [
          { source: "arxiv", count: 650, percentage: 52.0, avg_discovery_score: 72.5, avg_novelty: 0.65, avg_emergence: 0.58, avg_obscurity: 0.71 },
          { source: "github", count: 420, percentage: 33.6, avg_discovery_score: 68.3, avg_novelty: 0.58, avg_emergence: 0.62, avg_obscurity: 0.65 },
          { source: "x", count: 180, percentage: 14.4, avg_discovery_score: 61.2, avg_novelty: 0.52, avg_emergence: 0.55, avg_obscurity: 0.58 },
        ],
        total_artifacts: 1250,
        time_window: "720h"
      },
      temporal_trends: {
        daily_trends: {},
        days: 30,
        summary: {
          total_artifacts: 1250,
          avg_daily_artifacts: 41.7
        }
      },
      cross_source_correlations: {
        correlations: [
          {
            topic: "quantum error correction",
            sources: {
              arxiv: { count: 15, days_active: 12 },
              github: { count: 8, days_active: 8 },
              x: { count: 3, days_active: 4 }
            },
            source_count: 3,
            total_artifacts: 26
          },
        ],
        time_window: "720h",
        summary: {
          total_correlated_topics: 45,
          avg_sources_per_topic: 2.3
        }
      },
      score_distributions: {
        summary: {
          total_scored: 1250,
          avg_discovery_score: 67.3,
          min_discovery_score: 12.5,
          max_discovery_score: 98.7,
          avg_novelty: 0.58,
          avg_emergence: 0.58,
          avg_obscurity: 0.65
        },
        percentiles: {
          p10: 35.2,
          p25: 48.7,
          p50: 65.8,
          p75: 78.4,
          p90: 87.2,
          p95: 91.5,
          p99: 96.8
        },
        source_breakdown: [
          { source: "arxiv", count: 650, avg_discovery_score: 72.5, avg_novelty: 0.65, avg_emergence: 0.58, avg_obscurity: 0.71 },
          { source: "github", count: 420, avg_discovery_score: 68.3, avg_novelty: 0.58, avg_emergence: 0.62, avg_obscurity: 0.65 },
          { source: "x", count: 180, avg_discovery_score: 61.2, avg_novelty: 0.52, avg_emergence: 0.55, avg_obscurity: 0.58 },
        ]
      },
      system_health: {
        status: "healthy",
        timestamp: new Date().toISOString(),
        components: {
          database: {
            status: "healthy",
            size_mb: 245.6,
            artifact_count: 1250,
            entity_count: 342,
            topic_count: 156,
            recent_artifacts_24h: 42
          },
          pipeline: {
            status: "healthy",
            unanalyzed_artifacts: 23,
            unscored_artifacts: 15
          },
          api: {
            status: "healthy",
            version: "1.0.0"
          }
        }
      }
    };
  }

  return http.get<any>(`/analytics/dashboard`, { query: { days } });
}