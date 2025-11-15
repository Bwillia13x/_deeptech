import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArtifactRelationship,
  GetRelationshipsParams,
  GetRelationshipsResponse,
  CitationGraphResponse,
  RelationshipStats,
  RelationshipDetectionParams,
  RelationshipDetectionStats,
} from "../types/api";
import {
  getArtifactRelationships,
  getCitationGraph,
  getRelationshipStats,
  runRelationshipDetection,
} from "../api/relationships";

export interface UseArtifactRelationshipsParams extends GetRelationshipsParams {
  artifactId: number;
}

// Relationships list query
export function useArtifactRelationships(params: UseArtifactRelationshipsParams) {
  const { artifactId, ...queryParams } = params;
  
  return useQuery({
    queryKey: ["artifact", artifactId, "relationships", queryParams],
    queryFn: async () => {
      const response = await getArtifactRelationships(artifactId, queryParams);
      return response;
    },
    enabled: !!artifactId,
    placeholderData: (previousData) => previousData,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

// Citation graph query
export interface CitationGraphParams {
  artifactId: number;
  depth?: number;
  minConfidence?: number;
}

export function useCitationGraph(params: CitationGraphParams) {
  const { artifactId, depth = 2, minConfidence = 0.5 } = params;
  
  return useQuery({
    queryKey: ["artifact", artifactId, "citation-graph", { depth, minConfidence }],
    queryFn: async () => {
      const response = await getCitationGraph(artifactId, depth, minConfidence);
      return response;
    },
    enabled: !!artifactId,
    staleTime: 5 * 60 * 1000,
  });
}

// Relationship statistics query
export function useRelationshipStats() {
  return useQuery({
    queryKey: ["relationships", "stats"],
    queryFn: async () => {
      const response = await getRelationshipStats();
      return response;
    },
    staleTime: 10 * 60 * 1000, // 10 minutes
  });
}

// Run relationship detection mutation
export function useRunRelationshipDetection() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: async (params: RelationshipDetectionParams) => {
      const response = await runRelationshipDetection(params);
      return response;
    },
    onSuccess: () => {
      // Invalidate relationship queries to refresh data
      queryClient.invalidateQueries({ queryKey: ["relationships"] });
      queryClient.invalidateQueries({ queryKey: ["artifact"] });
      queryClient.invalidateQueries({ queryKey: ["discoveries"] });
    },
  });
}

// Combine multiple relationship queries for a comprehensive view
export interface ArtifactRelationshipOverviewParams {
  artifactId: number;
  relationshipsParams?: Omit<UseArtifactRelationshipsParams, "artifactId">;
  graphParams?: Omit<CitationGraphParams, "artifactId">;
}

export function useArtifactRelationshipOverview(params: ArtifactRelationshipOverviewParams) {
  const { artifactId, relationshipsParams = {}, graphParams = {} } = params;
  
  // Parallel queries
  const relationshipsQuery = useArtifactRelationships({
    artifactId,
    ...relationshipsParams,
  });
  
  const citationGraphQuery = useCitationGraph({
    artifactId,
    depth: 2,
    minConfidence: 0.5,
    ...graphParams,
  });
  
  const statsQuery = useRelationshipStats();
  
  // Check loading state
  const isLoading = 
    relationshipsQuery.isLoading || 
    citationGraphQuery.isLoading || 
    statsQuery.isLoading;
  
  // Check error state
  const isError = 
    relationshipsQuery.isError || 
    citationGraphQuery.isError || 
    statsQuery.isError;
  
  // Combine error messages
  const error = isError ? {
    relationships: relationshipsQuery.error,
    citationGraph: citationGraphQuery.error,
    stats: statsQuery.error,
  } : null;
  
  return {
    // Individual queries
    relationshipsQuery,
    citationGraphQuery,
    statsQuery,
    
    // Combined data
    data: relationshipsQuery.data ? {
      relationships: relationshipsQuery.data,
      citationGraph: citationGraphQuery.data,
      stats: statsQuery.data,
    } : null,
    
    // Loading and error states
    isLoading,
    isError,
    error,
    
    // Refetch function
    refetch: () => {
      relationshipsQuery.refetch();
      citationGraphQuery.refetch();
      statsQuery.refetch();
    },
  };
}

// Stats overview hook for dashboard
export function useRelationshipStatsOverview() {
  const statsQuery = useRelationshipStats();
  
  // Calculate distribution percentages
  const typeDistribution = statsQuery.data
    ? Object.entries(statsQuery.data.byType).map(([type, count]) => ({
        type: type as any,
        count,
        percentage: (count / statsQuery.data.totalRelationships) * 100,
      }))
    : [];
  
  // Sort by count descending
  typeDistribution.sort((a, b) => b.count - a.count);
  
  return {
    statsQuery,
    typeDistribution,
    isLoading: statsQuery.isLoading,
    isError: statsQuery.isError,
  };
}
