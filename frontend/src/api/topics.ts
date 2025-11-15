import { http } from "../lib/http";
import { isMockMode } from "../lib/env";
import {
  Topic,
  TrendingTopic,
  TrendingTopicsParams,
  TopicTimelinePoint,
  TopicStats,
  TopicMergeCandidate,
  TopicSplitDetection,
} from "../types/api";
import {
  mockGetTopicStats,
  mockGetMergeCandidates,
  mockGetSplitCandidates,
} from "../mocks/topics";

// API routes
const routes = {
  trending: "/topics/trending",
  topicTimeline: (topic: string) => `/topics/${encodeURIComponent(topic)}/timeline`,
  topicStats: (topicId: string) => `/topics/${encodeURIComponent(topicId)}/stats`,
  topicEvolution: (topicId: string) => `/topics/${encodeURIComponent(topicId)}/evolution`,
  mergeCandidates: "/topics/merges",
  splitCandidates: "/topics/splits",
};

/**
 * Get trending topics by artifact count and discovery score
 */
export async function getTrendingTopics(params: TrendingTopicsParams = {}): Promise<TrendingTopic[]> {
  if (isMockMode) {
    await new Promise((r) => setTimeout(r, 300));
    // Return mock data - would come from discoveries.ts mock
    return [];
  }

  return http.get<TrendingTopic[]>(routes.trending, {
    query: params as any,
  });
}

/**
 * Get timeline data for a specific topic
 */
export async function getTopicTimeline(params: { topic: string; days?: number }): Promise<TopicTimelinePoint[]> {
  if (isMockMode) {
    await new Promise((r) => setTimeout(r, 300));
    // Simple mock timeline with 14 days of data
    const days = params.days || 14;
    const points: TopicTimelinePoint[] = [];
    const now = new Date();
    
    for (let i = days - 1; i >= 0; i--) {
      const date = new Date(now);
      date.setDate(date.getDate() - i);
      const baseCount = Math.floor(Math.random() * 20) + 5;
      const trendFactor = 1 + (days - i) * 0.05; // Upward trend
      
      points.push({
        date: date.toISOString().split("T")[0],
        count: Math.floor(baseCount * trendFactor),
        avgScore: 50 + Math.random() * 30,
      });
    }
    
    return points;
  }

  return http.get<TopicTimelinePoint[]>(routes.topicTimeline(params.topic), {
    query: { days: params.days } as any,
  });
}

/**
 * Get comprehensive statistics for a topic
 */
export async function getTopicStats(topicId: string, windowDays: number = 30): Promise<TopicStats> {
  if (isMockMode) {
    await new Promise((r) => setTimeout(r, 400));
    return mockGetTopicStats(topicId, windowDays);
  }

  return http.get<TopicStats>(routes.topicStats(topicId), {
    query: { window_days: windowDays } as any,
  });
}

/**
 * Get evolution events for a topic
 */
export async function getTopicEvolution(
  topicId: string,
  eventType?: string,
  limit: number = 50
): Promise<any[]> {
  if (isMockMode) {
    await new Promise((r) => setTimeout(r, 300));
    return [];
  }

  const query: any = { limit };
  if (eventType) {
    query.event_type = eventType;
  }

  return http.get<any[]>(routes.topicEvolution(topicId), {
    query,
  });
}

/**
 * Get topic merge candidates
 */
export async function getMergeCandidates(
  windowDays: number = 30,
  similarityThreshold: number = 0.85
): Promise<TopicMergeCandidate[]> {
  if (isMockMode) {
    await new Promise((r) => setTimeout(r, 500));
    return mockGetMergeCandidates();
  }

  return http.get<TopicMergeCandidate[]>(routes.mergeCandidates, {
    query: { window_days: windowDays, similarity_threshold: similarityThreshold } as any,
  });
}

/**
 * Get topic split candidates
 */
export async function getSplitCandidates(
  windowDays: number = 30,
  diversityThreshold: number = 0.7
): Promise<TopicSplitDetection[]> {
  if (isMockMode) {
    await new Promise((r) => setTimeout(r, 500));
    return mockGetSplitCandidates();
  }

  return http.get<TopicSplitDetection[]>(routes.splitCandidates, {
    query: { window_days: windowDays, diversity_threshold: diversityThreshold } as any,
  });
}
