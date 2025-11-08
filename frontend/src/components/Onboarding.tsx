import React, { useState } from "react";
import { Button } from "./ui/button";
import { cn } from "../lib/utils";

interface OnboardingStep {
  id: string;
  title: string;
  description: string;
  target?: string; // CSS selector for element to highlight
  position?: "top" | "bottom" | "left" | "right" | "center";
}

const ONBOARDING_STEPS: OnboardingStep[] = [
  {
    id: "welcome",
    title: "Welcome to Signal Harvester! 🎉",
    description: "Let's take a quick tour to help you get started with monitoring social signals from X (Twitter).",
    position: "center",
  },
  {
    id: "dashboard",
    title: "Dashboard Overview",
    description: "Your dashboard shows key metrics at a glance, including total signals, active monitors, and recent activity.",
    target: "[href='/dashboard']",
    position: "right",
  },
  {
    id: "signals",
    title: "Signals Management",
    description: "View and manage all your harvested signals here. You can search, filter, and take bulk actions on signals.",
    target: "[href='/signals']",
    position: "right",
  },
  {
    id: "snapshots",
    title: "Snapshots & Backups",
    description: "Create snapshots to backup your signals at any point in time. Useful for historical analysis and recovery.",
    target: "[href='/snapshots']",
    position: "right",
  },
  {
    id: "settings",
    title: "Configuration",
    description: "Configure your X/Twitter API credentials, LLM settings, and notification preferences in Settings.",
    target: "[href='/settings']",
    position: "right",
  },
  {
    id: "complete",
    title: "You're All Set! 🚀",
    description: "You've completed the tour! Start by creating your first signal or running the pipeline to fetch data.",
    position: "center",
  },
];

interface OnboardingProps {
  onComplete: () => void;
  onSkip: () => void;
}

export default function Onboarding({ onComplete, onSkip }: OnboardingProps) {
  const [currentStep, setCurrentStep] = useState(0);
  const [highlightedElement, setHighlightedElement] = useState<HTMLElement | null>(null);

  const step = ONBOARDING_STEPS[currentStep];

  React.useEffect(() => {
    // Highlight target element if specified
    if (step.target) {
      const element = document.querySelector(step.target) as HTMLElement;
      setHighlightedElement(element);
      
      if (element) {
        element.style.outline = "2px solid #3b82f6";
        element.style.outlineOffset = "2px";
        element.style.borderRadius = "4px";
      }
    } else {
      setHighlightedElement(null);
    }

    // Cleanup on unmount or step change
    return () => {
      if (highlightedElement) {
        highlightedElement.style.outline = "";
        highlightedElement.style.outlineOffset = "";
        highlightedElement.style.borderRadius = "";
      }
    };
  }, [step.target, highlightedElement]);

  const handleNext = () => {
    if (currentStep < ONBOARDING_STEPS.length - 1) {
      setCurrentStep(currentStep + 1);
    } else {
      onComplete();
    }
  };

  const handlePrevious = () => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1);
    }
  };

  const handleSkip = () => {
    if (highlightedElement) {
      highlightedElement.style.outline = "";
      highlightedElement.style.outlineOffset = "";
      highlightedElement.style.borderRadius = "";
    }
    onSkip();
  };

  const progress = ((currentStep + 1) / ONBOARDING_STEPS.length) * 100;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
      {/* Overlay */}
      <div className="absolute inset-0" onClick={handleSkip} />
      
      {/* Onboarding Card */}
      <div
        className={cn(
          "relative z-10 w-full max-w-md rounded-lg border bg-background p-6 shadow-lg",
          step.position === "center" && "mx-4"
        )}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Progress Bar */}
        <div className="mb-6">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-muted-foreground">Step {currentStep + 1} of {ONBOARDING_STEPS.length}</span>
            <button
              onClick={handleSkip}
              className="text-sm text-muted-foreground hover:text-foreground"
            >
              Skip tour
            </button>
          </div>
          <div className="h-2 w-full rounded-full bg-muted">
            <div
              className="h-2 rounded-full bg-primary transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>

        {/* Content */}
        <div className="mb-6">
          <h2 className="text-xl font-semibold mb-3">{step.title}</h2>
          <p className="text-muted-foreground">{step.description}</p>
        </div>

        {/* Navigation */}
        <div className="flex items-center justify-between">
          <Button
            variant="outline"
            onClick={handlePrevious}
            disabled={currentStep === 0}
          >
            Previous
          </Button>

          <div className="flex items-center gap-2">
            {ONBOARDING_STEPS.map((_, index) => (
              <div
                key={index}
                className={cn(
                  "h-2 w-2 rounded-full",
                  index === currentStep ? "bg-primary" : "bg-muted-foreground/30"
                )}
              />
            ))}
          </div>

          <Button onClick={handleNext}>
            {currentStep === ONBOARDING_STEPS.length - 1 ? "Get Started" : "Next"}
          </Button>
        </div>
      </div>
    </div>
  );
}

// Hook to manage onboarding state
export function useOnboarding() {
  const [showOnboarding, setShowOnboarding] = useState(() => {
    // Check if user has already seen onboarding
    const hasSeenOnboarding = localStorage.getItem("hasSeenOnboarding");
    return hasSeenOnboarding !== "true";
  });

  const handleComplete = () => {
    localStorage.setItem("hasSeenOnboarding", "true");
    setShowOnboarding(false);
  };

  const handleSkip = () => {
    localStorage.setItem("hasSeenOnboarding", "true");
    setShowOnboarding(false);
  };

  const resetOnboarding = () => {
    localStorage.removeItem("hasSeenOnboarding");
    setShowOnboarding(true);
  };

  return {
    showOnboarding,
    handleComplete,
    handleSkip,
    resetOnboarding,
  };
}

// Onboarding trigger button (for settings or help menu)
export function OnboardingTrigger() {
  const { resetOnboarding } = useOnboarding();

  return (
    <button
      onClick={resetOnboarding}
      className="px-3 py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-muted rounded-md transition-colors"
    >
      Show Tour
    </button>
  );
}