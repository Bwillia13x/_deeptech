import React from "react";
import { Toaster } from "sonner";
import { useTheme } from "./theme/theme-provider";

export function AppToaster() {
  const { theme } = useTheme();
  return (
    <Toaster
      position="top-right"
      richColors
      theme={theme}
      closeButton
      toastOptions={{ classNames: { toast: "shadow" } }}
    />
  );
}
