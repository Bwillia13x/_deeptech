import { useCallback, useRef, useState } from "react";
import { getBulkJob, openBulkJobStream } from "../api/bulk";
import type { BulkJobStatus } from "../api/bulk";

type UseBulkOperationOptions = {
  onProgress?: (status: BulkJobStatus) => void;
};

export function useBulkOperation(options: UseBulkOperationOptions = {}) {
  const { onProgress } = options;
  const [serverJobId, setServerJobId] = useState<string | null>(null);
  const cancelRef = useRef(false);

  const runServerBulk = useCallback(
    async (start: () => Promise<{ jobId: string; total: number }>) => {
      cancelRef.current = false;
      const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

      try {
        const payload = await start();
        if (!payload || !payload.jobId) {
          return null;
        }
        const { jobId, total } = payload;
        setServerJobId(jobId);
        onProgress?.({ jobId, total, done: 0, fail: 0, status: "running" });

        let finalStatus: BulkJobStatus | null = null;
        const sseSupported = typeof window !== "undefined" && "EventSource" in window;

        if (sseSupported) {
          try {
            const stream = openBulkJobStream(jobId, (status) => {
              finalStatus = status;
              onProgress?.(status);
            });
            const connected = await Promise.race([
              stream.connected,
              sleep(1000).then(() => false),
            ]);
            if (connected) {
              await stream.wait;
            } else {
              stream.close();
            }
          } catch {
            // Fallback to polling if SSE fails
          }
        }

        if (!finalStatus) {
          let status: BulkJobStatus;
          do {
            if (cancelRef.current) break;
            status = await getBulkJob(jobId);
            finalStatus = status;
            onProgress?.(status);
            if (status.status === "running" && !cancelRef.current) {
              await sleep(700);
            }
          } while (status.status === "running" && !cancelRef.current);
        }

        return finalStatus;
      } catch {
        return null;
      } finally {
        setServerJobId(null);
        cancelRef.current = false;
      }
    },
    [onProgress]
  );

  const cancelCurrentJob = useCallback(() => {
    cancelRef.current = true;
  }, []);

  return {
    serverJobId,
    runServerBulk,
    cancelCurrentJob,
  };
}
