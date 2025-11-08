import { http } from "../lib/http";
import { env } from "../lib/env";
import type { SignalStatus } from "../types/api";
import { ApiError } from "../types/api";

export type BulkScope = {
  ids?: string[];
  filters?: {
    search?: string;
    status?: SignalStatus;
    source?: string;
  };
};

export type BulkJobStatus = {
  jobId: string;
  status: "running" | "completed" | "cancelled" | "failed";
  total: number;
  done: number;
  fail: number;
};

function isUnsupportedStatus(status: number) {
  return status === 404 || status === 405 || status === 501;
}

export async function startBulkSetSignalStatus(scope: BulkScope, status: SignalStatus): Promise<{ jobId: string; total: number }> {
  try {
    return await http.post<{ jobId: string; total: number }>("/signals/bulk/status", { ...scope, status });
  } catch (e: any) {
    if (e instanceof ApiError && isUnsupportedStatus(e.status)) {
      throw new Error("unsupported");
    }
    throw e;
  }
}

export async function startBulkDeleteSignals(scope: BulkScope): Promise<{ jobId: string; total: number }> {
  try {
    return await http.post<{ jobId: string; total: number }>("/signals/bulk/delete", scope);
  } catch (e: any) {
    if (e instanceof ApiError && isUnsupportedStatus(e.status)) {
      throw new Error("unsupported");
    }
    throw e;
  }
}

export async function getBulkJob(jobId: string): Promise<BulkJobStatus> {
  return http.get<BulkJobStatus>(`/bulk-jobs/${encodeURIComponent(jobId)}`);
}

export async function cancelBulkJob(jobId: string): Promise<void> {
  await http.post<void>(`/bulk-jobs/${encodeURIComponent(jobId)}/cancel`);
}

function buildSseUrl(path: string) {
  if (env.API_URL) {
    const base = env.API_URL.replace(/\/+$/, "");
    const p = path.replace(/^\/+/, "");
    return `${base}/${p}`;
  }
  return path;
}

export function openBulkJobStream(
  jobId: string,
  onUpdate: (st: BulkJobStatus) => void
): { connected: Promise<boolean>; wait: Promise<void>; close: () => void } {
  const url = buildSseUrl(`/bulk-jobs/${encodeURIComponent(jobId)}/stream`);
  const es = new EventSource(url);

  let opened = false;
  let finished = false;

  const connected = new Promise<boolean>((resolve) => {
    es.onopen = () => {
      opened = true;
      resolve(true);
    };
    es.onerror = () => {
      if (!opened) resolve(false);
    };
  });

  const wait = new Promise<void>((resolve) => {
    const onProgress = (evt: MessageEvent) => {
      try {
        const data = JSON.parse(evt.data) as BulkJobStatus;
        onUpdate(data);
        if (data.status !== "running") {
          cleanup();
          resolve();
        }
      } catch {
        // ignore
      }
    };
    const onEnd = () => {
      cleanup();
      resolve();
    };
    function cleanup() {
      if (finished) return;
      finished = true;
      es.removeEventListener("progress", onProgress as any);
      es.removeEventListener("end", onEnd as any);
      try {
        es.close();
      } catch { void 0; }
    }

    es.addEventListener("progress", onProgress as any);
    es.addEventListener("end", onEnd as any);
  });

  const close = () => {
    try {
      es.close();
    } catch { void 0; }
  };

  return { connected, wait, close };
}
