import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Entity,
  EntityStats,
  Discovery,
  EntityCandidate,
  EntityMergeHistoryItem,
  MergeEntityInput,
  EntityDecisionInput,
} from "../types/api";
import { http } from "../lib/http";

export interface ListEntitiesParams {
  entityType?: string;
  search?: string;
  page?: number;
  pageSize?: number;
  sort?: string;
  order?: "asc" | "desc";
}

export interface SearchEntitiesParams {
  q: string;
  entityType?: string;
  limit?: number;
}

export interface GetEntityArtifactsParams {
  entityId: string;
  source?: string;
  minScore?: number;
  limit?: number;
  offset?: number;
}

// Entity list query
export function useEntities(params: ListEntitiesParams = {}) {
  return useQuery({
    queryKey: ["entities", params],
    queryFn: async () => {
      const { page = 1, pageSize = 20, ...rest } = params;
      const response = await http.get<{
        items: Entity[];
        total: number;
        page: number;
        pageSize: number;
      }>("/entities", {
        query: { page, pageSize, ...rest },
      });
      return response;
    },
    placeholderData: (previousData) => previousData,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

// Single entity query
export function useEntity(entityId: string | number) {
  const id = typeof entityId === "string" ? entityId : entityId.toString();

  return useQuery({
    queryKey: ["entity", id],
    queryFn: async () => {
      const response = await http.get<Entity>(`/entities/${id}`);
      return response;
    },
    enabled: !!entityId,
    staleTime: 5 * 60 * 1000,
  });
}

// Entity search query
export function useEntitySearch(params: SearchEntitiesParams) {
  return useQuery({
    queryKey: ["entities", "search", params],
    queryFn: async () => {
      const response = await http.get<{
        entity: Entity;
        relevanceScore: number;
        matchReason: string;
      }[]>("/entities/search", {
        query: { q: params.q, entityType: params.entityType, limit: params.limit },
      });
      return response;
    },
    enabled: !!params.q && params.q.length > 2,
    staleTime: 5 * 60 * 1000,
  });
}

// Entity statistics query
export function useEntityStats(entityId: string | number, days = 30) {
  const id = typeof entityId === "string" ? entityId : entityId.toString();

  return useQuery({
    queryKey: ["entity", id, "stats", days],
    queryFn: async () => {
      const response = await http.get<EntityStats>(`/entities/${id}/stats`, {
        query: { days },
      });
      return response;
    },
    enabled: !!entityId,
    staleTime: 5 * 60 * 1000,
  });
}

// Entity artifacts query
export function useEntityArtifacts(params: GetEntityArtifactsParams) {
  const { entityId, ...queryParams } = params;

  return useQuery({
    queryKey: ["entity", entityId, "artifacts", queryParams],
    queryFn: async () => {
      const response = await http.get<{
        items: Discovery[];
        total: number;
        nextCursor?: string | null;
        hasMore: boolean;
      }>(`/entities/${entityId}/artifacts`, {
        query: queryParams,
      });
      return response;
    },
    enabled: !!entityId,
    placeholderData: (previousData) => previousData,
  });
}

export function useEntityResolutionCandidates(entityId: string | number) {
  const id = typeof entityId === "string" ? entityId : entityId.toString();

  return useQuery({
    queryKey: ["entity", id, "candidates"],
    queryFn: async () => {
      const response = await http.get<EntityCandidate[]>(`/entities/${id}/candidates`);
      return response;
    },
    enabled: !!entityId,
    staleTime: 5 * 60 * 1000,
  });
}

export function useEntityMergeHistory(entityId: string | number, limit = 25) {
  const id = typeof entityId === "string" ? entityId : entityId.toString();

  return useQuery({
    queryKey: ["entity", id, "history", limit],
    queryFn: async () => {
      const response = await http.get<EntityMergeHistoryItem[]>(`/entities/${id}/history`, {
        query: { limit },
      });
      return response;
    },
    enabled: !!entityId,
    staleTime: 60 * 1000,
  });
}

function invalidateEntityResolutionQueries(queryClient: ReturnType<typeof useQueryClient>, id: string) {
  queryClient.invalidateQueries({ queryKey: ["entity", id, "candidates"] });
  queryClient.invalidateQueries({ queryKey: ["entity", id, "history"] });
  queryClient.invalidateQueries({ queryKey: ["entity", id] });
  queryClient.invalidateQueries({ queryKey: ["entity", id, "stats"] });
}

export function useMergeEntity(entityId: string | number) {
  const id = typeof entityId === "string" ? entityId : entityId.toString();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (payload: MergeEntityInput) => {
      const response = await http.post(`/entities/${id}/merge`, payload);
      return response;
    },
    onSuccess: () => invalidateEntityResolutionQueries(queryClient, id),
  });
}

export function useEntityDecision(entityId: string | number) {
  const id = typeof entityId === "string" ? entityId : entityId.toString();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (payload: EntityDecisionInput) => {
      const response = await http.post(`/entities/${id}/decisions`, payload);
      return response;
    },
    onSuccess: () => invalidateEntityResolutionQueries(queryClient, id),
  });
}
