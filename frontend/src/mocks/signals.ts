import { Signal, SignalStatus, SignalsStats, Paginated, CreateSignalInput, UpdateSignalInput } from "../types/api";
import { SignalsListParams } from "../types/api";

const sources = ["webhook", "poller", "kafka", "sqs", "cron"];
const names = [
  "Order Created",
  "Payment Settled",
  "Inventory Low",
  "User Signup",
  "Abandoned Cart",
  "Refund Issued",
  "Shipment Delayed",
  "Price Change",
  "Threshold Breached",
  "Heartbeat"
];

const statuses: SignalStatus[] = ["active", "inactive", "paused", "error"];

function random<T>(arr: T[]) {
  return arr[Math.floor(Math.random() * arr.length)];
}

export function mockDeleteSignal(id: string): void {
  const idx = MOCK_SIGNALS.findIndex((s) => s.id === id);
  if (idx !== -1) {
    MOCK_SIGNALS.splice(idx, 1);
  }
}

export function mockGetSignal(id: string): Signal | undefined {
  return MOCK_SIGNALS.find((s) => s.id === id);
}

export function mockCreateSignal(input: CreateSignalInput): Signal {
  const nextNum = MOCK_SIGNALS.length + 1;
  const now = new Date().toISOString();
  const sig: Signal = {
    id: `sig_${nextNum.toString().padStart(4, "0")}`,
    name: input.name,
    source: input.source,
    status: input.status,
    tags: input.tags ?? [],
    createdAt: now,
    updatedAt: now,
    lastSeenAt: undefined
  };
  MOCK_SIGNALS.unshift(sig);
  return sig;
}

export function mockUpdateSignal(id: string, input: UpdateSignalInput): Signal {
  const idx = MOCK_SIGNALS.findIndex((s) => s.id === id);
  if (idx === -1) throw new Error("Signal not found");
  const current = MOCK_SIGNALS[idx];
  const updated: Signal = {
    ...current,
    ...input,
    tags: input.tags ?? current.tags,
    updatedAt: new Date().toISOString()
  };
  MOCK_SIGNALS[idx] = updated;
  return updated;
}

function daysAgo(n: number) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString();
}

function makeSignal(id: number): Signal {
  const createdAgo = Math.floor(Math.random() * 40) + 10;
  const updatedAgo = Math.floor(Math.random() * createdAgo);
  const lastSeenAgo = Math.random() > 0.2 ? Math.floor(Math.random() * 7) : undefined;
  const status = random(statuses);
  return {
    id: `sig_${id.toString().padStart(4, "0")}`,
    name: random(names),
    source: random(sources),
    status,
    tags: Math.random() > 0.7 ? ["prod"] : ["dev"],
    createdAt: daysAgo(createdAgo),
    updatedAt: daysAgo(updatedAgo),
    lastSeenAt: lastSeenAgo ? daysAgo(lastSeenAgo) : undefined
  };
}

export const MOCK_SIGNALS: Signal[] = Array.from({ length: 42 }).map((_, i) =>
  makeSignal(i + 1)
);

export function mockListSignals(params: SignalsListParams = {}): Paginated<Signal> {
  const { page = 1, pageSize = 10, search = "", sort = "updatedAt", order = "desc", status, source } = params;
  let items = [...MOCK_SIGNALS];

  if (search) {
    const s = search.toLowerCase();
    items = items.filter(
      (x) =>
        x.name.toLowerCase().includes(s) ||
        x.source.toLowerCase().includes(s) ||
        x.id.toLowerCase().includes(s)
    );
  }

  if (status) {
    items = items.filter((x) => x.status === status);
  }
  if (source) {
    items = items.filter((x) => x.source === source);
  }

  items.sort((a, b) => {
    const dir = order === "asc" ? 1 : -1;
    const getVal = (x: Signal) => {
      switch (sort) {
        case "name":
          return x.name.toLowerCase();
        case "status":
          return x.status;
        case "lastSeenAt":
          return x.lastSeenAt ?? "";
        case "createdAt":
          return x.createdAt;
        default:
          return x.updatedAt;
      }
    };
    const av = getVal(a);
    const bv = getVal(b);
    if (av < bv) return -1 * dir;
    if (av > bv) return 1 * dir;
    return 0;
  });

  const total = items.length;
  const start = (page - 1) * pageSize;
  const paged = items.slice(start, start + pageSize);

  return { items: paged, total, page, pageSize };
}

export function mockSignalsStats(): SignalsStats {
  const stats = { total: MOCK_SIGNALS.length, active: 0, paused: 0, error: 0, inactive: 0 };
  for (const s of MOCK_SIGNALS) {
    if (s.status in stats) (stats as any)[s.status] += 1;
  }
  return stats;
}

export function mockUpdateSignalStatus(id: string, status: SignalStatus): Signal {
  const idx = MOCK_SIGNALS.findIndex((s) => s.id === id);
  if (idx === -1) {
    throw new Error("Signal not found");
  }
  const current = MOCK_SIGNALS[idx];
  const updated: Signal = {
    ...current,
    status,
    updatedAt: new Date().toISOString()
  };
  MOCK_SIGNALS[idx] = updated;
  return updated;
}
