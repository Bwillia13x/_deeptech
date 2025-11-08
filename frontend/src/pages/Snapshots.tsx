import React from "react";
import { useSearchParams, Link } from "react-router-dom";
import { useSnapshotsQuery } from "../hooks/useSnapshots";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";
import type { SnapshotsListParams, SnapshotStatus } from "../types/api";

const PAGE_SIZES = [10, 20, 50];
const STATUS_OPTIONS: SnapshotStatus[] = ["ready", "processing", "failed"];

export default function Snapshots() {
  const [sp, setSp] = useSearchParams();

  const [search, setSearch] = React.useState(sp.get("q") ?? "");
  const [page, setPage] = React.useState(Number(sp.get("page") ?? 1));
  const [pageSize, setPageSize] = React.useState(Number(sp.get("pageSize") ?? 10));
  const [sort, setSort] = React.useState<SnapshotsListParams["sort"]>((sp.get("sort") as any) ?? "createdAt");
  const [order, setOrder] = React.useState<SnapshotsListParams["order"]>((sp.get("order") as any) ?? "desc");
  const [status, setStatus] = React.useState<SnapshotStatus | undefined>((sp.get("status") as SnapshotStatus) || undefined);
  const [signalId, setSignalId] = React.useState<string | undefined>(sp.get("signalId") || undefined);

  React.useEffect(() => {
    const next = new URLSearchParams();
    next.set("page", String(page));
    next.set("pageSize", String(pageSize));
    next.set("sort", String(sort));
    next.set("order", String(order));
    if (search) next.set("q", search);
    else next.delete("q");
    if (status) next.set("status", status);
    else next.delete("status");
    if (signalId) next.set("signalId", signalId);
    else next.delete("signalId");
    setSp(next, { replace: true });
  }, [page, pageSize, sort, order, search, status, signalId, setSp]);

  React.useEffect(() => {
    setPage(1);
  }, [search, pageSize, sort, order, status, signalId]);

  const params = React.useMemo(
    () => ({ page, pageSize, search, sort, order, status, signalId } as SnapshotsListParams),
    [page, pageSize, search, sort, order, status, signalId]
  );

  const { data, isLoading, isFetching } = useSnapshotsQuery(params);

  const total = data?.total ?? 0;
  const maxPage = Math.max(1, Math.ceil(total / pageSize));
  const showingFrom = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const showingTo = Math.min(page * pageSize, total);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Snapshots</h1>
        <p className="text-muted-foreground">Historical snapshots of signals.</p>
      </div>

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2 flex-wrap">
          <Input
            placeholder="Search snapshots..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-[260px]"
          />

          <select
            className="h-10 rounded-md border bg-background px-2 text-sm"
            value={status ?? ""}
            onChange={(e) => setStatus((e.target.value || undefined) as any)}
            aria-label="Status"
          >
            <option value="">All statuses</option>
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>

          <select
            className="h-10 rounded-md border bg-background px-2 text-sm"
            value={`${sort}:${order}`}
            onChange={(e) => {
              const [s, o] = e.target.value.split(":") as [typeof sort, typeof order];
              setSort(s);
              setOrder(o);
            }}
            aria-label="Sort"
          >
            <option value="createdAt:desc">Newest</option>
            <option value="createdAt:asc">Oldest</option>
            <option value="status:asc">Status A–Z</option>
            <option value="status:desc">Status Z–A</option>
          </select>
        </div>

        <div className="flex items-center gap-2">
          <div className="text-sm text-muted-foreground">
            {isLoading ? "Loading…" : `Showing ${showingFrom}-${showingTo} of ${total}`}
          </div>
          {signalId ? (
            <button
              className="text-xs rounded border px-2 py-1 bg-muted hover:bg-muted/70"
              onClick={() => setSignalId(undefined)}
              aria-label="Clear signal filter"
            >
              Signal filter: <span className="font-mono">{signalId}</span> ×
            </button>
          ) : null}
          <select
            className="h-10 rounded-md border bg-background px-2 text-sm"
            value={pageSize}
            onChange={(e) => setPageSize(Number(e.target.value))}
            aria-label="Page size"
          >
            {PAGE_SIZES.map((s) => (
              <option key={s} value={s}>
                {s} / page
              </option>
            ))}
          </select>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1 || isFetching}
          >
            Prev
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPage((p) => Math.min(maxPage, p + 1))}
            disabled={page >= maxPage || isFetching}
          >
            Next
          </Button>
        </div>
      </div>

      <div className="overflow-hidden rounded-md border">
        <table className="w-full caption-bottom text-sm">
          <thead className="bg-muted/50">
            <tr className="border-b">
              <Th>ID</Th>
              <Th>Signal</Th>
              <Th>Status</Th>
              <Th>Size</Th>
              <Th>Created</Th>
              <Th className="text-right">Actions</Th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <RowsSkeleton />
            ) : data && data.items.length > 0 ? (
              data.items.map((s) => (
                <tr key={s.id} className="border-b last:border-0">
                  <Td className="font-mono text-xs">{s.id}</Td>
                  <Td>
                    <div className="font-medium">{s.signalName ?? s.signalId}</div>
                    <div className="text-xs text-muted-foreground">
                      <Link to={`/snapshots?signalId=${encodeURIComponent(s.signalId)}`} className="underline-offset-2 hover:underline">
                        {s.signalId}
                      </Link>
                    </div>
                  </Td>
                  <Td className="capitalize">{s.status}</Td>
                  <Td>{s.sizeKb ? `${s.sizeKb} KB` : "—"}</Td>
                  <Td>{timeAgo(s.createdAt)}</Td>
                  <Td className="text-right">
                    <Link to={`/snapshots/${s.id}`}>
                      <Button variant="outline" size="sm">View</Button>
                    </Link>
                  </Td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={6} className="p-6 text-center text-sm text-muted-foreground">
                  No snapshots found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Th({ children, className }: { children: React.ReactNode; className?: string }) {
  return <th className={["px-4 py-3 text-left align-middle font-medium", className].filter(Boolean).join(" ")}>{children}</th>;
}

function Td({ children, className }: { children: React.ReactNode; className?: string }) {
  return <td className={["px-4 py-3 align-middle", className].filter(Boolean).join(" ")}>{children}</td>;
}

function RowsSkeleton() {
  return (
    <>
      {Array.from({ length: 8 }).map((_, i) => (
        <tr key={i} className="border-b last:border-0">
          <Td>
            <div className="h-4 w-28 rounded bg-muted animate-pulse" />
          </Td>
          <Td>
            <div className="h-4 w-40 rounded bg-muted animate-pulse" />
          </Td>
          <Td>
            <div className="h-4 w-20 rounded bg-muted animate-pulse" />
          </Td>
          <Td>
            <div className="h-4 w-14 rounded bg-muted animate-pulse" />
          </Td>
          <Td>
            <div className="h-4 w-24 rounded bg-muted animate-pulse" />
          </Td>
          <Td className="text-right">
            <div className="ml-auto h-8 w-20 rounded bg-muted animate-pulse" />
          </Td>
        </tr>
      ))}
    </>
  );
}

function timeAgo(iso: string) {
  const d = new Date(iso);
  const diff = Date.now() - d.getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const days = Math.floor(h / 24);
  if (days < 30) return `${days}d ago`;
  return d.toLocaleDateString();
}
