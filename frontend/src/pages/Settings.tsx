import React from "react";
import { ModeToggle } from "../components/theme/mode-toggle";
import { OnboardingTrigger } from "../components/Onboarding";

export default function Settings() {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Settings</h1>
        <p className="text-muted-foreground">
          Configure preferences and integrations.
        </p>
      </div>

      <div className="rounded-lg border p-6 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <div className="font-medium">Theme</div>
            <div className="text-sm text-muted-foreground">
              Choose light, dark, or system theme.
            </div>
          </div>
          <ModeToggle />
        </div>
      </div>

      <div className="rounded-lg border p-6 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <div className="font-medium">Onboarding</div>
            <div className="text-sm text-muted-foreground">
              Take the tour again to learn about features.
            </div>
          </div>
          <OnboardingTrigger />
        </div>
      </div>
    </div>
  );
}
