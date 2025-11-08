import React from "react";
import { Badge } from "./ui/badge";
import type { SignalStatus } from "../types/api";

export function StatusBadge({ status }: { status: SignalStatus }) {
  const map: Record<SignalStatus, { label: string; variant: any }> = {
    active: { label: "Active", variant: "success" },
    paused: { label: "Paused", variant: "warning" },
    error: { label: "Error", variant: "destructive" },
    inactive: { label: "Inactive", variant: "muted" }
  };
  const { label, variant } = map[status];
  return <Badge variant={variant}>{label}</Badge>;
}
