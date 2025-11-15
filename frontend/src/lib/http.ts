import { ApiError } from "../types/api";
import { env } from "./env";

type Query = Record<string, string | number | boolean | undefined | null>;

function joinUrl(base: string, path: string) {
  if (!base) return path;
  const a = base.replace(/\/+$/, "");
  const b = path.replace(/^\/+/, "");
  return `${a}/${b}`;
}

function buildUrl(path: string, query?: Query) {
  const url = joinUrl(env.API_URL ?? "", path);
  if (!query) return url;
  const params = new URLSearchParams();
  Object.entries(query).forEach(([k, v]) => {
    if (v === undefined || v === null) return;
    params.append(k, String(v));
  });
  const qs = params.toString();
  return qs ? `${url}?${qs}` : url;
}

type RequestOptions = {
  query?: Query;
  body?: any;
  headers?: Record<string, string>;
  signal?: AbortSignal;
};

async function request<T>(method: string, path: string, opts: RequestOptions = {}) {
  const url = buildUrl(path, opts.query);
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...(opts.body ? { "Content-Type": "application/json" } : {}),
    ...(opts.headers ?? {})
  };

  if (env.API_KEY) {
    const hasCustomApiKey = Object.keys(headers).some(
      (key) => key.toLowerCase() === "x-api-key"
    );
    if (!hasCustomApiKey) {
      headers["X-API-Key"] = env.API_KEY;
    }
  }

  const res = await fetch(url, {
    method,
    headers,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
    signal: opts.signal
  });

  const isJson = res.headers.get("content-type")?.includes("application/json");
  const data = isJson ? await res.json().catch(() => undefined) : undefined;

  if (!res.ok) {
    const message = (data && (data.message || (data as any).error)) || `HTTP ${res.status}`;
    throw new ApiError(message, res.status, data);
  }

  if (res.status === 204) return undefined as unknown as T;
  return data as T;
}

export const http = {
  get: <T>(path: string, opts?: Omit<RequestOptions, "body">) => request<T>("GET", path, opts),
  post: <T>(path: string, body?: any, opts?: Omit<RequestOptions, "body">) =>
    request<T>("POST", path, { ...opts, body }),
  patch: <T>(path: string, body?: any, opts?: Omit<RequestOptions, "body">) =>
    request<T>("PATCH", path, { ...opts, body }),
  delete: <T>(path: string, opts?: Omit<RequestOptions, "body">) => request<T>("DELETE", path, opts)
};
