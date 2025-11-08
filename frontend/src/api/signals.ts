import { http } from "../lib/http";
import { isMockMode } from "../lib/env";
import { Paginated, Signal, SignalsListParams, SignalsStats, SignalStatus, CreateSignalInput, UpdateSignalInput } from "../types/api";
import { mockListSignals, mockSignalsStats, mockUpdateSignalStatus, mockDeleteSignal, mockGetSignal, mockCreateSignal, mockUpdateSignal } from "../mocks/signals";

// API routes can be adjusted to your backend
const routes = {
  list: "/signals",
  stats: "/signals/stats",
  one: (id: string) => `/signals/${encodeURIComponent(id)}`
};

export async function listSignals(params: SignalsListParams): Promise<Paginated<Signal>> {
  if (isMockMode) {
    await new Promise((r) => setTimeout(r, 400)); // simulate latency
    return mockListSignals(params);
  }
  return http.get<Paginated<Signal>>(routes.list, { query: params as any });
}

export async function getSignal(id: string): Promise<Signal> {
  if (isMockMode) {
    await new Promise((r) => setTimeout(r, 200));
    const s = mockGetSignal(id);
    if (!s) throw new Error("Not found");
    return s;
  }
  return http.get<Signal>(routes.one(id));
}

export async function createSignal(input: CreateSignalInput): Promise<Signal> {
  if (isMockMode) {
    await new Promise((r) => setTimeout(r, 250));
    return mockCreateSignal(input);
  }
  return http.post<Signal>(routes.list, input);
}

export async function updateSignal(id: string, input: UpdateSignalInput): Promise<Signal> {
  if (isMockMode) {
    await new Promise((r) => setTimeout(r, 250));
    return mockUpdateSignal(id, input);
  }
  return http.patch<Signal>(routes.one(id), input);
}

export async function getSignalsStats(): Promise<SignalsStats> {
  if (isMockMode) {
    await new Promise((r) => setTimeout(r, 300));
    return mockSignalsStats();
  }
  return http.get<SignalsStats>(routes.stats);
}

export async function updateSignalStatus(id: string, status: SignalStatus): Promise<Signal> {
  if (isMockMode) {
    await new Promise((r) => setTimeout(r, 250));
    return mockUpdateSignalStatus(id, status);
  }
  return http.patch<Signal>(`${routes.list}/${id}`, { status });
}

export function setSignalStatus(id: string, status: SignalStatus) {
  return updateSignalStatus(id, status);
}

export async function deleteSignal(id: string): Promise<void> {
  if (isMockMode) {
    await new Promise((r) => setTimeout(r, 200));
    mockDeleteSignal(id);
    return;
  }
  await http.delete<void>(`${routes.list}/${id}`);
}
