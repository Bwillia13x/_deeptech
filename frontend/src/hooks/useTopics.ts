import { useQuery } from "@tanstack/react-query";
import {
  Topic,
  TrendingTopic,
  TopicStats,
  TopicMergeCandidate,
  TopicSplitDetection,
  TopicTimelinePoint,
} from "../types/api";
import {
  getTrendingTopics,
  getTopicTimeline,
  getTopicStats,
  getTopicEvolution,
  getMergeCandidates,
  getSplitCandidates,
} from "../api/topics";

export interface ListTopicsParams {
  windowDays?: number;
  limit?: number;
  minArtifactCount?: number;
}

export interface TopicStatsParams {
  topicId: string;
  windowDays?: number;
}

// Topic list query
export function useTopics(params: ListTopicsParams = {}) {
  return useQuery({
    queryKey: ["topics", params],
    queryFn: async () => {
      const response = await getTrendingTopics(params);
      return response;
    },
    placeholderData: (previousData) => previousData,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

// Single topic stats query
export function useTopicStats({ topicId, windowDays = 30 }: TopicStatsParams) {
  return useQuery({
    queryKey: ["topic", topicId, "stats", windowDays],
    queryFn: async () => {
      const response = await getTopicStats(topicId, windowDays);
      return response;
    },
    enabled: !!topicId,
    staleTime: 5 * 60 * 1000,
  });
}

// Topic timeline query
export function useTopicTimeline(topicName: string, days: number = 14) {
  return useQuery({
    queryKey: ["topic", topicName, "timeline", days],
    queryFn: async () => {
      const response = await getTopicTimeline({ topic: topicName, days });
      return response;
    },
    enabled: !!topicName && topicName.length > 0,
    staleTime: 5 * 60 * 1000,
  });
}

// Topic evolution events query
export function useTopicEvolution(topicId: string, eventType?: string, limit: number = 50) {
  return useQuery({
    queryKey: ["topic", topicId, "evolution", eventType, limit],
    queryFn: async () => {
      const response = await getTopicEvolution(topicId, eventType, limit);
      return response;
    },
    enabled: !!topicId,
    staleTime: 5 * 60 * 1000,
  });
}

// Merge candidates query
export function useMergeCandidates(windowDays: number = 30, similarityThreshold: number = 0.85) {
  return useQuery({
    queryKey: ["topics", "merges", windowDays, similarityThreshold],
    queryFn: async () => {
      const response = await getMergeCandidates(windowDays, similarityThreshold);
      return response;
    },
    staleTime: 5 * 60 * 1000,
  });
}

// Split candidates query
export function useSplitCandidates(windowDays: number = 30, diversityThreshold: number = 0.7) {
  return useQuery({
    queryKey: ["topics", "splits", windowDays, diversityThreshold],
    queryFn: async () => {
      const response = await getSplitCandidates(windowDays, diversityThreshold);
      return response;
    },
    staleTime: 5 * 60 * 1000,
  });
}

// Topic detail hook (combines multiple queries)
export function useTopicDetail(topicId: string, topicName: string, windowDays: number = 30) {
  // Parallel queries for topic data
  const statsQuery = useTopicStats({ topicId, windowDays });
  const timelineQuery = useTopicTimeline(topicName, windowDays);
  const evolutionQuery = useTopicEvolution(topicId, undefined, 20);
  const mergeCandidatesQuery = useMergeCandidates(Math.min(windowDays, 30), 0.85);
  const splitCandidatesQuery = useSplitCandidates(Math.min(windowDays, 30), 0.7);

  // Check if any query is loading
  const isLoading = 
    statsQuery.isLoading || 
    timelineQuery.isLoading || 
    evolutionQuery.isLoading ||
    mergeCandidatesQuery.isLoading ||
    splitCandidatesQuery.isLoading;

  // Check if any query has error
  const isError = 
    statsQuery.isError || 
    timelineQuery.isError || 
    evolutionQuery.isError ||
    mergeCandidatesQuery.isError ||
    splitCandidatesQuery.isError;

  // Combine error messages
  const error = isError ? {
    stats: statsQuery.error,
    timeline: timelineQuery.error,
    evolution: evolutionQuery.error,
    merges: mergeCandidatesQuery.error,
    splits: splitCandidatesQuery.error,
  } : null;

  // Get relevant merge/split candidates for this topic
  const relevantMerges = (mergeCandidatesQuery.data || []).filter(
    (candidate) => 
      candidate.primaryTopic.id === topicId || 
      candidate.secondaryTopic.id === topicId
  );

  const relevantSplits = (splitCandidatesQuery.data || []).filter(
    (candidate) => candidate.primaryTopic.id === topicId
  );

  return {
    // Queries
    statsQuery,
    timelineQuery,
    evolutionQuery,
    mergeCandidatesQuery,
    splitCandidatesQuery,

    // Combined data
    data: statsQuery.data ? {
      ...statsQuery.data,
      timeline: timelineQuery.data || [],
      recentEvents: evolutionQuery.data || [],
      mergeCandidates: relevantMerges,
      splitCandidates: relevantSplits,
    } : null,

    // Loading and error states
    isLoading,
    isError,
    error,

    // Refetch functions
    refetch: () => {
      statsQuery.refetch();
      timelineQuery.refetch();
      evolutionQuery.refetch();
      mergeCandidatesQuery.refetch();
      splitCandidatesQuery.refetch();
    },
  };
}
