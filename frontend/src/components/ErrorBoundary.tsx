import React from "react";
import * as Sentry from "@sentry/react";

export default function ErrorBoundary({ children }: { children: React.ReactNode }) {
  return (
    <Sentry.ErrorBoundary
      fallback={({ error, resetError }) => {
        const errorMessage = error instanceof Error ? error.message : String(error);
        return (
          <div className="flex flex-col items-center justify-center min-h-screen p-4">
            <div className="max-w-md w-full space-y-4 text-center">
              <h1 className="text-2xl font-bold">Something went wrong</h1>
              <p className="text-muted-foreground">
                We&apos;ve been notified and are working on a fix.
              </p>
              <div className="rounded-lg border p-4 bg-muted">
                <p className="text-sm font-mono text-muted-foreground">
                  {errorMessage || "Unknown error"}
                </p>
              </div>
              <button
                onClick={resetError}
                className="px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90 transition-colors"
              >
                Try again
              </button>
            </div>
          </div>
        );
      }}
    >
      {children}
    </Sentry.ErrorBoundary>
  );
}
