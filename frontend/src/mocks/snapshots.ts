import type { Snapshot, SnapshotStatus, SnapshotsListParams, Paginated } from "../types/api";
import { MOCK_SIGNALS } from "./signals";

const snapshotStatuses: SnapshotStatus[] = ["ready", "processing", "failed"];

function random<T>(arr: T[]) {
  return arr[Math.floor(Math.random() * arr.length)];
}

function daysAgo(n: number) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString();
}

function makeSnapshot(idNum: number): Snapshot {
  const sig = random(MOCK_SIGNALS);
  const createdAgo = Math.floor(Math.random() * 30) + 1;
  const sizeKb = Math.random() > 0.2 ? Math.floor(Math.random() * 900) + 100 : undefined;
  return {
    id: `snap_${idNum.toString().padStart(4, "0")}`,
    signalId: sig.id,
    signalName: sig.name,
    status: random(snapshotStatuses),
    sizeKb,
    createdAt: daysAgo(createdAgo)
  };
}

export const MOCK_SNAPSHOTS: Snapshot[] = Array.from({ length: 80 }).map((_, i) => makeSnapshot(i + 1));

export function mockListSnapshots(params: SnapshotsListParams = {}): Paginated<Snapshot> {
  const { page = 1, pageSize = 10, search = "", sort = "createdAt", order = "desc", status, signalId } = params;
  let items = [...MOCK_SNAPSHOTS];

  if (search) {
    const s = search.toLowerCase();
    items = items.filter(
      (x) =>
        x.id.toLowerCase().includes(s) ||
        x.signalId.toLowerCase().includes(s) ||
        (x.signalName ? x.signalName.toLowerCase().includes(s) : false)
    );
  }
  if (status) items = items.filter((x) => x.status === status);
  if (signalId) items = items.filter((x) => x.signalId === signalId);

  items.sort((a, b) => {
    const dir = order === "asc" ? 1 : -1;
    const av = sort === "status" ? a.status : a.createdAt;
    const bv = sort === "status" ? b.status : b.createdAt;
    if (av < bv) return -1 * dir;
    if (av > bv) return 1 * dir;
    return 0;
  });

  const total = items.length;
  const start = (page - 1) * pageSize;
  const paged = items.slice(start, start + pageSize);
  return { items: paged, total, page, pageSize };
}

export function mockGetSnapshot(id: string): Snapshot | undefined {
  return MOCK_SNAPSHOTS.find((s) => s.id === id);
}
