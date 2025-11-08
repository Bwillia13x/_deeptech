import React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useSearchParams, useNavigate } from "react-router-dom";
import { useSignalsQuery, useUpdateSignalStatusMutation, useDeleteSignalMutation } from "../hooks/useSignals";
import { useDebounce } from "../hooks/useDebounce";
import { Input } from "./ui/input";
import { Button } from "./ui/button";
import { StatusBadge } from "./StatusBadge";
import { cn } from "../lib/utils";
import { toast } from "sonner";
import type { SignalsListParams, SignalStatus } from "../types/api";
import { startBulkSetSignalStatus, startBulkDeleteSignals, getBulkJob, openBulkJobStream, cancelBulkJob } from "../api/bulk";
import { setSignalStatus as apiSetSignalStatus, deleteSignal as apiDeleteSignal, listSignals as apiListSignals } from "../api/signals";
import { useConfirm } from "./ConfirmDialog";
import { Dropdown, DropdownItem, DropdownSeparator } from "./ui/dropdown";
import EmptyState, { EmptySignals, EmptySearch } from "./EmptyState";

const PAGE_SIZES = [10, 20, 50];

export default function SignalsTable() {
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { confirm, Confirm } = useConfirm();

  const [search, setSearch] = React.useState(() => searchParams.get("q") ?? "");
  const [page, setPage] = React.useState(() => {
    const p = parseInt(searchParams.get("page") ?? "1", 10);
    return Number.isFinite(p) && p > 0 ? p : 1;
  });
  const [pageSize, setPageSize] = React.useState(() => {
    const ps = parseInt(searchParams.get("pageSize") ?? "10", 10);
    return PAGE_SIZES.includes(ps) ? ps : 10;
  });
  const [sort, setSort] = React.useState<SignalsListParams["sort"]>(() => {
    const s = searchParams.get("sort") as SignalsListParams["sort"] | null;
    const allowed: SignalsListParams["sort"][] = [
      "name",
      "status",
      "lastSeenAt",
      "createdAt",
      "updatedAt"
    ];
    return s && allowed.includes(s) ? s : "updatedAt";
  });
  const [order, setOrder] = React.useState<SignalsListParams["order"]>(() => {
    const o = searchParams.get("order") as SignalsListParams["order"] | null;
    return o === "asc" || o === "desc" ? o : "desc";
  });
  const [status, setStatus] = React.useState<SignalStatus | undefined>(() => {
    const s = searchParams.get("status");
    const allowed: SignalStatus[] = ["active", "paused", "error", "inactive"];
    return s && (allowed as string[]).includes(s) ? (s as SignalStatus) : undefined;
  });
  const [source, setSource] = React.useState<string | undefined>(() => {
    const src = searchParams.get("source");
    return src || undefined;
  });

  const debouncedSearch = useDebounce(search, 400);
  const updateStatus = useUpdateSignalStatusMutation();
  const deleteMutation = useDeleteSignalMutation();
  const [pendingId, setPendingId] = React.useState<string | null>(null);
  const [bulkLoading, setBulkLoading] = React.useState<null | "pause" | "resume" | "delete">(null);
  const [progress, setProgress] = React.useState<{ total: number; done: number; fail: number } | null>(null);
  const cancelRef = React.useRef(false);
  const [serverJobId, setServerJobId] = React.useState<string | null>(null);

  React.useEffect(() => {
    setPage(1);
  }, [debouncedSearch, pageSize, sort, order]);

  React.useEffect(() => {
    const sp = new URLSearchParams();
    if (debouncedSearch) sp.set("q", debouncedSearch);
    sp.set("page", String(page));
    sp.set("pageSize", String(pageSize));
    sp.set("sort", String(sort));
    sp.set("order", String(order));
    if (status) sp.set("status", status);
    if (source) sp.set("source", source);
    setSearchParams(sp, { replace: true });
  }, [debouncedSearch, page, pageSize, sort, order, status, source, setSearchParams]);

  const params = React.useMemo(
    () => ({ page, pageSize, search: debouncedSearch, sort, order, status, source }),
    [page, pageSize, debouncedSearch, sort, order, status, source]
  );

  const { data, isLoading, isFetching, isError, error } = useSignalsQuery(params);

  React.useEffect(() => {
    if (isError && error) {
      toast.error("Failed to load signals");
    }
  }, [isError, error]);

  const total = data?.total ?? 0;
  const maxPage = Math.max(1, Math.ceil(total / pageSize));
  const showingFrom = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const showingTo = Math.min(page * pageSize, total);

  // Selection (per page and across all results)
  const items = React.useMemo(() => data?.items ?? [], [data]);
  const [selected, setSelected] = React.useState<Record<string, boolean>>({});
  const [selectAcrossAll, setSelectAcrossAll] = React.useState(false);
  const [excludedIds, setExcludedIds] = React.useState<Record<string, boolean>>({});

  React.useEffect(() => {
    // clear per-page selection on page data change
    setSelected({});
  }, [items]);

  React.useEffect(() => {
    // clear across-all selection when filters change
    setSelectAcrossAll(false);
    setExcludedIds({});
  }, [debouncedSearch, status, source]);

  const selectedIds = React.useMemo(() => items.filter((x) => selected[x.id]).map((x) => x.id), [items, selected]);
  const selectedCount = React.useMemo(() => {
    if (selectAcrossAll) {
      const excluded = Object.keys(excludedIds).length;
      return Math.max(0, total - excluded);
    }
    return selectedIds.length;
  }, [selectAcrossAll, excludedIds, selectedIds.length, total]);

  const headerCbRef = React.useRef<HTMLInputElement>(null);
  const pageAllIncluded = React.useMemo(() => {
    if (!selectAcrossAll) return items.length > 0 && items.every((x) => selected[x.id]);
    return items.length > 0 && items.every((x) => !excludedIds[x.id]);
  }, [items, selectAcrossAll, selected, excludedIds]);
  const pageSomeIncluded = React.useMemo(() => {
    if (!selectAcrossAll) {
      const some = items.some((x) => selected[x.id]);
      const all = items.length > 0 && items.every((x) => selected[x.id]);
      return some && !all;
    } else {
      const includedCount = items.filter((x) => !excludedIds[x.id]).length;
      return includedCount > 0 && includedCount < items.length;
    }
  }, [items, selectAcrossAll, selected, excludedIds]);
  React.useEffect(() => {
    if (headerCbRef.current) headerCbRef.current.indeterminate = pageSomeIncluded && !pageAllIncluded;
  }, [pageSomeIncluded, pageAllIncluded]);

  const toggleAllOnPage = () => {
    if (!selectAcrossAll) {
      const next: Record<string, boolean> = {};
      if (!pageAllIncluded) {
        for (const it of items) next[it.id] = true;
      }
      setSelected(next);
    } else {
      setExcludedIds((prev) => {
        const next = { ...prev };
        const allIncluded = items.every((it) => !prev[it.id]);
        if (allIncluded) {
          for (const it of items) next[it.id] = true; // exclude page
        } else {
          for (const it of items) delete next[it.id]; // include page
        }
        return next;
      });
    }
  };

  const clearSelection = () => {
    setSelected({});
    setExcludedIds({});
    setSelectAcrossAll(false);
  };

  const selectAllAcrossResults = () => {
    setSelected({});
    setExcludedIds({});
    setSelectAcrossAll(true);
  };
  const selectOnlyThisPage = () => {
    const next: Record<string, boolean> = {};
    for (const it of items) next[it.id] = true;
    setSelected(next);
    setExcludedIds({});
    setSelectAcrossAll(false);
  };

  // Helpers: concurrency runner, enumerate ids across all pages, resolve targets
  async function runWithConcurrency<T>(
    ids: string[],
    concurrency: number,
    worker: (id: string) => Promise<T>,
    opts?: { onTick?: (okInc: number, failInc: number) => void; shouldCancel?: () => boolean }
  ): Promise<{ ok: number; fail: number; cancelled: boolean }> {
    let ok = 0;
    let fail = 0;
    let i = 0;
    let cancelled = false;
    const runners = new Array(Math.min(concurrency, ids.length)).fill(0).map(async () => {
      while (i < ids.length) {
        if (opts?.shouldCancel?.()) {
          cancelled = true;
          break;
        }
        const idx = i++;
        if (idx >= ids.length) break;
        try {
          await worker(ids[idx]);
          ok++;
          opts?.onTick?.(1, 0);
        } catch {
          fail++;
          opts?.onTick?.(0, 1);
        }
      }
    });
    await Promise.all(runners);
    return { ok, fail, cancelled };
  }

  async function fetchAllMatchingIds(): Promise<string[]> {
    const fetchSize = 200;
    const baseParams: SignalsListParams = { pageSize: fetchSize, sort, order, search: debouncedSearch || undefined, status, source };
    const first = await apiListSignals({ ...baseParams, page: 1 });
    const ids: string[] = first.items.map((x) => x.id);
    const totalPages = Math.max(1, Math.ceil((first.total ?? 0) / fetchSize));
    if (totalPages === 1) return ids;
    const pages: number[] = [];
    for (let p = 2; p <= totalPages; p++) pages.push(p);
    await runWithConcurrency(
      pages.map(String),
      4,
      async (pStr) => {
        const p = Number(pStr);
        const res = await apiListSignals({ ...baseParams, page: p });
        ids.push(...res.items.map((x) => x.id));
      }
    );
    return ids;
  }

  async function resolveTargetIds(): Promise<string[]> {
    if (!selectAcrossAll) return selectedIds;
    const all = await fetchAllMatchingIds();
    return all.filter((id) => !excludedIds[id]);
  }

  // Server bulk attempt with SSE preferred, fallback to polling
  async function tryServerBulk(
    label: "resume" | "pause" | "delete",
    start: () => Promise<{ jobId: string; total: number }>
  ): Promise<boolean> {
    function successPast(l: "resume" | "pause" | "delete") {
      switch (l) {
        case "resume":
          return "resumed";
        case "pause":
          return "paused";
        case "delete":
          return "deleted";
      }
    }
    const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
    try {
      const { jobId, total } = await start();
      if (!jobId) return false;
      setServerJobId(jobId);
      setProgress({ total, done: 0, fail: 0 });
      let finalSt: import("../api/bulk").BulkJobStatus | null = null;
      let usedSSE = false;
      const sseSupported = typeof window !== "undefined" && "EventSource" in window;
      if (sseSupported) {
        try {
          const stream = openBulkJobStream(jobId, (st) => {
            finalSt = st;
            setProgress({ total: st.total, done: st.done, fail: st.fail });
          });
          const connected = await Promise.race([stream.connected, sleep(1000).then(() => false)]);
          if (connected) {
            usedSSE = true;
            await stream.wait;
          } else {
            stream.close();
          }
        } catch {
          // ignore and fallback to polling
        }
      }
      if (!usedSSE) {
        let st: import("../api/bulk").BulkJobStatus;
        do {
          st = await getBulkJob(jobId);
          finalSt = st;
          setProgress({ total: st.total, done: st.done, fail: st.fail });
          if (st.status === "running") {
            await sleep(700);
          }
        } while (st.status === "running");
      }
      if (finalSt) {
        if (finalSt.status === "cancelled") {
          toast.message(`Cancelled ${label} operation (${finalSt.done + finalSt.fail}/${finalSt.total} processed)`);
        } else {
          const past = successPast(label);
          if (finalSt.done) toast.success(`${past.charAt(0).toUpperCase() + past.slice(1)} ${finalSt.done} signal${finalSt.done === 1 ? "" : "s"}`);
          if (finalSt.fail) toast.error(`Failed to ${label} ${finalSt.fail} signal${finalSt.fail === 1 ? "" : "s"}`);
        }
      }
      return true;
    } catch (_e) {
      return false;
    } finally {
      setServerJobId(null);
    }
  }

  async function bulkSetStatus(next: SignalStatus) {
    const label = next === "active" ? "resume" : "pause";
    const targets = selectAcrossAll ? await resolveTargetIds() : selectedIds;
    if (targets.length === 0) return;
    setBulkLoading(label);
    setProgress({ total: targets.length, done: 0, fail: 0 });
    cancelRef.current = false;
    // Try server bulk first
    const serverScope = selectAcrossAll
      ? { filters: { search: debouncedSearch || undefined, status, source } }
      : { ids: targets };
    const usedServer = await tryServerBulk(label as any, () => startBulkSetSignalStatus(serverScope as any, next));
    if (!usedServer) {
      try {
        const { ok, fail, cancelled } = await runWithConcurrency(
          targets,
          8,
          (id) => apiSetSignalStatus(id, next),
          {
            onTick: (okInc, failInc) =>
              setProgress((prev) => (prev ? { ...prev, done: prev.done + okInc, fail: prev.fail + failInc } : prev)),
            shouldCancel: () => cancelRef.current
          }
        );
        if (cancelled) {
          toast.message(`Cancelled ${label} operation (${ok + fail}/${targets.length} processed)`);
        } else {
          if (ok) toast.success(`Successfully ${label}d ${ok} signal${ok === 1 ? "" : "s"}`);
          if (fail) toast.error(`Failed to ${label} ${fail} signal${fail === 1 ? "" : "s"}`);
        }
      } finally {
        await queryClient.invalidateQueries({ queryKey: ["signals"] });
        await queryClient.invalidateQueries({ queryKey: ["signals", "stats"] });
      }
    } else {
      await queryClient.invalidateQueries({ queryKey: ["signals"] });
      await queryClient.invalidateQueries({ queryKey: ["signals", "stats"] });
    }
    // Reset UI
    setSelected({});
    setExcludedIds({});
    setSelectAcrossAll(false);
    setBulkLoading(null);
    setProgress(null);
    cancelRef.current = false;
  }

  async function bulkDelete() {
    const targets = await resolveTargetIds();
    if (targets.length === 0) return;
    if (!window.confirm(`Delete ${targets.length} selected signal${targets.length === 1 ? "" : "s"}? This cannot be undone.`)) return;
    setBulkLoading("delete");
    setProgress({ total: targets.length, done: 0, fail: 0 });
    cancelRef.current = false;
    const serverScope = selectAcrossAll
      ? { filters: { search: debouncedSearch || undefined, status, source } }
      : { ids: targets };
    const usedServer = await tryServerBulk("delete", () => startBulkDeleteSignals(serverScope as any));
    if (!usedServer) {
      try {
        const { ok, fail, cancelled } = await runWithConcurrency(
          targets,
          8,
          (id) => apiDeleteSignal(id),
          {
            onTick: (okInc, failInc) =>
              setProgress((prev) => (prev ? { ...prev, done: prev.done + okInc, fail: prev.fail + failInc } : prev)),
            shouldCancel: () => cancelRef.current
          }
        );
        if (cancelled) {
          toast.message(`Cancelled delete operation (${ok + fail}/${targets.length} processed)`);
        } else {
          if (ok) toast.success(`Deleted ${ok} signal${ok === 1 ? "" : "s"}`);
          if (fail) toast.error(`Failed to delete ${fail} signal${fail === 1 ? "" : "s"}`);
        }
      } finally {
        await queryClient.invalidateQueries({ queryKey: ["signals"] });
        await queryClient.invalidateQueries({ queryKey: ["signals", "stats"] });
      }
    } else {
      await queryClient.invalidateQueries({ queryKey: ["signals"] });
      await queryClient.invalidateQueries({ queryKey: ["signals", "stats"] });
    }
    setSelected({});
    setExcludedIds({});
    setSelectAcrossAll(false);
    setBulkLoading(null);
    setProgress(null);
    cancelRef.current = false;
  }

  function handleToggleStatus(id: string, current: SignalStatus, name: string) {
    const next: SignalStatus = current === "active" ? "paused" : "active";
    setPendingId(id);
    updateStatus.mutate(
      { id, status: next },
      {
        onSuccess: () => {
          toast.success(`${next === "active" ? "Resumed" : "Paused"} ${name}`);
        },
        onError: () => {
          toast.error("Failed to update status");
        },
        onSettled: () => setPendingId(null)
      }
    );
  }

  async function handleDelete(id: string, name: string) {
    const ok = await confirm({
      title: `Delete ${name}?`,
      description: "This action cannot be undone.",
      confirmText: "Delete",
      tone: "destructive",
    });
    if (!ok) return;
    setPendingId(id);
    try {
      await deleteMutation.mutateAsync(id);
      toast.success("Signal deleted");
    } catch {
      toast.error("Failed to delete");
    } finally {
      setPendingId(null);
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2 flex-wrap">
          <Input
            placeholder="Search signals..."
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
            <option value="active">active</option>
            <option value="paused">paused</option>
            <option value="error">error</option>
            <option value="inactive">inactive</option>
          </select>
          <select
            className="h-10 rounded-md border bg-background px-2 text-sm capitalize"
            value={source ?? ""}
            onChange={(e) => setSource((e.target.value || undefined) as any)}
            aria-label="Source"
          >
            <option value="">All sources</option>
            <option value="webhook">webhook</option>
            <option value="poller">poller</option>
            <option value="kafka">kafka</option>
            <option value="sqs">sqs</option>
            <option value="cron">cron</option>
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
            <option value="updatedAt:desc">Recently updated</option>
            <option value="updatedAt:asc">Oldest updated</option>
            <option value="name:asc">Name A–Z</option>
            <option value="name:desc">Name Z–A</option>
            <option value="status:asc">Status A–Z</option>
            <option value="status:desc">Status Z–A</option>
            <option value="createdAt:desc">Newest</option>
            <option value="createdAt:asc">Oldest</option>
            <option value="lastSeenAt:desc">Last seen (recent)</option>
            <option value="lastSeenAt:asc">Last seen (oldest)</option>
          </select>
        </div>

        <div className="flex items-center gap-2">
          <div className="text-sm text-muted-foreground">
            {isLoading ? "Loading…" : `Showing ${showingFrom}-${showingTo} of ${total}`}
          </div>
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

      {selectedCount > 0 || selectAcrossAll ? (
        <div className="flex flex-wrap items-center gap-2 rounded-md border bg-muted/40 px-3 py-2">
          <div className="text-sm">
            {selectAcrossAll ? (
              <>Selected {selectedCount} across all results{Object.keys(excludedIds).length ? ` (excluding ${Object.keys(excludedIds).length})` : ""}</>
            ) : (
              <>{selectedCount} selected</>
            )}
          </div>
          {!selectAcrossAll && pageAllIncluded && total > items.length ? (
            <>
              <div className="h-4 w-px bg-border" />
              <Button variant="outline" size="sm" onClick={selectAllAcrossResults} disabled={bulkLoading !== null}>
                Select all {total} results
              </Button>
            </>
          ) : null}
          {selectAcrossAll ? (
            <>
              <div className="h-4 w-px bg-border" />
              <Button variant="outline" size="sm" onClick={selectOnlyThisPage} disabled={bulkLoading !== null}>
                Select only this page
              </Button>
            </>
          ) : null}
          <div className="h-4 w-px bg-border" />
          <Button variant="outline" size="sm" onClick={() => bulkSetStatus("active")} disabled={bulkLoading !== null}>
            {bulkLoading === "resume" ? "Resuming…" : "Resume"}
          </Button>
          <Button variant="outline" size="sm" onClick={() => bulkSetStatus("paused")} disabled={bulkLoading !== null}>
            {bulkLoading === "pause" ? "Pausing…" : "Pause"}
          </Button>
          <Button variant="destructive" size="sm" onClick={bulkDelete} disabled={bulkLoading !== null}>
            {bulkLoading === "delete" ? "Deleting…" : "Delete"}
          </Button>
          {bulkLoading !== null && progress ? (
            <>
              <div className="h-4 w-px bg-border" />
              <div className="text-xs text-muted-foreground">
                Processing {progress.done + progress.fail} / {progress.total}
                {progress.fail ? ` (${progress.fail} failed)` : ""}
                {serverJobId ? ` — Job ${serverJobId}` : ""}
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  if (serverJobId) {
                    cancelBulkJob(serverJobId).catch(() => {});
                  }
                  cancelRef.current = true;
                }}
              >
                Cancel
              </Button>
            </>
          ) : null}
          <div className="ml-auto">
            <Button variant="outline" size="sm" onClick={clearSelection} disabled={bulkLoading !== null}>
              Clear selection
            </Button>
          </div>
        </div>
      ) : null}

      <div className="overflow-hidden rounded-md border">
        <table className="w-full caption-bottom text-sm">
          <thead className="bg-muted/50">
            <tr className="border-b">
              <Th className="w-10">
                <input
                  ref={headerCbRef}
                  type="checkbox"
                  className="h-4 w-4"
                  checked={pageAllIncluded}
                  onChange={toggleAllOnPage}
                  aria-label="Select all on page"
                />
              </Th>
              <Th>Name</Th>
              <Th>Source</Th>
              <Th>Status</Th>
              <Th>Last seen</Th>
              <Th>Updated</Th>
              <Th>Actions</Th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <RowsSkeleton />
            ) : data && data.items.length > 0 ? (
              data.items.map((s) => (
                <tr key={s.id} className="border-b last:border-0">
                  <Td className="w-10">
                    <input
                      type="checkbox"
                      className="h-4 w-4"
                      checked={selectAcrossAll ? !excludedIds[s.id] : !!selected[s.id]}
                      onChange={(e) => {
                        const v = e.target.checked;
                        if (!selectAcrossAll) {
                          setSelected((prev) => ({ ...prev, [s.id]: v }));
                        } else {
                          setExcludedIds((prev) => {
                            const next = { ...prev };
                            if (v) delete next[s.id]; else next[s.id] = true;
                            return next;
                          });
                        }
                      }}
                      aria-label={`Select ${s.name}`}
                    />
                  </Td>
                  <Td>
                    <div className="font-medium">{s.name}</div>
                    <div className="text-xs text-muted-foreground">{s.id}</div>
                  </Td>
                  <Td className="capitalize">{s.source}</Td>
                  <Td>
                    <StatusBadge status={s.status} />
                  </Td>
                  <Td>{s.lastSeenAt ? timeAgo(s.lastSeenAt) : "—"}</Td>
                  <Td>{timeAgo(s.updatedAt)}</Td>
                  <Td>
                    <div className="flex items-center gap-2">
                      <Dropdown
                        trigger={
                          <Button variant="outline" size="sm" aria-label={`More actions for ${s.name}`}>
                            ⋯
                          </Button>
                        }
                        align="end"
                      >
                        <DropdownItem onSelect={() => navigate(`/signals/${s.id}/edit`)}>Edit</DropdownItem>
                        <DropdownItem
                          onSelect={() => handleToggleStatus(s.id, s.status, s.name)}
                          disabled={pendingId === s.id || isFetching}
                        >
                          {s.status === "active" ? "Pause" : "Resume"}
                        </DropdownItem>
                        <DropdownSeparator />
                        <DropdownItem
                          onSelect={() => handleDelete(s.id, s.name)}
                          disabled={pendingId === s.id || isFetching}
                          variant="destructive"
                        >
                          Delete
                        </DropdownItem>
                      </Dropdown>
                    </div>
                  </Td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={7} className="p-6">
                  {debouncedSearch ? (
                    <EmptySearch query={debouncedSearch} />
                  ) : (
                    <EmptySignals />
                  )}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {isFetching && !isLoading ? (
        <div className="text-xs text-muted-foreground">Refreshing…</div>
      ) : null}
      {Confirm}
    </div>
  );
}

function Th({ children, className }: { children: React.ReactNode; className?: string }) {
  return <th className={cn("px-4 py-3 text-left align-middle font-medium", className)}>{children}</th>;
}

function Td({ children, className }: { children: React.ReactNode; className?: string }) {
  return <td className={cn("px-4 py-3 align-middle", className)}>{children}</td>;
}

function RowsSkeleton() {
  return (
    <>
      {Array.from({ length: 8 }).map((_, i) => (
        <tr key={i} className="border-b last:border-0">
          <Td className="w-10">
            <div className="h-4 w-4 rounded bg-muted animate-pulse" />
          </Td>
          <Td>
            <div className="h-4 w-40 rounded bg-muted animate-pulse" />
            <div className="mt-2 h-3 w-28 rounded bg-muted animate-pulse" />
          </Td>
          <Td>
            <div className="h-4 w-20 rounded bg-muted animate-pulse" />
          </Td>
          <Td>
            <div className="h-5 w-16 rounded bg-muted animate-pulse" />
          </Td>
          <Td>
            <div className="h-4 w-24 rounded bg-muted animate-pulse" />
          </Td>
          <Td>
            <div className="h-4 w-28 rounded bg-muted animate-pulse" />
          </Td>
          <Td>
            <div className="h-8 w-20 rounded bg-muted animate-pulse" />
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
