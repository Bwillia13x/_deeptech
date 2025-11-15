import React, { useState } from "react";
import { Link } from "react-router-dom";
import { useLabels, useAddLabel } from "../hooks/useExperiments";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Skeleton } from "../components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import {
  FlaskConical,
  Tag,
  Upload,
  Download,
  Plus,
  User,
  Calendar,
  Filter,
  BarChart3,
  CheckCircle,
  XCircle,
} from "lucide-react";
import { DataTable } from "../components/ui/data-table";
import { ColumnDef } from "@tanstack/react-table";
import { DiscoveryLabel } from "../types/api";
import { useToast } from "../components/ui/use-toast";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { cn } from "../lib/utils";

export default function LabelsPage() {
  const [labelFilter, setLabelFilter] = useState<string>("all");
  const [importOpen, setImportOpen] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const { toast } = useToast();

  // Fetch labels
  const {
    data: labelsData,
    isLoading,
    error,
  } = useLabels({
    label: labelFilter === "all" ? undefined : labelFilter,
  });

  // Add label mutation
  const addLabelMutation = useAddLabel();

  // Show error toast
  if (error) {
    toast({
      title: "Error loading labels",
      description: error.message,
      variant: "destructive",
    });
  }

  const labels = labelsData?.labels || [];
  const positiveLabels = labels.filter((l) => l.label.includes("positive"));
  const negativeLabels = labels.filter((l) => l.label.includes("negative"));
  const relevanceLabels = labels.filter((l) => l.label === "relevant" || l.label === "irrelevant");

  // Count labels by type
  const labelCounts = labels.reduce(
    (acc, label) => {
      acc[label.label] = (acc[label.label] || 0) + 1;
      return acc;
    },
    {} as Record<string, number>
  );

  // Define columns for labels table
  const labelColumns: ColumnDef<DiscoveryLabel>[] = [
    {
      accessorKey: "artifactTitle",
      header: "Artifact",
      cell: ({ row }) => (
        <div className="space-y-1">
          <div className="font-medium">{row.original.artifactTitle}</div>
          <div className="text-sm text-muted-foreground">
            {row.original.artifactSource} • ID: {row.original.artifactId}
          </div>
        </div>
      ),
    },
    {
      accessorKey: "label",
      header: "Label",
      cell: ({ row }) => {
        const labelColors: Record<string, string> = {
          true_positive: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
          false_positive: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
          true_negative: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
          false_negative: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200",
          relevant: "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200",
          irrelevant: "bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200",
        };
        return (
          <Badge className={labelColors[row.original.label] || "bg-gray-100 text-gray-800"}>
            {row.original.label.replace("_", " ")}
          </Badge>
        );
      },
    },
    {
      accessorKey: "confidence",
      header: "Confidence",
      cell: ({ row }) => {
        const segments = 10;
        const activeSegments = Math.round(row.original.confidence * segments);
        return (
          <div className="flex items-center gap-2">
            <div className="flex h-2 w-20 gap-0.5">
              {Array.from({ length: segments }).map((_, index) => (
                <span
                  key={index}
                  className={cn(
                    "flex-1 rounded-full bg-muted transition-colors",
                    index < activeSegments && "bg-primary"
                  )}
                />
              ))}
            </div>
            <span className="text-sm font-medium">
              {(row.original.confidence * 100).toFixed(0)}%
            </span>
          </div>
        );
      },
    },
    {
      accessorKey: "annotator",
      header: "Annotator",
      cell: ({ row }) => (
        <div className="flex items-center gap-2">
          {row.original.annotator ? (
            <>
              <User className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm">{row.original.annotator}</span>
            </>
          ) : (
            <span className="text-sm text-muted-foreground">Auto</span>
          )}
        </div>
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
        <Link to={`/artifacts/${row.original.artifactId}`}>
          <Button variant="ghost" size="sm">
            View
          </Button>
        </Link>
      ),
    },
  ];

  // Handle file import
  const handleImport = async () => {
    if (!selectedFile) {
      toast({
        title: "No file selected",
        variant: "destructive",
      });
      return;
    }

    try {
      // In a real implementation, this would upload the file
      toast({
        title: "Importing Labels",
        description: `Importing ${selectedFile.name}...`,
      });
      setImportOpen(false);
      setSelectedFile(null);
    } catch (error) {
      toast({
        title: "Import Failed",
        description: error instanceof Error ? error.message : "Unknown error",
        variant: "destructive",
      });
    }
  };

  // Handle export
  const handleExport = () => {
    toast({
      title: "Exporting Labels",
      description: "Preparing CSV download...",
    });
    // In a real implementation, this would trigger a download
  };

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Ground Truth Labels</h1>
          <p className="text-muted-foreground">
            Annotate artifacts with labels for training and validation
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Dialog open={importOpen} onOpenChange={setImportOpen}>
            <DialogTrigger asChild>
              <Button variant="outline">
                <Upload className="h-4 w-4 mr-2" />
                Import CSV
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Import Labels from CSV</DialogTitle>
              </DialogHeader>
              <div className="space-y-4">
                <div>
                  <Label>CSV File</Label>
                  <Input
                    type="file"
                    accept=".csv"
                    onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                  />
                  <p className="text-sm text-muted-foreground mt-1">
                    Expected columns: artifact_id, label, confidence, annotator, notes
                  </p>
                </div>
                <Button onClick={handleImport} disabled={!selectedFile}>
                  Import
                </Button>
              </div>
            </DialogContent>
          </Dialog>
          <Button onClick={handleExport} variant="outline">
            <Download className="h-4 w-4 mr-2" />
            Export
          </Button>
          <Link to="/experiments">
            <Button>
              <BarChart3 className="h-4 w-4 mr-2" />
              Experiments
            </Button>
          </Link>
        </div>
      </header>

      {/* Label Distribution Stats */}
      <section className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          icon={Tag}
          label="Total Labels"
          value={labels.length}
          loading={isLoading}
          color="text-blue-500"
        />
        <StatCard
          icon={CheckCircle}
          label="True Positives"
          value={labelCounts["true_positive"] || 0}
          loading={isLoading}
          color="text-green-500"
        />
        <StatCard
          icon={XCircle}
          label="False Positives"
          value={labelCounts["false_positive"] || 0}
          loading={isLoading}
          color="text-red-500"
        />
        <StatCard
          icon={User}
          label="Manual Labels"
          value={labels.filter((l) => l.annotator).length}
          loading={isLoading}
          color="text-purple-500"
        />
      </section>

      {/* Main Content Tabs */}
      <Tabs defaultValue="all" className="space-y-4">
        <TabsList className="flex flex-wrap gap-2">
          <TabsTrigger value="all">
            All Labels ({labels.length})
          </TabsTrigger>
          <TabsTrigger value="positive">Positive</TabsTrigger>
          <TabsTrigger value="negative">Negative</TabsTrigger>
          <TabsTrigger value="relevant">Relevant</TabsTrigger>
        </TabsList>

        <TabsContent value="all">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="flex items-center gap-2">
                  <FlaskConical className="h-5 w-5" />
                  All Labels
                </CardTitle>
                <Select value={labelFilter} onValueChange={setLabelFilter}>
                  <SelectTrigger className="w-40 h-9">
                    <SelectValue placeholder="Filter by label..." />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Labels</SelectItem>
                    <SelectItem value="true_positive">True Positive</SelectItem>
                    <SelectItem value="false_positive">False Positive</SelectItem>
                    <SelectItem value="true_negative">True Negative</SelectItem>
                    <SelectItem value="false_negative">False Negative</SelectItem>
                    <SelectItem value="relevant">Relevant</SelectItem>
                    <SelectItem value="irrelevant">Irrelevant</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <TableSkeleton />
              ) : labels.length === 0 ? (
                <EmptyState message="No labels found" description="Start by annotating artifacts." actionLabel="Create Experiment" actionHref="/experiments" />
              ) : (
                <ResponsiveTable>
                  <DataTable
                    columns={labelColumns}
                    data={labels}
                    getRowKey={(label) => label.id}
                  />
                </ResponsiveTable>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="positive">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FlaskConical className="h-5 w-5" />
                Positive Labels
              </CardTitle>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <TableSkeleton rows={6} />
              ) : positiveLabels.length === 0 ? (
                <EmptyState message="No positive labels found" />
              ) : (
                <ResponsiveTable>
                  <DataTable
                    columns={labelColumns}
                    data={positiveLabels}
                    getRowKey={(label) => label.id}
                  />
                </ResponsiveTable>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="negative">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FlaskConical className="h-5 w-5" />
                Negative Labels
              </CardTitle>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <TableSkeleton rows={6} />
              ) : negativeLabels.length === 0 ? (
                <EmptyState message="No negative labels found" />
              ) : (
                <ResponsiveTable>
                  <DataTable
                    columns={labelColumns}
                    data={negativeLabels}
                    getRowKey={(label) => label.id}
                  />
                </ResponsiveTable>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="relevant">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FlaskConical className="h-5 w-5" />
                Relevance Labels
              </CardTitle>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <TableSkeleton rows={6} />
              ) : relevanceLabels.length === 0 ? (
                <EmptyState message="No relevance labels found" />
              ) : (
                <ResponsiveTable>
                  <DataTable
                    columns={labelColumns}
                    data={relevanceLabels}
                    getRowKey={(label) => label.id}
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
              {typeof value === "number" ? value.toLocaleString() : value}
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
