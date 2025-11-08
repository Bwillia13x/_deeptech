import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { listSnapshots, getSnapshot } from "../api/snapshots";
import type { Paginated, Snapshot, SnapshotsListParams } from "../types/api";

export const qk = {
  snapshots: (params: SnapshotsListParams) => ["snapshots", "list", params] as const,
  snapshot: (id: string | undefined) => ["snapshots", "detail", id] as const,
};

export function useSnapshotsQuery(params: SnapshotsListParams): UseQueryResult<Paginated<Snapshot>> {
  return useQuery<Paginated<Snapshot>>({
    queryKey: qk.snapshots(params),
    queryFn: () => listSnapshots(params),
    placeholderData: (prev) => prev,
  });
}

export function useSnapshotQuery(id: string | undefined): UseQueryResult<Snapshot | undefined> {
  return useQuery<Snapshot | undefined>({
    queryKey: qk.snapshot(id),
    queryFn: () => (id ? getSnapshot(id) : Promise.resolve(undefined)),
    enabled: !!id,
    staleTime: 10_000,
  });
}
