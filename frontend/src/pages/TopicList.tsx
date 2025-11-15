import React, { useState } from "react";
import { Link } from "react-router-dom";
import { useTopics, useMergeCandidates, useSplitCandidates } from "../hooks/useTopics";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Skeleton } from "../components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { TrendingUp, GitMerge, GitBranch, AlertTriangle, Activity } from "lucide-react";
import { DataTable } from "../components/ui/data-table";
import { ColumnDef } from "@tanstack/react-table";
import { TrendingTopic, TopicMergeCandidate, TopicSplitDetection } from "../types/api";
import { useToast } from "../components/ui/use-toast";

const numberFormatter = new Intl.NumberFormat("en-US");

export default function TopicListPage() {
  const [windowDays, setWindowDays] = useState(30);
  const { toast } = useToast();

  // Fetch trending topics
  const { 
    data: topics = [], 
    isLoading: topicsLoading,
    error: topicsError 
  } = useTopics({ windowDays, limit: 100 });

  // Fetch merge candidates
  const {
    data: mergeCandidates = [],
    isLoading: mergesLoading,
    error: mergesError
  } = useMergeCandidates(windowDays, 0.85);

  // Fetch split candidates
  const {
    data: splitCandidates = [],
    isLoading: splitsLoading,
    error: splitsError
  } = useSplitCandidates(windowDays, 0.7);

  // Show error toasts
  if (topicsError) {
    toast({
      title: "Error loading topics",
      description: topicsError.message,
      variant: "destructive",
    });
  }
  if (mergesError) {
    toast({
      title: "Error loading merge candidates",
      description: mergesError.message,
      variant: "destructive",
    });
  }
  if (splitsError) {
    toast({
      title: "Error loading split candidates",
      description: splitsError.message,
      variant: "destructive",
    });
  }

  // Define columns for topics table
  const topicColumns: ColumnDef<TrendingTopic>[] = [
    {
      accessorKey: "name",
      header: "Topic",
      cell: ({ row }) => (
        <Link
          to={`/topics/${row.original.id}`}
          className="font-medium text-primary hover:underline"
        >
          {row.original.name}
        </Link>
      ),
    },
    {
      accessorKey: "taxonomyPath",
      header: "Category",
      cell: ({ row }) => (
        <div className="text-sm text-muted-foreground">
          {row.original.taxonomyPath || "-"}
        </div>
      ),
    },
    {
      accessorKey: "artifactCount",
      header: "Artifacts",
      cell: ({ row }) => (
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-muted-foreground" />
          <span className="font-medium">
            {numberFormatter.format(row.original.artifactCount)}
          </span>
        </div>
      ),
    },
    {
      accessorKey: "avgDiscoveryScore",
      header: "Avg Score",
      cell: ({ row }) => (
        <Badge variant="outline">
          {row.original.avgDiscoveryScore.toFixed(1)}
        </Badge>
      ),
    },
    {
      id: "actions",
      header: "Actions",
      cell: ({ row }) => (
        <Link to={`/topics/${row.original.id}`}>
          <Button variant="ghost" size="sm">
            View Details
          </Button>
        </Link>
      ),
    },
  ];

  // Define columns for merge candidates table
  const mergeColumns: ColumnDef<TopicMergeCandidate>[] = [
    {
      accessorKey: "primaryTopic.name",
      header: "Primary Topic",
      cell: ({ row }) => (
        <Link
          to={`/topics/${row.original.primaryTopic.id}`}
          className="font-medium text-primary hover:underline"
        >
          {row.original.primaryTopic.name}
        </Link>
      ),
    },
    {
      accessorKey: "secondaryTopic.name",
      header: "Secondary Topic",
      cell: ({ row }) => (
        <Link
          to={`/topics/${row.original.secondaryTopic.id}`}
          className="font-medium text-primary hover:underline"
        >
          {row.original.secondaryTopic.name}
        </Link>
      ),
    },
    {
      accessorKey: "currentSimilarity",
      header: "Similarity",
      cell: ({ row }) => (
        <Badge
          variant={row.original.currentSimilarity > 0.9 ? "default" : "secondary"}
        >
          {(row.original.currentSimilarity * 100).toFixed(1)}%
        </Badge>
      ),
    },
    {
      accessorKey: "confidence",
      header: "Confidence",
      cell: ({ row }) => (
        <div className="flex items-center gap-2">
          <div className="h-2 w-20 bg-muted rounded-full overflow-hidden">
            <div
              className="h-full bg-primary transition-all"
              style={{ width: `${row.original.confidence * 100}%` }}
            />
          </div>
          <span className="text-sm font-medium">
            {(row.original.confidence * 100).toFixed(0)}%
          </span>
        </div>
      ),
    },
  ];

  // Define columns for split candidates table
  const splitColumns: ColumnDef<TopicSplitDetection>[] = [
    {
      accessorKey: "primaryTopic.name",
      header: "Topic",
      cell: ({ row }) => (
        <Link
          to={`/topics/${row.original.primaryTopic.id}`}
          className="font-medium text-primary hover:underline"
        >
          {row.original.primaryTopic.name}
        </Link>
      ),
    },
    {
      accessorKey: "coherenceDrop",
      header: "Coherence Drop",
      cell: ({ row }) => (
        <Badge variant="destructive">
          {(row.original.coherenceDrop * 100).toFixed(1)}%
        </Badge>
      ),
    },
    {
      accessorKey: "subClusters",
      header: "Sub-clusters",
      cell: ({ row }) => (
        <Badge variant="outline">
          {row.original.subClusters?.length || 0} clusters
        </Badge>
      ),
    },
    {
      accessorKey: "confidence",
      header: "Confidence",
      cell: ({ row }) => (
        <div className="flex items-center gap-2">
          <div className="h-2 w-20 bg-muted rounded-full overflow-hidden">
            <div
              className="h-full bg-destructive transition-all"
              style={{ width: `${row.original.confidence * 100}%` }}
            />
          </div>
          <span className="text-sm font-medium">
            {(row.original.confidence * 100).toFixed(0)}%
          </span>
        </div>
      ),
    },
  ];

  const isLoading = topicsLoading || mergesLoading || splitsLoading;

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Topic Evolution Dashboard</h1>
          <p className="text-muted-foreground">
            Monitor trending topics, identify merge opportunities, and detect emerging topic splits
          </p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={windowDays}
            onChange={(e) => setWindowDays(Number(e.target.value))}
            className="rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
          >
            <option value={7}>Last 7 days</option>
            <option value={14}>Last 14 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
          </select>
        </div>
      </header>

      {/* Stats Overview */}
      <section className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          icon={TrendingUp}
          label="Active Topics"
          value={topics.length}
          loading={topicsLoading}
          color="text-blue-500"
        />
        <StatCard
          icon={GitMerge}
          label="Merge Candidates"
          value={mergeCandidates.length}
          loading={mergesLoading}
          color="text-amber-500"
        />
        <StatCard
          icon={GitBranch}
          label="Split Candidates"
          value={splitCandidates.length}
          loading={splitsLoading}
          color="text-purple-500"
        />
        <StatCard
          icon={AlertTriangle}
          label="High-Risk Topics"
          value={splitCandidates.filter(s => s.coherenceDrop > 0.3).length}
          loading={splitsLoading}
          color="text-red-500"
        />
      </section>

      {/* Main Content Tabs */}
      <Tabs defaultValue="topics" className="space-y-4">
        <TabsList>
          <TabsTrigger value="topics">Trending Topics</TabsTrigger>
          <TabsTrigger value="merges" className="flex items-center gap-2">
            <GitMerge className="h-4 w-4" />
            Merge Candidates ({mergeCandidates.length})
          </TabsTrigger>
          <TabsTrigger value="splits" className="flex items-center gap-2">
            <GitBranch className="h-4 w-4" />
            Split Candidates ({splitCandidates.length})
          </TabsTrigger>
        </TabsList>

        <TabsContent value="topics">
          <Card>
            <CardHeader>
              <CardTitle>Trending Topics</CardTitle>
            </CardHeader>
            <CardContent>
              {topicsLoading ? (
                <div className="space-y-2">
                  {[...Array(5)].map((_, i) => (
                    <Skeleton key={i} className="h-12 w-full" />
                  ))}
                </div>
              ) : topics.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  No trending topics found
                </div>
              ) : (
                <DataTable
                  columns={topicColumns}
                  data={topics}
                  getRowKey={(topic) => topic.name}
                />
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="merges">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Topic Merge Candidates</CardTitle>
                <Badge variant="outline" className="flex items-center gap-1">
                  <AlertTriangle className="h-3 w-3" />
                  Review recommended
                </Badge>
              </div>
              <p className="text-sm text-muted-foreground">
                Topics with high similarity and increasing overlap. Consider merging these topics to maintain clean taxonomy.
              </p>
            </CardHeader>
            <CardContent>
              {mergesLoading ? (
                <div className="space-y-2">
                  {[...Array(3)].map((_, i) => (
                    <Skeleton key={i} className="h-12 w-full" />
                  ))}
                </div>
              ) : mergeCandidates.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  No merge candidates detected
                </div>
              ) : (
                <DataTable
                  columns={mergeColumns}
                  data={mergeCandidates}
                  getRowKey={(candidate) => `${candidate.primaryTopic.id}-${candidate.secondaryTopic.id}`}
                />
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="splits">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Topic Split Candidates</CardTitle>
                <Badge variant="destructive" className="flex items-center gap-1">
                  <AlertTriangle className="h-3 w-3" />
                  Action needed
                </Badge>
              </div>
              <p className="text-sm text-muted-foreground">
                Topics showing decreasing coherence or emerging sub-clusters. Consider splitting these topics for better organization.
              </p>
            </CardHeader>
            <CardContent>
              {splitsLoading ? (
                <div className="space-y-2">
                  {[...Array(3)].map((_, i) => (
                    <Skeleton key={i} className="h-12 w-full" />
                  ))}
                </div>
              ) : splitCandidates.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  No split candidates detected
                </div>
              ) : (
                <DataTable
                  columns={splitColumns}
                  data={splitCandidates}
                  getRowKey={(candidate) => `${candidate.primaryTopic.id}`}
                />
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
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: number;
  loading: boolean;
  color: string;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{label}</CardTitle>
        <Icon className={`h-4 w-4 ${color}`} />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">
          {loading ? <Skeleton className="h-7 w-16" /> : numberFormatter.format(value)}
        </div>
      </CardContent>
    </Card>
  );
}
