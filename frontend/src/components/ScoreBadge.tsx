import React from "react";
import { Badge } from "./ui/badge";
import { cn } from "../lib/utils";

interface ScoreBadgeProps {
  score: number;
  size?: "sm" | "md" | "lg";
  showLabel?: boolean;
}

export function ScoreBadge({ score, size = "md", showLabel = false }: ScoreBadgeProps) {
  const getScoreColor = (score: number) => {
    if (score >= 85) return "bg-green-500";
    if (score >= 70) return "bg-yellow-500";
    if (score >= 50) return "bg-orange-500";
    return "bg-gray-500";
  };

  const getScoreTextColor = (score: number) => {
    if (score >= 85) return "text-green-700";
    if (score >= 70) return "text-yellow-700";
    if (score >= 50) return "text-orange-700";
    return "text-gray-700";
  };

  const sizeClasses = {
    sm: "text-xs px-2 py-0.5",
    md: "text-sm px-2.5 py-1",
    lg: "text-base px-3 py-1.5",
  };

  return (
    <Badge
      variant="secondary"
      className={cn(
        "font-bold",
        sizeClasses[size],
        getScoreTextColor(score),
        "bg-opacity-10"
      )}
      style={{
        borderColor: getScoreColor(score),
        backgroundColor: `${getScoreColor(score)}20`,
      }}
    >
      {showLabel ? "Score: " : ""}
      {score.toFixed(1)}
    </Badge>
  );
}

// Sparkline component for trend visualization
interface ScoreSparklineProps {
  scores: number[];
  className?: string;
}

export function ScoreSparkline({ scores, className }: ScoreSparklineProps) {
  const maxScore = Math.max(...scores);
  const minScore = Math.min(...scores);
  const range = maxScore - minScore || 1;

  // Create SVG path for sparkline
  const points = scores.map((score, i) => {
    const x = (i / (scores.length - 1)) * 100;
    const y = 100 - ((score - minScore) / range) * 100;
    return `${x},${y}`;
  });

  const pathData = `M ${points.join(" L ")}`;

  return (
    <svg viewBox="0 0 100 20" className={cn("w-full h-8", className)}>
      <path
        d={pathData}
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="text-primary"
      />
    </svg>
  );
}