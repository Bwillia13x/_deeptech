import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { Button } from "../components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Badge } from "../components/ui/badge";
import { RefreshCw, BarChart3, TrendingUp, Activity, Database, Zap, Shield } from "lucide-react";
import { getDashboardAnalytics, getDiscoveryStats } from "../api/discoveries";
import { SourceDistributionChart } from "../components/analytics/SourceDistributionChart";
import { TemporalTrendsChart } from "../components/analytics/TemporalTrendsChart";
import { ScoreDistributionChart } from "../components/analytics/ScoreDistributionChart";
import { CorrelationAnalysis } from "../components/analytics/CorrelationAnalysis";
import { SystemHealthPanel } from "../components/analytics/SystemHealthPanel";
import { Skeleton } from "../components/ui/skeleton";
import { useToast } from "../hooks/use-toast";

interface DashboardData {
  source_distribution: any;
  temporal_trends: any;
  cross_source_correlations: any;
  score_distributions: any;
  system_health: any;
}

export default function AnalyticsDashboard() {
  const [days, setDays] = useState(30);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const { toast } = useToast();

  // Fetch dashboard data
  const {
    data: dashboardData,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery<DashboardData>({
    queryKey: ["dashboard-analytics", days],
    queryFn: () => getDashboardAnalytics(days),
  });

  // Fetch discovery stats
  const { data: discoveryStats } = useQuery({
    queryKey: ["discovery-stats"],
    queryFn: getDiscoveryStats,
  });

  const handleRefresh = async () => {
    setIsRefreshing(true);
    try {
      await refetch();
      toast({
        title: "Dashboard refreshed",
        description: "Analytics data updated successfully",
      });
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

  if (isError) {
    return (
      <div className="flex items-center justify-center h-screen">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle>Error Loading Dashboard</CardTitle>
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
          <h1 className="text-3xl font-bold tracking-tight">Analytics Dashboard</h1>
          <p className="text-muted-foreground">
            Comprehensive analytics and insights for your discovery pipeline
          </p>
        </div>
        <div className="flex gap-2">
          <Select value={days.toString()} onValueChange={(v) => setDays(parseInt(v))}>
            <SelectTrigger className="w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="7">Last 7 days</SelectItem>
              <SelectItem value="30">Last 30 days</SelectItem>
              <SelectItem value="90">Last 90 days</SelectItem>
            </SelectContent>
          </Select>
          <Button onClick={handleRefresh} disabled={isRefreshing}>
            <RefreshCw className={`mr-2 h-4 w-4 ${isRefreshing ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Overview Stats */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          icon={<Zap className="h-4 w-4 text-blue-500" />}
          label="Total Artifacts"
          value={discoveryStats?.totalArtifacts}
          loading={isLoading}
        />
        <StatCard
          icon={<TrendingUp className="h-4 w-4 text-green-500" />}
          label="High-Quality Discoveries"
          value={discoveryStats?.totalDiscoveries}
          loading={isLoading}
        />
        <StatCard
          icon={<BarChart3 className="h-4 w-4 text-purple-500" />}
          label="Avg Discovery Score"
          value={discoveryStats?.avgDiscoveryScore}
          loading={isLoading}
          format="score"
        />
        <StatCard
          icon={<Activity className="h-4 w-4 text-orange-500" />}
          label="System Status"
          value={dashboardData?.system_health?.status}
          loading={isLoading}
          format="status"
        />
      </div>

      {/* Main Content Tabs */}
      <Tabs defaultValue="overview" className="space-y-4">
        <TabsList className="grid w-full grid-cols-5 lg:w-[600px]">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="sources">Sources</TabsTrigger>
          <TabsTrigger value="trends">Trends</TabsTrigger>
          <TabsTrigger value="correlations">Correlations</TabsTrigger>
          <TabsTrigger value="health">Health</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-4">
          <div className="grid gap-4 lg:grid-cols-2">
            <SourceDistributionChart
              data={dashboardData?.source_distribution}
              isLoading={isLoading}
            />
            <ScoreDistributionChart
              data={dashboardData?.score_distributions}
              isLoading={isLoading}
            />
          </div>
        </TabsContent>

        <TabsContent value="sources" className="space-y-4">
          <SourceDistributionChart
            data={dashboardData?.source_distribution}
            isLoading={isLoading}
            detailed
          />
        </TabsContent>

        <TabsContent value="trends" className="space-y-4">
          <TemporalTrendsChart
            data={dashboardData?.temporal_trends}
            isLoading={isLoading}
          />
        </TabsContent>

        <TabsContent value="correlations" className="space-y-4">
          <CorrelationAnalysis
            data={dashboardData?.cross_source_correlations}
            isLoading={isLoading}
          />
        </TabsContent>

        <TabsContent value="health" className="space-y-4">
          <SystemHealthPanel
            data={dashboardData?.system_health}
            isLoading={isLoading}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}

interface StatCardProps {
  icon: React.ReactNode;
  label: string;
  value?: number | string;
  loading: boolean;
  format?: "number" | "score" | "status";
}

function StatCard({ icon, label, value, loading, format = "number" }: StatCardProps) {
  const renderValue = () => {
    if (loading) {
      return <Skeleton className="h-8 w-24" />;
    }

    if (format === "score" && typeof value === "number") {
      return <div className="text-3xl font-semibold">{value.toFixed(1)}</div>;
    }

    if (format === "status" && typeof value === "string") {
      const color = value === "healthy" ? "text-green-500" : value === "warning" ? "text-yellow-500" : "text-red-500";
      return (
        <div className={`text-3xl font-semibold ${color} flex items-center gap-2`}>
          <Shield className="h-6 w-6" />
          {value}
        </div>
      );
    }

    return <div className="text-3xl font-semibold">{value ?? 0}</div>;
  };

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm text-muted-foreground">{label}</div>
            {renderValue()}
          </div>
          {icon}
        </div>
      </CardContent>
    </Card>
  );
}