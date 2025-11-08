import React from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";
import { useCreateSignalMutation, useSignalQuery, useUpdateSignalMutation } from "../hooks/useSignals";
import type { CreateSignalInput, SignalStatus } from "../types/api";
import { toast } from "sonner";

const SOURCES = ["webhook", "poller", "kafka", "sqs", "cron"];
const STATUSES: SignalStatus[] = ["inactive", "active", "paused", "error"];

export default function SignalForm() {
  const { id } = useParams<{ id: string }>();
  const isEdit = Boolean(id);
  const navigate = useNavigate();

  const { data: existing, isLoading: loadingExisting } = useSignalQuery(id);
  const { mutateAsync: create, isPending: creating } = useCreateSignalMutation();
  const { mutateAsync: update, isPending: updating } = useUpdateSignalMutation();

  const [name, setName] = React.useState("");
  const [source, setSource] = React.useState(SOURCES[0]);
  const [status, setStatus] = React.useState<SignalStatus>("inactive");
  const [tags, setTags] = React.useState<string>("");

  React.useEffect(() => {
    if (existing) {
      setName(existing.name);
      setSource(existing.source);
      setStatus(existing.status);
      setTags(existing.tags?.join(", ") ?? "");
    }
  }, [existing]);

  const loading = isEdit ? loadingExisting || updating : creating;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const input: CreateSignalInput = {
      name: name.trim(),
      source,
      tags: tags
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean),
      status
    };
    try {
      if (isEdit && id) {
        await update({ id, input });
        toast.success("Signal updated");
      } else {
        await create(input);
        toast.success("Signal created");
      }
      navigate("/signals");
    } catch (err: any) {
      toast.error(err?.message || "Failed to save signal");
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">{isEdit ? "Edit Signal" : "New Signal"}</h1>
        <p className="text-muted-foreground">
          {isEdit ? "Update signal configuration." : "Create a new signal to start ingesting data."}
        </p>
      </div>

      <form onSubmit={onSubmit} className="max-w-xl space-y-4">
        <div className="space-y-2">
          <label className="text-sm font-medium">Name</label>
          <Input
            required
            placeholder="e.g. Order Created"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium">Source</label>
          <select
            className="h-10 w-full rounded-md border bg-background px-3 text-sm"
            value={source}
            onChange={(e) => setSource(e.target.value)}
            aria-label="Source"
          >
            {SOURCES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium">Status</label>
          <select
            className="h-10 w-full rounded-md border bg-background px-3 text-sm"
            value={status}
            onChange={(e) => setStatus(e.target.value as SignalStatus)}
            aria-label="Status"
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium">Tags (comma separated)</label>
          <Input
            placeholder="prod, payments"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
          />
        </div>

        <div className="flex items-center gap-2 pt-2">
          <Button type="submit" disabled={loading}>
            {loading ? "Saving..." : "Save"}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => navigate("/signals")}
            disabled={loading}
          >
            Cancel
          </Button>
        </div>
      </form>
    </div>
  );
}
