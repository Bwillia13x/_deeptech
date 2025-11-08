import { useQuery, useMutation, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { listSignals, getSignalsStats, updateSignalStatus, deleteSignal, getSignal, createSignal, updateSignal } from "../api/signals";
import type { Paginated, Signal, SignalsListParams, SignalsStats, SignalStatus, CreateSignalInput, UpdateSignalInput } from "../types/api";

export const qk = {
  signals: (params: SignalsListParams) => ["signals", "list", params] as const,
  signalsAll: ["signals", "list"] as const,
  signalsStats: ["signals", "stats"] as const,
  signal: (id: string) => ["signals", "one", id] as const
};

export function useSignalsQuery(params: SignalsListParams): UseQueryResult<Paginated<Signal>> {
  return useQuery<Paginated<Signal>>({
    queryKey: qk.signals(params),
    queryFn: () => listSignals(params),
    placeholderData: (prev) => prev,
  });
}

export function useSignalsStatsQuery(): UseQueryResult<SignalsStats> {
  return useQuery<SignalsStats>({
    queryKey: qk.signalsStats,
    queryFn: () => getSignalsStats(),
    staleTime: 10_000
  });
}

export function useUpdateSignalStatusMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: SignalStatus }) =>
      updateSignalStatus(id, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["signals"] });
      queryClient.invalidateQueries({ queryKey: qk.signalsStats });
    }
  });
}

export function useSetSignalStatusMutation() {
  return useUpdateSignalStatusMutation();
}

export function useDeleteSignalMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteSignal(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["signals"] });
      queryClient.invalidateQueries({ queryKey: qk.signalsStats });
    }
  });
}

export function useSignalQuery(id?: string): UseQueryResult<Signal> {
  return useQuery<Signal>({
    queryKey: id ? qk.signal(id) : ["signals", "one", "empty"],
    queryFn: () => getSignal(id as string),
    enabled: Boolean(id)
  });
}

export function useCreateSignalMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateSignalInput) => createSignal(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.signalsAll });
      queryClient.invalidateQueries({ queryKey: qk.signalsStats });
    }
  });
}

export function useUpdateSignalMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: UpdateSignalInput }) => updateSignal(id, input),
    onSuccess: (_data, { id }) => {
      queryClient.invalidateQueries({ queryKey: qk.signalsAll });
      queryClient.invalidateQueries({ queryKey: qk.signal(id) });
      queryClient.invalidateQueries({ queryKey: qk.signalsStats });
    }
  });
}
