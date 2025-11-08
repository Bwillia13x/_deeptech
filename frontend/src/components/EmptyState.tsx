import React from "react";
import { cn } from "../lib/utils";

interface EmptyStateProps {
  title: string;
  description: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}

export default function EmptyState({
  title,
  description,
  icon,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div className={cn("flex flex-col items-center justify-center rounded-lg border p-8 text-center", className)}>
      {icon && <div className="mb-4 text-muted-foreground">{icon}</div>}
      <h3 className="text-lg font-semibold">{title}</h3>
      <p className="mt-2 text-sm text-muted-foreground max-w-sm">{description}</p>
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}

// Common empty state variants
export function EmptySignals({ onCreate }: { onCreate?: () => void }) {
  return (
    <EmptyState
      title="No signals found"
      description="There are no signals matching your filters. Try adjusting your search or create a new signal."
      icon={<SignalIcon />}
      action={
        onCreate && (
          <button
            onClick={onCreate}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90 transition-colors"
          >
            Create Signal
          </button>
        )
      }
    />
  );
}

export function EmptySnapshots({ onCreate }: { onCreate?: () => void }) {
  return (
    <EmptyState
      title="No snapshots yet"
      description="Snapshots are backups of your signals at a point in time. Create your first snapshot to get started."
      icon={<SnapshotIcon />}
      action={
        onCreate && (
          <button
            onClick={onCreate}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90 transition-colors"
          >
            Create Snapshot
          </button>
        )
      }
    />
  );
}

export function EmptySearch({ query }: { query: string }) {
  return (
    <EmptyState
      title="No results found"
      description={`We couldn't find anything matching "${query}". Try adjusting your search terms.`}
      icon={<SearchIcon />}
    />
  );
}

export function EmptyDashboard() {
  return (
    <EmptyState
      title="Welcome to Signal Harvester"
      description="Connect your X/Twitter API and start harvesting signals to see data here."
      icon={<DashboardIcon />}
    />
  );
}

// Icon components
function SignalIcon() {
  return (
    <svg className="h-12 w-12" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
    </svg>
  );
}

function SnapshotIcon() {
  return (
    <svg className="h-12 w-12" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2H5a2 2 0 00-2-2z" />
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 7V5a2 2 0 012-2h4a2 2 0 012 2v2" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg className="h-12 w-12" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
    </svg>
  );
}

function DashboardIcon() {
  return (
    <svg className="h-12 w-12" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
    </svg>
  );
}