import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as Sentry from "@sentry/react";
import App from "./App";
import ErrorBoundary from "./components/ErrorBoundary";
import "./index.css";

// Initialize Sentry for error tracking
const sentryDsn = import.meta.env.VITE_SENTRY_DSN;
if (sentryDsn) {
  Sentry.init({
    dsn: sentryDsn,
    integrations: [
      Sentry.browserTracingIntegration(),
      Sentry.replayIntegration(),
    ],
    tracesSampleRate: 1.0, // Capture 100% for beta
    replaysSessionSampleRate: 0.1,
    replaysOnErrorSampleRate: 1.0,
    environment: import.meta.env.VITE_ENVIRONMENT || "beta",
    release: `signal-harvester-frontend@${import.meta.env.VITE_APP_VERSION || "0.1.0"}`,
    beforeSend(event) {
      // Filter out sensitive data
      if (event.request?.headers?.["X-API-Key"]) {
        delete event.request.headers["X-API-Key"];
      }
      return event;
    },
  });
  console.log("Sentry error tracking initialized");
} else {
  console.log("VITE_SENTRY_DSN not configured, skipping error tracking");
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5000,
      refetchOnWindowFocus: false,
    },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ErrorBoundary>
          <App />
        </ErrorBoundary>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);
