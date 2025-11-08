import React from "react";
import { useSignalsStatsQuery } from "../hooks/useSignals";
import { Skeleton } from "../components/ui/skeleton";

export default function Dashboard() {
  const { data, isLoading } = useSignalsStatsQuery();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p className="text-muted-foreground">
          Overview of signals and recent activity.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Total Signals" value={data?.total} loading={isLoading} />
        <StatCard label="Active" value={data?.active} loading={isLoading} />
        <StatCard label="Paused" value={data?.paused} loading={isLoading} />
        <StatCard label="Errors" value={data?.error} loading={isLoading} />
      </div>

      <div className="rounded-lg border p-6">
        <h2 className="text-lg font-semibold">Recent Activity</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Data will appear here once the API is connected.
        </p>
      </div>
    </div>
  );
}

function StatCard({ label, value, loading }: { label: string; value?: number; loading: boolean }) {
  return (
    <div className="rounded-lg border p-4">
      <div className="text-sm text-muted-foreground">{label}</div>
      <div className="mt-2 text-3xl font-semibold">
        {loading ? <Skeleton className="h-8 w-16" /> : value ?? 0}
      </div>
    </div>
  );
}
