import { ApiError } from "../types/api";
import { env } from "./env";
import { toast } from "sonner";

// Configuration for retry logic
export interface RetryConfig {
  maxRetries?: number;
  retryDelay?: number; // in milliseconds
  retryOn?: number[]; // HTTP status codes to retry on
}

const DEFAULT_RETRY_CONFIG: Required<RetryConfig> = {
  maxRetries: 3,
  retryDelay: 1000,
  retryOn: [408, 429, 500, 502, 503, 504],
};

// Configuration for request timeout
export interface TimeoutConfig {
  timeout?: number; // in milliseconds
}

const DEFAULT_TIMEOUT_CONFIG: Required<TimeoutConfig> = {
  timeout: 30000, // 30 seconds
};

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

// Sleep helper for retry delays
function sleep(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// Check if we should retry based on status code
function shouldRetry(status: number, retryOn: number[]): boolean {
  return retryOn.includes(status);
}

// Create abort controller with timeout
function createTimeoutController(timeout: number): { controller: AbortController; timeoutId: ReturnType<typeof setTimeout> } {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);
  return { controller, timeoutId };
}

async function requestWithRetry<T>(
  method: string,
  path: string,
  opts: RequestOptions & RetryConfig & TimeoutConfig = {}
): Promise<T> {
  const retryConfig = { ...DEFAULT_RETRY_CONFIG, ...opts };
  const timeoutConfig = { ...DEFAULT_TIMEOUT_CONFIG, ...opts };
  
  let lastError: Error | ApiError | undefined;
  
  for (let attempt = 0; attempt <= retryConfig.maxRetries; attempt++) {
    try {
      // Create timeout controller
      const { controller: timeoutController, timeoutId } = createTimeoutController(timeoutConfig.timeout);
      
      // Merge signals if provided
      let signal = timeoutController.signal;
      if (opts.signal) {
        // If caller provided a signal, combine them
        const combinedController = new AbortController();
        opts.signal.addEventListener('abort', () => combinedController.abort());
        timeoutController.signal.addEventListener('abort', () => combinedController.abort());
        signal = combinedController.signal;
        
        // Clean up listeners
        setTimeout(() => {
          opts.signal?.removeEventListener('abort', () => combinedController.abort());
          timeoutController.signal.removeEventListener('abort', () => combinedController.abort());
        }, 0);
      }
      
      const url = buildUrl(path, opts.query);
      const headers: Record<string, string> = {
        Accept: "application/json",
        ...(opts.body ? { "Content-Type": "application/json" } : {}),
        ...(opts.headers ?? {})
      };

      const res = await fetch(url, {
        method,
        headers,
        body: opts.body ? JSON.stringify(opts.body) : undefined,
        signal
      });

      // Clear timeout since request completed
      clearTimeout(timeoutId);

      const isJson = res.headers.get("content-type")?.includes("application/json");
      const data = isJson ? await res.json().catch(() => undefined) : undefined;

      if (!res.ok) {
        const message = (data && (data.message || (data as any).error)) || `HTTP ${res.status}`;
        const apiError = new ApiError(message, res.status, data);
        
        // Check if we should retry
        if (attempt < retryConfig.maxRetries && shouldRetry(res.status, retryConfig.retryOn)) {
          const delay = retryConfig.retryDelay * Math.pow(2, attempt); // Exponential backoff
          console.warn(`Request failed with ${res.status}, retrying in ${delay}ms (attempt ${attempt + 1}/${retryConfig.maxRetries})`);
          await sleep(delay);
          lastError = apiError;
          continue;
        }
        
        throw apiError;
      }

      if (res.status === 204) return undefined as unknown as T;
      return data as T;
      
    } catch (error) {
      // Clear timeout if it was set
      if (error instanceof Error && error.name === 'AbortError') {
        throw new ApiError("Request timed out", 408, { timeout: timeoutConfig.timeout });
      }
      
      // Check if we should retry on network errors
      const isNetworkError = error instanceof TypeError && error.message === 'Failed to fetch';
      if (isNetworkError && attempt < retryConfig.maxRetries) {
        const delay = retryConfig.retryDelay * Math.pow(2, attempt);
        console.warn(`Network error, retrying in ${delay}ms (attempt ${attempt + 1}/${retryConfig.maxRetries})`);
        await sleep(delay);
        lastError = error as Error;
        continue;
      }
      
      throw error;
    }
  }
  
  // If we get here, all retries failed
  throw lastError || new ApiError("All retry attempts failed", 500);
}

