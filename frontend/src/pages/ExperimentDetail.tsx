import React, { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useExperimentDetail, useRunExperiment } from "../hooks/useExperiments";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Skeleton } from "../components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import {
  BarChart3,
  Play,
  Trophy,
  Clock,
  CheckCircle,
  Activity,
  Target,
  Zap,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
} from "lucide-react";
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from "recharts";
import { PieChart, Pie, Cell } from "recharts";
import { useToast } from "../components/ui/use-toast";
import { DataTable } from "../components/ui/data-table";
import { ColumnDef } from "@tanstack/react-table";
import { ExperimentRun, ExperimentStatus } from "../types/api";

// Colors for pie chart
const COLORS = {
  truePositive: "#10b981", // green
  falsePositive: "#ef4444", // red
  trueNegative: "#3b82f6", // blue
  falseNegative: "#f59e0b", // amber
};

// Status colors - must match ExperimentStatus type
const statusColors: Record<ExperimentStatus, string> = {
  draft: "bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200",
  running: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
  completed: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  failed: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
};

export default function ExperimentDetailPage() {
  const { experimentId } = useParams<{ experimentId: string }>();
  const [comparisonExperimentId, setComparisonExperimentId] = useState<string>("");
  const { toast } = useToast();

  // Fetch experiment detail - MUST come before any conditional returns
  const {
    data: experimentData,
    isLoading: detailLoading,
    isError: detailError,
    refetch,
  } = useExperimentDetail({ experimentId });

  // Run experiment mutation - MUST come before any conditional returns
  const runExperimentMutation = useRunExperiment();

  if (!experimentId) {
    return <div className="text-red-500">Experiment ID is required</div>;
  }

  // Handle run experiment
  const handleRunExperiment = async () => {
    try {
      await runExperimentMutation.mutateAsync(experimentId);
      toast({
        title: "Experiment Started",
        description: "Your experiment is now running.",
      });
      refetch();
    } catch (error) {
      toast({
        title: "Failed to Start",
        description: error instanceof Error ? error.message : "Unknown error",
        variant: "destructive",
      });
    }
  };

  if (detailError) {
    return (
      <div className="text-red-500">
        Error loading experiment: {JSON.stringify(detailError)}
      </div>
    );
  }

  if (detailLoading || !experimentData) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <Card>
          <CardHeader>
            <Skeleton className="h-6 w-32" />
          </CardHeader>
          <CardContent>
            <Skeleton className="h-[600px] w-full" />
          </CardContent>
        </Card>
      </div>
    );
  }

  const { experiment, runs, bestRun, metricsOverTime, confusionMatrix } = experimentData;

  // Define columns for runs table
  const runColumns: ColumnDef<ExperimentRun>[] = [
    {
      accessorKey: "id",
      header: "Run ID",
      cell: ({ row }) => <div className="font-mono text-sm">{row.original.id}</div>,
    },
    {
      accessorKey: "status",
      header: "Status",
      cell: ({ row }) => (
        <Badge
          variant={
            row.original.status === "completed" ? "default" : "destructive"
          }
        >
          {row.original.status}
        </Badge>
      ),
    },
    {
      accessorKey: "artifactCount",
      header: "Artifacts",
      cell: ({ row }) => (
        <div className="font-medium">{row.original.artifactCount}</div>
      ),
    },
    {
      accessorKey: "precision",
      header: "Precision",
      cell: ({ row }) => (
        <div className="font-medium">
          {(row.original.precision * 100).toFixed(1)}%
        </div>
      ),
    },
    {
      accessorKey: "recall",
      header: "Recall",
      cell: ({ row }) => (
        <div className="font-medium">
          {(row.original.recall * 100).toFixed(1)}%
        </div>
      ),
    },
    {
      accessorKey: "f1Score",
      header: "F1 Score",
      cell: ({ row }) => (
        <div className="font-bold text-primary">
          {(row.original.f1Score * 100).toFixed(1)}%
        </div>
      ),
    },
    {
      accessorKey: "accuracy",
      header: "Accuracy",
      cell: ({ row }) => (
        <div className="font-medium">
          {(row.original.accuracy * 100).toFixed(1)}%
        </div>
      ),
    },
    {
      accessorKey: "completedAt",
      header: "Completed",
      cell: ({ row }) => (
        <div className="text-sm text-muted-foreground">
          {new Date(row.original.completedAt).toLocaleDateString()}
        </div>
      ),
    },
  ];

  // Prepare data for metrics trend chart
  const trendData = metricsOverTime.dates.map((date, index) => ({
    date: new Date(date).toLocaleDateString(),
    precision: Math.round(metricsOverTime.precision[index] * 100),
    recall: Math.round(metricsOverTime.recall[index] * 100),
    f1Score: Math.round(metricsOverTime.f1Score[index] * 100),
    accuracy: Math.round(metricsOverTime.accuracy[index] * 100),
  }));

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{experiment.name}</h1>
          <div className="flex items-center gap-3 mt-2">
            <Badge className={statusColors[experiment.status]}>
              {experiment.status}
            </Badge>
            {experiment.baselineId && (
              <Link to={`/experiments/${experiment.baselineId}`}>
                <Badge variant="outline">Baseline: {experiment.baselineId}</Badge>
              </Link>
            )}
          </div>
          {experiment.description && (
            <p className="mt-2 text-muted-foreground">{experiment.description}</p>
          )}
        </div>
        <div className="flex items-center gap-3">
          <Button
            onClick={handleRunExperiment}
            disabled={runExperimentMutation.isPending}
            variant="outline"
          >
            <Play
              className={`h-4 w-4 mr-2 ${
                runExperimentMutation.isPending ? "animate-pulse" : ""
              }`}
            />
            {runExperimentMutation.isPending ? "Running..." : "Run Experiment"}
          </Button>
          <Link to={`/experiments/${experiment.id}/compare`}>
            <Button>Compare</Button>
          </Link>
        </div>
      </header>

      {/* Metrics Overview */}
      {bestRun && (
        <section className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <MetricCard
            icon={Target}
            label="Precision"
            value={bestRun.precision}
            format="percent"
            color="text-blue-500"
          />
          <MetricCard
            icon={Activity}
            label="Recall"
            value={bestRun.recall}
            format="percent"
            color="text-green-500"
          />
          <MetricCard
            icon={Trophy}
            label="F1 Score"
            value={bestRun.f1Score}
            format="percent"
            color="text-yellow-500"
          />
          <MetricCard
            icon={Zap}
            label="Accuracy"
            value={bestRun.accuracy}
            format="percent"
            color="text-purple-500"
          />
        </section>
      )}

      {/* Main Content Tabs */}
      <Tabs defaultValue="overview" className="space-y-4">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="runs">Runs ({runs.length})</TabsTrigger>
          <TabsTrigger value="comparison">Comparison</TabsTrigger>
          <TabsTrigger value="configuration">Configuration</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <div className="grid gap-6 lg:grid-cols-2">
            {/* Metrics Trend Chart */}
            <Card>
              <CardHeader>
                <CardTitle>Performance Trends</CardTitle>
                <p className="text-sm text-muted-foreground">
                  Metrics over recent runs
                </p>
              </CardHeader>
              <CardContent>
                <div className="h-[300px]">
                  {trendData.length > 0 ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={trendData}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="date" />
                        <YAxis domain={[0, 100]} />
                        <Tooltip />
                        <Legend />
                        <Line
                          type="monotone"
                          dataKey="precision"
                          stroke="#3b82f6"
                          strokeWidth={2}
                          name="Precision"
                        />
                        <Line
                          type="monotone"
                          dataKey="recall"
                          stroke="#10b981"
                          strokeWidth={2}
                          name="Recall"
                        />
                        <Line
                          type="monotone"
                          dataKey="f1Score"
                          stroke="#f59e0b"
                          strokeWidth={3}
                          name="F1 Score"
                        />
                        <Line
                          type="monotone"
                          dataKey="accuracy"
                          stroke="#8b5cf6"
                          strokeWidth={2}
                          name="Accuracy"
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="flex items-center justify-center h-full text-muted-foreground">
                      No run data available
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>

            {/* Confusion Matrix */}
            <Card>
              <CardHeader>
                <CardTitle>Confusion Matrix</CardTitle>
                <p className="text-sm text-muted-foreground">
                  True vs False predictions
                </p>
              </CardHeader>
              <CardContent>
                {confusionMatrix ? (
                  <div className="h-[300px]">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={[
                            { name: "True Positive", value: confusionMatrix.truePositives },
                            { name: "False Positive", value: confusionMatrix.falsePositives },
                            { name: "True Negative", value: confusionMatrix.trueNegatives },
                            { name: "False Negative", value: confusionMatrix.falseNegatives },
                          ]}
                          cx="50%"
                          cy="50%"
                          label={(entry) => `${entry.name}: ${entry.value}`}
                          labelLine={false}
                          outerRadius={80}
                          fill="#8884d8"
                          dataKey="value"
                        >
                          <Cell fill={COLORS.truePositive} />
                          <Cell fill={COLORS.falsePositive} />
                          <Cell fill={COLORS.trueNegative} />
                          <Cell fill={COLORS.falseNegative} />
                        </Pie>
                        <Tooltip />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <div className="flex items-center justify-center h-full text-muted-foreground">
                    No confusion matrix data
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="runs">
          <Card>
            <CardHeader>
              <CardTitle>Experiment Runs</CardTitle>
              <p className="text-sm text-muted-foreground">
                All execution runs for this experiment
              </p>
            </CardHeader>
            <CardContent>
              {runs.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  No runs yet. Click "Run Experiment" to start.
                </div>
              ) : (
                <DataTable
                  columns={runColumns}
                  data={runs}
                  getRowKey={(run) => run.id}
                />
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="comparison">
          <Card>
            <CardHeader>
              <CardTitle>Experiment Comparison</CardTitle>
              <p className="text-sm text-muted-foreground">
                Compare this experiment with another
              </p>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div className="grid gap-3 md:grid-cols-2">
                  <div className="space-y-2">
                    <label className="text-sm font-medium">Current Experiment</label>
                    <div className="rounded-md border p-3">
                      <div className="font-medium">{experiment.name}</div>
                      <div className="text-sm text-muted-foreground">
                        F1: {(bestRun?.f1Score || 0 * 100).toFixed(1)}%
                      </div>
                    </div>
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-medium">Compare With</label>
                    <select
                      value={comparisonExperimentId}
                      onChange={(e) => setComparisonExperimentId(e.target.value)}
                      className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    >
                      <option value="">Select experiment...</option>
                      {/* In real implementation, this would be populated with other experiments */}
                      {experiment.baselineId && (
                        <option value={experiment.baselineId}>Baseline</option>
                      )}
                    </select>
                  </div>
                </div>
                <Button
                  disabled={!comparisonExperimentId}
                  onClick={() => {
                    // In real implementation, navigate to comparison view
                    toast({
                      title: "Opening Comparison",
                      description: "Navigating to A/B comparison...",
                    });
                  }}
                >
                  Compare
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="configuration">
          <Card>
            <CardHeader>
              <CardTitle>Experiment Configuration</CardTitle>
              <p className="text-sm text-muted-foreground">
                Scoring weights and configuration parameters
              </p>
            </CardHeader>
            <CardContent>
              <div className="grid gap-6 md:grid-cols-2">
                <div>
                  <h4 className="font-medium mb-3">Scoring Weights</h4>
                  <div className="space-y-2">
                    {Object.entries(experiment.config.scoringWeights).map(
                      ([key, value]) => (
                        <div key={key} className="flex justify-between">
                          <span className="text-sm capitalize">{key}</span>
                          <span className="text-sm font-medium">
                            {(value as number * 100).toFixed(0)}%
                          </span>
                        </div>
                      )
                    )}
                  </div>
                </div>
                <div>
                  <h4 className="font-medium mb-3">Parameters</h4>
                  <div className="space-y-2">
                    <div className="flex justify-between">
                      <span className="text-sm">Min Score Threshold</span>
                      <span className="text-sm font-medium">
                        {experiment.config.minScoreThreshold || 70}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-sm">Lookback Days</span>
                      <span className="text-sm font-medium">
                        {experiment.config.lookbackDays || 7}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-sm">Source Filters</span>
                      <span className="text-sm font-medium">
                        {experiment.config.sourceFilters?.join(", ") || "All"}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function MetricCard({
  icon: Icon,
  label,
  value,
  format = "number",
  color,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: number;
  format?: "number" | "percent" | "delta";
  color: string;
}) {
  let displayValue: React.ReactNode;
  let deltaIndicator: React.ReactNode = null;

  if (format === "percent") {
    displayValue = `${(value * 100).toFixed(1)}%`;
  } else if (format === "delta") {
    const delta = value * 100;
    displayValue = `${delta > 0 ? "+" : ""}${delta.toFixed(1)}%`;
    deltaIndicator = delta > 0 ? (
      <ArrowUpRight className="h-4 w-4 text-green-500" />
    ) : delta < 0 ? (
      <ArrowDownRight className="h-4 w-4 text-red-500" />
    ) : (
      <Minus className="h-4 w-4 text-gray-500" />
    );
  } else {
    displayValue = value.toFixed(3);
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{label}</CardTitle>
        <div className={`flex items-center gap-1 ${color}`}>
          <Icon className="h-4 w-4" />
          {deltaIndicator}
        </div>
      </CardHeader>
      <CardContent>
        <div className="text-3xl font-bold flex items-baseline gap-2">
          {displayValue}
        </div>
      </CardContent>
    </Card>
  );
}
