import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Badge } from "../components/ui/badge";
import { RefreshCw, Filter, TrendingUp, Users, Search } from "lucide-react";
import { listDiscoveries, getDiscoveryStats, refreshPipeline } from "../api/discoveries";
import { DiscoveriesListParams } from "../types/api";
import { DiscoveryCard } from "../components/DiscoveryCard";
import { ScoreBadge } from "../components/ScoreBadge";
import { TopicFilter } from "../components/TopicFilter";
import { useToast } from "../hooks/use-toast";
import { Skeleton } from "../components/ui/skeleton";

export default function DiscoveriesPage() {
  const [params, setParams] = useState<DiscoveriesListParams>({
    minScore: 70,
    hours: 168, // Last 7 days
    limit: 50,
    sort: "discoveryScore",
    order: "desc",
  });

  const [isRefreshing, setIsRefreshing] = useState(false);
  const { toast } = useToast();

  // Fetch discoveries
  const {
    data: discoveries,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["discoveries", params],
    queryFn: () => listDiscoveries(params),
  });

  // Fetch stats
  const { data: stats } = useQuery({
    queryKey: ["discovery-stats"],
    queryFn: getDiscoveryStats,
  });

  const handleRefresh = async () => {
    setIsRefreshing(true);
    try {
      const result = await refreshPipeline({ type: "discovery" });
      toast({
        title: "Pipeline refreshed",
        description: `Fetched: ${result.stats.fetched}, Analyzed: ${result.stats.analyzed}, Scored: ${result.stats.scored}`,
      });
      refetch();
    } catch (err) {
      toast({
        title: "Refresh failed",
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setIsRefreshing(false);
    }
  };

  const handleParamChange = <K extends keyof DiscoveriesListParams>(
    key: K,
    value: DiscoveriesListParams[K]
  ) => {
    setParams((prev) => ({ ...prev, [key]: value }));
  };

  if (isError) {
    return (
      <div className="flex items-center justify-center h-screen">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle>Error Loading Discoveries</CardTitle>
            <CardDescription>{error instanceof Error ? error.message : "Unknown error"}</CardDescription>
          </CardHeader>
          <CardContent>
            <Button onClick={() => refetch()}>Retry</Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="container mx-auto py-6 space-y-6">
      {/* Header */}
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Discoveries</h1>
          <p className="text-muted-foreground">
            Novel deep-tech research and breakthroughs ranked by discovery score
          </p>
        </div>
        <Button onClick={handleRefresh} disabled={isRefreshing}>
          <RefreshCw className={`mr-2 h-4 w-4 ${isRefreshing ? "animate-spin" : ""}`} />
          Refresh Pipeline
        </Button>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Total Artifacts</CardTitle>
              <TrendingUp className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.totalArtifacts}</div>
              <p className="text-xs text-muted-foreground">
                Across all sources
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">High-Value Discoveries</CardTitle>
              <Badge variant="secondary" className="bg-green-100 text-green-800">
                Score &gt;70
              </Badge>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.totalDiscoveries}</div>
              <p className="text-xs text-muted-foreground">
                {((stats.totalDiscoveries / stats.totalArtifacts) * 100).toFixed(1)}% of artifacts
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Avg Discovery Score</CardTitle>
              <ScoreBadge score={stats.avgDiscoveryScore} />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.avgDiscoveryScore.toFixed(1)}</div>
              <p className="text-xs text-muted-foreground">
                Across all discoveries
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Top Topic</CardTitle>
              <Users className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                {stats.topTopics[0]?.name || "-"}
              </div>
              <p className="text-xs text-muted-foreground">
                {stats.topTopics[0]?.count || 0} artifacts
              </p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Filters */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center">
            <Filter className="mr-2 h-4 w-4" />
            Filters
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
            <div className="space-y-2">
              <label className="text-sm font-medium">Min Score</label>
              <Select
                value={String(params.minScore || 70)}
                onValueChange={(v) => handleParamChange("minScore", Number(v))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="60">&gt; 60</SelectItem>
                  <SelectItem value="70">&gt; 70</SelectItem>
                  <SelectItem value="80">&gt; 80</SelectItem>
                  <SelectItem value="85">&gt; 85</SelectItem>
                  <SelectItem value="90">&gt; 90</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium">Time Window</label>
              <Select
                value={String(params.hours || 168)}
                onValueChange={(v) => handleParamChange("hours", Number(v))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="24">Last 24 hours</SelectItem>
                  <SelectItem value="72">Last 3 days</SelectItem>
                  <SelectItem value="168">Last 7 days</SelectItem>
                  <SelectItem value="336">Last 14 days</SelectItem>
                  <SelectItem value="720">Last 30 days</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium">Source</label>
              <Select
                value={params.source || "all"}
                onValueChange={(v) => handleParamChange("source", v === "all" ? undefined : v as any)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                <SelectItem value="all">All Sources</SelectItem>
                <SelectItem value="arxiv">arXiv</SelectItem>
                <SelectItem value="github">GitHub</SelectItem>
                <SelectItem value="x">X/Twitter</SelectItem>
                <SelectItem value="facebook">Facebook</SelectItem>
                <SelectItem value="linkedin">LinkedIn</SelectItem>
                <SelectItem value="reddit">Reddit</SelectItem>
                <SelectItem value="hackernews">Hacker News</SelectItem>
              </SelectContent>
            </Select>
          </div>

            <div className="space-y-2">
              <label className="text-sm font-medium">Sort By</label>
              <Select
                value={params.sort || "discoveryScore"}
                onValueChange={(v) => handleParamChange("sort", v as any)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="discoveryScore">Discovery Score</SelectItem>
                  <SelectItem value="novelty">Novelty</SelectItem>
                  <SelectItem value="emergence">Emergence</SelectItem>
                  <SelectItem value="obscurity">Obscurity</SelectItem>
                  <SelectItem value="publishedAt">Published Date</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium">Limit</label>
              <Select
                value={String(params.limit || 50)}
                onValueChange={(v) => handleParamChange("limit", Number(v))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="25">25</SelectItem>
                  <SelectItem value="50">50</SelectItem>
                  <SelectItem value="100">100</SelectItem>
                  <SelectItem value="200">200</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Topic Filter */}
          <TopicFilter
            selectedTopic={params.topic}
            onTopicSelect={(topic) => handleParamChange("topic", topic)}
          />
        </CardContent>
      </Card>

      {/* Results */}
      <div className="space-y-4">
        <div className="flex justify-between items-center">
          <h2 className="text-xl font-semibold">
            {isLoading ? "Loading..." : `${discoveries?.length || 0} Discoveries`}
          </h2>
          {params.sort && (
            <div className="text-sm text-muted-foreground">
              Sorted by {params.sort} ({params.order || "desc"})
            </div>
          )}
        </div>

        {isLoading ? (
          <div className="space-y-4">
            {[...Array(5)].map((_, i) => (
              <Card key={i}>
                <CardHeader>
                  <Skeleton className="h-6 w-3/4" />
                  <Skeleton className="h-4 w-1/2" />
                </CardHeader>
                <CardContent>
                  <Skeleton className="h-20 w-full" />
                </CardContent>
              </Card>
            ))}
          </div>
        ) : discoveries && discoveries.length > 0 ? (
          <div className="space-y-4">
            {discoveries.map((discovery) => (
              <DiscoveryCard key={discovery.id} discovery={discovery} />
            ))}
          </div>
        ) : (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-12">
              <Search className="h-12 w-12 text-muted-foreground mb-4" />
              <h3 className="text-lg font-semibold mb-2">No discoveries found</h3>
              <p className="text-muted-foreground text-center">
                Try adjusting your filters or refresh the pipeline to fetch new data.
              </p>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
