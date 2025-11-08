import { http } from "../lib/http";
import { isMockMode } from "../lib/env";
import type { Paginated, Snapshot, SnapshotsListParams } from "../types/api";
import { mockListSnapshots, mockGetSnapshot } from "../mocks/snapshots";

const routes = {
  list: "/snapshots",
  detail: (id: string) => `/snapshots/${encodeURIComponent(id)}`,
};

export async function listSnapshots(params: SnapshotsListParams): Promise<Paginated<Snapshot>> {
  if (isMockMode) {
    await new Promise((r) => setTimeout(r, 350));
    return mockListSnapshots(params);
  }
  return http.get<Paginated<Snapshot>>(routes.list, { query: params as any });
}

export async function getSnapshot(id: string): Promise<Snapshot | undefined> {
  if (isMockMode) {
    await new Promise((r) => setTimeout(r, 250));
    return mockGetSnapshot(id);
  }
  return http.get<Snapshot>(routes.detail(id));
}
