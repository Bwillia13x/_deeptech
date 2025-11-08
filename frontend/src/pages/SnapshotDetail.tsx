import React from "react";
import { useParams, Link } from "react-router-dom";
import { useSnapshotQuery } from "../hooks/useSnapshots";
import { Button } from "../components/ui/button";

export default function SnapshotDetail() {
  const { id } = useParams<{ id: string }>();
  const { data, isLoading } = useSnapshotQuery(id);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Snapshot {id}</h1>
          <p className="text-muted-foreground">Inspect snapshot metadata.</p>
        </div>
        <Link to="/snapshots">
          <Button variant="outline">Back</Button>
        </Link>
      </div>

      {isLoading ? (
        <div className="rounded-lg border p-6">Loading…</div>
      ) : data ? (
        <div className="rounded-lg border p-6 space-y-4">
          <div className="grid gap-2 sm:grid-cols-2">
            <Field label="ID" value={data.id} mono />
            <Field label="Signal ID" value={data.signalId} mono />
            <Field label="Signal Name" value={data.signalName ?? "—"} />
            <Field label="Status" value={data.status} />
            <Field label="Size" value={data.sizeKb ? `${data.sizeKb} KB` : "—"} />
            <Field label="Created At" value={new Date(data.createdAt).toLocaleString()} />
          </div>

          <div>
            <div className="text-sm font-medium mb-2">Raw JSON</div>
            <pre className="max-h-[400px] overflow-auto rounded-md bg-muted p-4 text-xs">
              {JSON.stringify(data, null, 2)}
            </pre>
          </div>
        </div>
      ) : (
        <div className="rounded-lg border p-6">Snapshot not found.</div>
      )}
    </div>
  );
}

function Field({ label, value, mono }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={mono ? "font-mono text-sm" : "font-medium"}>{value}</div>
    </div>
  );
}