// Enhanced HTTP client with retry logic
export const httpEnhanced = {
  get: <T>(path: string, opts?: Omit<RequestOptions & RetryConfig & TimeoutConfig, "body">) =>
    requestWithRetry<T>("GET", path, opts || {}),
  
  post: <T>(path: string, body?: any, opts?: Omit<RequestOptions & RetryConfig & TimeoutConfig, "body">) =>
    requestWithRetry<T>("POST", path, { ...opts, body }),
  
  patch: <T>(path: string, body?: any, opts?: Omit<RequestOptions & RetryConfig & TimeoutConfig, "body">) =>
    requestWithRetry<T>("PATCH", path, { ...opts, body }),
  
  delete: <T>(path: string, opts?: Omit<RequestOptions & RetryConfig & TimeoutConfig, "body">) =>
    requestWithRetry<T>("DELETE", path, opts || {}),
};

// API client wrapper with user-friendly error messages
export class ApiClient {
  private static handleError(error: unknown): never {
    if (error instanceof ApiError) {
      let userMessage = "An error occurred";
      
      // Handle specific error cases
      if (error.status === 401) {
        userMessage = "Authentication failed. Please check your API key.";
        toast.error(userMessage);
      } else if (error.status === 403) {
        userMessage = "You don't have permission to perform this action.";
        toast.error(userMessage);
      } else if (error.status === 404) {
        userMessage = "The requested resource was not found.";
        toast.error(userMessage);
      } else if (error.status === 429) {
        userMessage = "Too many requests. Please slow down.";
        toast.error(userMessage);
      } else if (error.status >= 500) {
        userMessage = "Server error. Please try again later.";
        toast.error(userMessage);
      } else if (error.message.includes("timeout") || error.status === 408) {
        userMessage = "Request timed out. Please check your connection.";
        toast.error(userMessage);
      } else if (error.message.includes("Failed to fetch")) {
        userMessage = "Network error. Please check your connection.";
        toast.error(userMessage);
      } else {
        userMessage = error.message || "An unexpected error occurred";
        toast.error(userMessage);
      }
      
      // Log detailed error for debugging
      console.error("API Error:", {
        status: error.status,
        message: error.message,
        data: error.data,
        userMessage
      });
      
      throw new ApiError(userMessage, error.status, error.data);
    }
    
    // Unknown error
    console.error("Unknown error:", error);
    toast.error("An unexpected error occurred");
    throw new ApiError("An unexpected error occurred", 500);
  }

  static async get<T>(path: string, opts?: RequestOptions & RetryConfig & TimeoutConfig): Promise<T> {
    try {
      return await httpEnhanced.get<T>(path, opts);
    } catch (error) {
      this.handleError(error);
    }
  }

  static async post<T>(path: string, body?: any, opts?: RequestOptions & RetryConfig & TimeoutConfig): Promise<T> {
    try {
      return await httpEnhanced.post<T>(path, body, opts);
    } catch (error) {
      this.handleError(error);
    }
  }

  static async patch<T>(path: string, body?: any, opts?: RequestOptions & RetryConfig & TimeoutConfig): Promise<T> {
    try {
      return await httpEnhanced.patch<T>(path, body, opts);
    } catch (error) {
      this.handleError(error);
    }
  }

  static async delete<T>(path: string, opts?: RequestOptions & RetryConfig & TimeoutConfig): Promise<T> {
    try {
      return await httpEnhanced.delete<T>(path, opts);
    } catch (error) {
      this.handleError(error);
    }
  }
}

// Re-export the enhanced HTTP client as the default
export { httpEnhanced as http };

// Export both the raw enhanced client and the wrapped API client
export default {
  http: httpEnhanced,
  api: ApiClient,
};