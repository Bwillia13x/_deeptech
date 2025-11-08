export const env = {
  API_URL:
    (import.meta as any).env?.VITE_API_URL ||
    (import.meta as any).env?.VITE_API_BASE_URL,
  USE_MOCKS: ((import.meta as any).env?.VITE_USE_MOCKS as string | undefined) === "true",
  DEV: ((import.meta as any).env?.DEV as boolean | undefined) ?? false
};

// Use mocks if explicitly enabled or if no API URL set (ideal for local dev)
export const isMockMode = env.USE_MOCKS || !env.API_URL;
