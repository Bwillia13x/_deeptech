import React from "react";
import { Button } from "./ui/button";
import { cn } from "../lib/utils";

export type ConfirmOptions = {
  title?: string;
  description?: React.ReactNode;
  confirmText?: string;
  cancelText?: string;
  tone?: "default" | "destructive";
};

type InternalState = ConfirmOptions & {
  open: boolean;
  resolve?: (v: boolean) => void;
};

export function useConfirm(defaults?: ConfirmOptions) {
  const [state, setState] = React.useState<InternalState>({
    open: false,
    title: defaults?.title,
    description: defaults?.description,
    confirmText: defaults?.confirmText ?? "Confirm",
    cancelText: defaults?.cancelText ?? "Cancel",
    tone: defaults?.tone ?? "default"
  });

  const confirm = React.useCallback((opts?: ConfirmOptions) => {
    return new Promise<boolean>((resolve) => {
      setState({
        open: true,
        title: opts?.title ?? defaults?.title ?? "Are you sure?",
        description: opts?.description ?? defaults?.description ?? "",
        confirmText: opts?.confirmText ?? defaults?.confirmText ?? "Confirm",
        cancelText: opts?.cancelText ?? defaults?.cancelText ?? "Cancel",
        tone: opts?.tone ?? defaults?.tone ?? "default",
        resolve
      });
    });
  }, [defaults]);

  const onCancel = React.useCallback(() => {
    const r = state.resolve;
    setState((s) => ({ ...s, open: false, resolve: undefined }));
    r?.(false);
  }, [state.resolve]);

  const onConfirm = React.useCallback(() => {
    const r = state.resolve;
    setState((s) => ({ ...s, open: false, resolve: undefined }));
    r?.(true);
  }, [state.resolve]);

  const Dialog = (
    <ConfirmDialog
      open={state.open}
      title={state.title}
      description={state.description}
      confirmText={state.confirmText}
      cancelText={state.cancelText}
      tone={state.tone}
      onCancel={onCancel}
      onConfirm={onConfirm}
    />
  );

  return { confirm, Confirm: Dialog };
}

export function ConfirmDialog({
  open,
  title = "Are you sure?",
  description,
  confirmText = "Confirm",
  cancelText = "Cancel",
  tone = "default",
  onCancel,
  onConfirm
}: {
  open: boolean;
  title?: string;
  description?: React.ReactNode;
  confirmText?: string;
  cancelText?: string;
  tone?: "default" | "destructive";
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const titleId = React.useId();
  const descId = React.useId();
  React.useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onCancel();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onCancel]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-background/80" onClick={onCancel} />
      <div
        className="relative z-10 w-full max-w-sm rounded-md border bg-popover p-4 text-popover-foreground shadow-lg"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descId : undefined}
      >
        <div className="space-y-2">
          <div id={titleId} className="text-base font-semibold">{title}</div>
          {description ? (
            <div id={descId} className="text-sm text-muted-foreground">{description}</div>
          ) : null}
        </div>
        <div className="mt-4 flex items-center justify-end gap-2">
          <Button variant="outline" onClick={onCancel}>{cancelText}</Button>
          <Button
            onClick={onConfirm}
            className={cn(tone === "destructive" ? "bg-destructive text-destructive-foreground hover:bg-destructive/90" : "")}
            autoFocus
          >
            {confirmText}
          </Button>
        </div>
      </div>
    </div>
  );
}
