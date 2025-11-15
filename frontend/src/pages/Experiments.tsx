import React, { useState } from "react";
import { Link } from "react-router-dom";
import { useExperimentsOverview } from "../hooks/useExperiments";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Skeleton } from "../components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import {
  FlaskConical,
  Activity,
  TrendingUp,
  AlertTriangle,
  Play,
  Plus,
  BarChart3,
  CheckCircle,
  Clock,
  XCircle,
} from "lucide-react";
import { DataTable } from "../components/ui/data-table";
import { ColumnDef } from "@tanstack/react-table";
import { Experiment, ExperimentStatus } from "../types/api";
import { useToast } from "../components/ui/use-toast";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";

const numberFormatter = new Intl.NumberFormat("en-US");

const statusColors: Record<ExperimentStatus, string> = {
  draft: "bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200",
  running: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
  completed: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  failed: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
};

const statusIcons: Record<ExperimentStatus, React.ComponentType<{ className?: string }>> = {
  draft: Clock,
  running: Activity,
  completed: CheckCircle,
  failed: XCircle,
};

export default function ExperimentsPage() {
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const { toast } = useToast();

  // Fetch experiments overview
  const {
    experimentsQuery: { data: experimentsData, isLoading, error },
    stats,
  } = useExperimentsOverview(statusFilter === "all" ? undefined : statusFilter);

  // Show error toast
  if (error) {
    toast({
      title: "Error loading experiments",
      description: error.message,
      variant: "destructive",
    });
  }

  // Filter experiments based on status
  const filteredExperiments = experimentsData?.experiments.filter((exp) => {
    if (statusFilter === "all") return true;
    return exp.status === statusFilter;
  }) || [];
  const draftExperiments = experimentsData?.experiments.filter((exp) => exp.status === "draft") || [];
  const runningExperiments = experimentsData?.experiments.filter((exp) => exp.status === "running") || [];
  const completedExperiments = experimentsData?.experiments.filter((exp) => exp.status === "completed") || [];
  const failedExperiments = experimentsData?.experiments.filter((exp) => exp.status === "failed") || [];

  // Define columns for experiments table
  const experimentColumns: ColumnDef<Experiment>[] = [
    {
      accessorKey: "name",
      header: "Name",
      cell: ({ row }) => (
        <Link
          to={`/experiments/${row.original.id}`}
          className="font-medium text-primary hover:underline"
        >
          {row.original.name}
        </Link>
      ),
    },
    {
      accessorKey: "description",
      header: "Description",
      cell: ({ row }) => (
        <div className="text-sm text-muted-foreground">
          {row.original.description || "No description"}
        </div>
      ),
    },
    {
      accessorKey: "status",
      header: "Status",
      cell: ({ row }) => {
        const Icon = statusIcons[row.original.status];
        return (
          <Badge className={statusColors[row.original.status]}>
            <Icon className="h-3 w-3 mr-1" />
            {row.original.status}
          </Badge>
        );
      },
    },
    {
      id: "scoringWeights",
      header: "Scoring Weights",
      cell: ({ row }) => {
        const weights = Object.entries(row.original.config.scoringWeights)
          .map(([k, v]) => `${k.substring(0, 4)}: ${Math.round(v * 100)}%`)
          .join(", ");
        return <div className="text-sm text-muted-foreground">{weights}</div>;
      },
    },
    {
      accessorKey: "config.lookbackDays",
      header: "Lookback",
      cell: ({ row }) => (
        <div className="text-sm">{row.original.config.lookbackDays || 7} days</div>
      ),
    },
    {
      accessorKey: "createdAt",
      header: "Created",
      cell: ({ row }) => (
        <div className="text-sm text-muted-foreground">
          {new Date(row.original.createdAt).toLocaleDateString()}
        </div>
      ),
    },
    {
      id: "actions",
      header: "Actions",
      cell: ({ row }) => (
        <div className="flex gap-2">
          <Link to={`/experiments/${row.original.id}`}>
            <Button variant="ghost" size="sm">
              <BarChart3 className="h-4 w-4" />
            </Button>
          </Link>
          {row.original.status === "draft" && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => handleRunExperiment(row.original.id)}
            >
              <Play className="h-4 w-4 text-green-600" />
            </Button>
          )}
        </div>
      ),
    },
  ];

  // Placeholder for running an experiment
  const handleRunExperiment = (experimentId: string) => {
    toast({
      title: "Running Experiment",
      description: `Experiment ${experimentId} is starting...`,
    });
    // In a real implementation, this would call the run experiment mutation
  };

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">A/B Testing Dashboard</h1>
          <p className="text-muted-foreground">
            Compare scoring algorithms, validate improvements, and track experiment performance
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Link to="/experiments/new">
            <Button>
              <Plus className="h-4 w-4 mr-2" />
              New Experiment
            </Button>
          </Link>
          <Link to="/labels">
            <Button variant="outline">
              <FlaskConical className="h-4 w-4 mr-2" />
              Ground Truth
            </Button>
          </Link>
        </div>
      </header>

      {/* Stats Overview */}
      <section className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          icon={FlaskConical}
          label="Total Experiments"
          value={stats.total}
          loading={isLoading}
          color="text-blue-500"
        />
        <StatCard
          icon={Clock}
          label="Draft"
          value={stats.draft}
          loading={isLoading}
          color="text-gray-500"
        />
        <StatCard
          icon={Activity}
          label="Running"
          value={stats.running}
          loading={isLoading}
          color="text-blue-500"
        />
        <StatCard
          icon={CheckCircle}
          label="Completed"
          value={stats.completed}
          loading={isLoading}
          color="text-green-500"
        />
      </section>

      {/* Main Content Tabs */}
      <Tabs defaultValue="all" className="space-y-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <TabsList className="flex flex-wrap gap-1">
            <TabsTrigger value="all">All</TabsTrigger>
            <TabsTrigger value="draft">Draft</TabsTrigger>
            <TabsTrigger value="running">Running</TabsTrigger>
            <TabsTrigger value="completed">Completed</TabsTrigger>
            <TabsTrigger value="failed">Failed</TabsTrigger>
          </TabsList>
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-40 h-9">
              <SelectValue placeholder="Filter..." />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Status</SelectItem>
              <SelectItem value="draft">Draft</SelectItem>
              <SelectItem value="running">Running</SelectItem>
              <SelectItem value="completed">Completed</SelectItem>
              <SelectItem value="failed">Failed</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <TabsContent value="all">
          <Card>
            <CardHeader>
              <CardTitle>All Experiments</CardTitle>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <TableSkeleton />
              ) : filteredExperiments.length === 0 ? (
                <EmptyState message="No experiments found" actionLabel="Create Experiment" actionHref="/experiments/new" />
              ) : (
                <ResponsiveTable>
                  <DataTable
                    columns={experimentColumns}
                    data={filteredExperiments}
                    getRowKey={(experiment) => experiment.id}
                  />
                </ResponsiveTable>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="draft">
          <Card>
            <CardHeader>
              <CardTitle>Draft Experiments</CardTitle>
              <p className="text-sm text-muted-foreground">
                Experiments ready to be configured and run
              </p>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <TableSkeleton rows={6} />
              ) : draftExperiments.length === 0 ? (
                <EmptyState message="No draft experiments yet" actionLabel="New Experiment" actionHref="/experiments/new" />
              ) : (
                <ResponsiveTable>
                  <DataTable
                    columns={experimentColumns}
                    data={draftExperiments}
                    getRowKey={(experiment) => experiment.id}
                  />
                </ResponsiveTable>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="running">
          <Card>
            <CardHeader>
              <CardTitle>Running Experiments</CardTitle>
              <p className="text-sm text-muted-foreground">
                Experiments currently being executed
              </p>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <TableSkeleton rows={6} />
              ) : runningExperiments.length === 0 ? (
                <EmptyState message="No experiments currently running" />
              ) : (
                <ResponsiveTable>
                  <DataTable
                    columns={experimentColumns}
                    data={runningExperiments}
                    getRowKey={(experiment) => experiment.id}
                  />
                </ResponsiveTable>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="completed">
          <Card>
            <CardHeader>
              <CardTitle>Completed Experiments</CardTitle>
              <p className="text-sm text-muted-foreground">
                Experiments with results ready for analysis
              </p>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <TableSkeleton rows={6} />
              ) : completedExperiments.length === 0 ? (
                <EmptyState message="No completed experiments" />
              ) : (
                <ResponsiveTable>
                  <DataTable
                    columns={experimentColumns}
                    data={completedExperiments}
                    getRowKey={(experiment) => experiment.id}
                  />
                </ResponsiveTable>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="failed">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <AlertTriangle className="h-5 w-5 text-red-500" />
                Failed Experiments
              </CardTitle>
              <p className="text-sm text-muted-foreground">
                Experiments that encountered errors during execution
              </p>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <TableSkeleton rows={6} />
              ) : failedExperiments.length === 0 ? (
                <EmptyState message="No failed experiments" description="Track this tab to monitor regression risk." />
              ) : (
                <ResponsiveTable>
                  <DataTable
                    columns={experimentColumns}
                    data={failedExperiments}
                    getRowKey={(experiment) => experiment.id}
                  />
                </ResponsiveTable>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  loading,
  color,
  suffix = "",
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: number | string;
  loading: boolean;
  color: string;
  suffix?: string;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{label}</CardTitle>
        <Icon className={`h-4 w-4 ${color}`} />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">
          {loading ? (
            <Skeleton className="h-7 w-16" />
          ) : (
            <>
              {typeof value === "number" ? numberFormatter.format(value) : value}
              {suffix}
            </>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function TableSkeleton({ rows = 8 }: { rows?: number }) {
  return (
    <div className="space-y-2">
      {[...Array(rows)].map((_, index) => (
        <Skeleton key={index} className="h-16 w-full" />
      ))}
    </div>
  );
}

function ResponsiveTable({ children }: { children: React.ReactNode }) {
  return (
    <div className="w-full overflow-x-auto">
      <div className="min-w-[640px]">{children}</div>
    </div>
  );
}

function EmptyState({
  message,
  description,
  actionLabel,
  actionHref,
}: {
  message: string;
  description?: string;
  actionLabel?: string;
  actionHref?: string;
}) {
  return (
    <div className="flex flex-col items-center gap-3 py-10 text-center text-muted-foreground">
      <div>
        <p className="font-medium text-foreground">{message}</p>
        {description ? <p className="text-sm">{description}</p> : null}
      </div>
      {actionLabel && actionHref ? (
        <Link to={actionHref}>
          <Button variant="outline" size="sm">
            {actionLabel}
          </Button>
        </Link>
      ) : null}
    </div>
  );
}
