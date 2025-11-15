import React, { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useTopicStats, useTopicTimeline, useTopicEvolution } from "../hooks/useTopics";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { Skeleton } from "../components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "../components/ui/alert";
import { AlertTriangle, Activity, TrendingUp, GitMerge, GitBranch, Calendar } from "lucide-react";

// Recharts imports
import {
  ResponsiveContainer,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  Bar,
  ComposedChart,
} from "recharts";

import { useToast } from "../components/ui/use-toast";
const numberFormatter = new Intl.NumberFormat("en-US");

export default function TopicDetailPage() {
  const { topicId } = useParams<{ topicId: string }>();
  const [windowDays, setWindowDays] = useState(30);
  const { toast } = useToast();

  // Fetch topic data (hooks must be called before any early returns)
  // Use empty strings/values when topicId is missing to satisfy hook order rules
  const {
    data: stats,
    isLoading: statsLoading,
    error: statsError,
  } = useTopicStats({ topicId: topicId || "", windowDays });

  const {
    data: timeline = [],
    isLoading: timelineLoading,
    error: timelineError,
  } = useTopicTimeline(stats?.name || "", windowDays);

  const {
    data: evolutionEvents = [],
    isLoading: evolutionLoading,
    error: evolutionError,
  } = useTopicEvolution(topicId || "", undefined, 20);

  // Error handling - MUST come before any conditional returns
  React.useEffect(() => {
    if (statsError) {
      toast({
        title: "Error loading topic stats",
        description: statsError.message,
        variant: "destructive",
      });
    }
  }, [statsError, toast]);

  React.useEffect(() => {
    if (timelineError) {
      toast({
        title: "Error loading timeline",
        description: timelineError.message,
        variant: "destructive",
      });
    }
  }, [timelineError, toast]);

  React.useEffect(() => {
    if (evolutionError) {
      toast({
        title: "Error loading evolution events",
        description: evolutionError.message,
        variant: "destructive",
      });
    }
  }, [evolutionError, toast]);

  if (!topicId) {
    return (
      <Alert variant="destructive">
        <AlertTriangle className="h-4 w-4" />
        <AlertTitle>Topic not found</AlertTitle>
        <AlertDescription>
          No topic ID provided. Please navigate to a valid topic.
        </AlertDescription>
      </Alert>
    );
  }

  const isLoading = statsLoading || timelineLoading || evolutionLoading;

  // Prepare timeline data for Recharts
  const timelineData = timeline.map((point) => ({
    date: new Date(point.date).toLocaleDateString(),
    count: point.count,
    avgScore: Number(point.avgScore?.toFixed(1) || 0),
  }));

  // Calculate stats from timeline
  const totalArtifacts = timeline.reduce((sum, p) => sum + p.count, 0);
  const avgCount = timeline.length > 0 ? totalArtifacts / timeline.length : 0;
  
  // Filter evolution events by type
  const growthEvents = evolutionEvents.filter((e) => e.eventType === "growth");
  const mergeEvents = evolutionEvents.filter((e) => e.eventType === "merge");
  const splitEvents = evolutionEvents.filter((e) => e.eventType === "split");
  const declineEvents = evolutionEvents.filter((e) => e.eventType === "decline");

  if (!stats && !isLoading) {
    return (
      <Alert variant="destructive">
        <AlertTriangle className="h-4 w-4" />
        <AlertTitle>Topic not found</AlertTitle>
        <AlertDescription>
          Could not find topic with ID: {topicId}
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <header className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-3xl font-bold tracking-tight">
              {isLoading ? <Skeleton className="h-8 w-64" /> : stats?.name}
            </h1>
            {stats?.emergenceMetrics && (
              <Badge
                variant={
                  stats.emergenceMetrics.emergenceScore > 70
                    ? "default"
                    : stats.emergenceMetrics.emergenceScore > 40
                    ? "secondary"
                    : "outline"
                }
              >
                Emergence: {stats.emergenceMetrics.emergenceScore.toFixed(0)}/100
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-4 mt-2 text-sm text-muted-foreground">
            {stats?.taxonomyPath && (
              <span className="flex items-center gap-1">
                <Activity className="h-4 w-4" />
                {stats.taxonomyPath}
              </span>
            )}
            <span className="flex items-center gap-1">
              <Calendar className="h-4 w-4" />
              {windowDays} day analysis
            </span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={windowDays}
            onChange={(e) => setWindowDays(Number(e.target.value))}
            className="rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
          >
            <option value={7}>7 days</option>
            <option value={14}>14 days</option>
            <option value={30}>30 days</option>
            <option value={90}>90 days</option>
          </select>
          <Button variant="outline" onClick={() => window.history.back()}>
            Back to Topics
          </Button>
        </div>
      </header>

      {/* Stats Overview */}
      <section className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          icon={Activity}
          label="Total Artifacts"
          value={numberFormatter.format(totalArtifacts)}
          loading={isLoading}
        />
        <StatCard
          icon={TrendingUp}
          label="Avg Daily Artifacts"
          value={avgCount.toFixed(1)}
          loading={isLoading}
        />
        <StatCard
          icon={GitMerge}
          label="Merge Events"
          value={mergeEvents.length}
          loading={isLoading}
        />
        <StatCard
          icon={GitBranch}
          label="Split Events"
          value={splitEvents.length}
          loading={isLoading}
        />
      </section>

      {/* Growth Prediction Alert */}
      {stats?.growthPrediction && stats.growthPrediction.confidence > 0.7 && (
        <Alert variant="default">
          <TrendingUp className="h-4 w-4" />
          <AlertTitle>Growth Prediction</AlertTitle>
          <AlertDescription>
            Topic is {stats.growthPrediction.trend.replace("_", " ")} with{" "}
            {(stats.growthPrediction.confidence * 100).toFixed(0)}% confidence. 
            Predicted {stats.growthPrediction.predictedCounts[stats.growthPrediction.predictedCounts.length - 1]} artifacts in {stats.growthPrediction.predictionWindowDays} days.
          </AlertDescription>
        </Alert>
      )}

      {/* Main Content Tabs */}
      <Tabs defaultValue="timeline" className="space-y-4">
        <TabsList>
          <TabsTrigger value="timeline" className="flex items-center gap-2">
            <Activity className="h-4 w-4" />
            Timeline
          </TabsTrigger>
          <TabsTrigger value="evolution" className="flex items-center gap-2">
            <GitMerge className="h-4 w-4" />
            Evolution Events ({evolutionEvents.length})
          </TabsTrigger>
          <TabsTrigger value="related" className="flex items-center gap-2">
            <Activity className="h-4 w-4" />
            Related Topics ({stats?.relatedTopics?.length || 0})
          </TabsTrigger>
        </TabsList>

        <TabsContent value="timeline">
          <Card>
            <CardHeader>
              <CardTitle>Topic Timeline</CardTitle>
              <CardDescription>
                Daily artifact count and average discovery score over time
              </CardDescription>
            </CardHeader>
            <CardContent>
              {timelineLoading ? (
                <Skeleton className="h-96 w-full" />
              ) : timelineData.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  No timeline data available for this topic
                </div>
              ) : (
                <ResponsiveContainer width="100%" height={400}>
                  <ComposedChart data={timelineData}>
                    <CartesianGrid strokeDasharray="3 3" className="opacity-50" />
                    <XAxis 
                      dataKey="date" 
                      tick={{ fontSize: 12 }}
                      angle={-45}
                      textAnchor="end"
                      height={60}
                    />
                    <YAxis
                      yAxisId="left"
                      tick={{ fontSize: 12 }}
                      label={{ value: "Artifact Count", angle: -90, position: "insideLeft" }}
                    />
                    <YAxis
                      yAxisId="right"
                      orientation="right"
                      tick={{ fontSize: 12 }}
                      label={{ value: "Avg Score", angle: 90, position: "insideRight" }}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "var(--popover)",
                        border: "1px solid var(--border)",
                        borderRadius: "var(--radius)",
                      }}
                    />
                    <Legend />
                    <Bar
                      yAxisId="left"
                      dataKey="count"
                      name="Artifact Count"
                      fill="var(--primary)"
                      fillOpacity={0.6}
                      radius={[4, 4, 0, 0]}
                    />
                    <Line
                      yAxisId="right"
                      type="monotone"
                      dataKey="avgScore"
                      name="Avg Discovery Score"
                      stroke="var(--chart-2)"
                      strokeWidth={2}
                      dot={{ r: 3, strokeWidth: 2 }}
                      activeDot={{ r: 5 }}
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="evolution">
          <div className="space-y-4">
            {/* Evolution Events by Type */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
              <EventCard
                icon={TrendingUp}
                type="growth"
                count={growthEvents.length}
                color="text-green-500"
              />
              <EventCard
                icon={GitMerge}
                type="merge"
                count={mergeEvents.length}
                color="text-amber-500"
              />
              <EventCard
                icon={GitBranch}
                type="split"
                count={splitEvents.length}
                color="text-purple-500"
              />
              <EventCard
                icon={TrendingUp}
                type="decline"
                count={declineEvents.length}
                color="text-red-500"
              />
            </div>

            {/* Recent Events Timeline */}
            <Card>
              <CardHeader>
                <CardTitle>Recent Evolution Events</CardTitle>
                <CardDescription>
                  Chronological list of evolution events for this topic
                </CardDescription>
              </CardHeader>
              <CardContent>
                {evolutionLoading ? (
                  <div className="space-y-3">
                    {[...Array(3)].map((_, i) => (
                      <Skeleton key={i} className="h-16 w-full" />
                    ))}
                  </div>
                ) : evolutionEvents.length === 0 ? (
                  <div className="text-center py-8 text-muted-foreground">
                    No evolution events recorded for this topic
                  </div>
                ) : (
                  <div className="space-y-3">
                    {evolutionEvents.slice().sort((a, b) => 
                      new Date(b.eventDate).getTime() - new Date(a.eventDate).getTime()
                    ).map((event) => (
                      <div
                        key={event.id}
                        className="flex items-start gap-4 p-4 rounded-lg border border-border hover:bg-muted/50 transition-colors"
                      >
                        <div className="mt-1">
                          {getEventIcon(event.eventType)}
                        </div>
                        <div className="flex-1">
                          <div className="flex items-center justify-between">
                            <p className="font-medium capitalize">
                              {event.eventType} Event
                            </p>
                            <span className="text-xs text-muted-foreground">
                              {new Date(event.eventDate).toLocaleDateString()}
                            </span>
                          </div>
                          {event.description && (
                            <p className="text-sm text-muted-foreground mt-1">
                              {event.description}
                            </p>
                          )}
                          {event.eventStrength && (
                            <div className="flex items-center gap-2 mt-2">
                              <span className="text-xs text-muted-foreground">
                                Confidence:
                              </span>
                              <div className="h-1.5 w-24 bg-muted rounded-full overflow-hidden">
                                <div
                                  className="h-full bg-primary transition-all"
                                  style={{ width: `${event.eventStrength * 100}%` }}
                                />
                              </div>
                              <span className="text-xs font-medium">
                                {(event.eventStrength * 100).toFixed(0)}%
                              </span>
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="related">
          <Card>
            <CardHeader>
              <CardTitle>Related Topics</CardTitle>
              <CardDescription>
                Topics with similar content and overlapping artifacts
              </CardDescription>
            </CardHeader>
            <CardContent>
              {statsLoading ? (
                <div className="space-y-3">
                  {[...Array(4)].map((_, i) => (
                    <Skeleton key={i} className="h-12 w-full" />
                  ))}
                </div>
              ) : !stats?.relatedTopics || stats.relatedTopics.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  No related topics found
                </div>
              ) : (
                <div className="space-y-3">
                  {stats.relatedTopics.map((topic) => (
                    <div
                      key={topic.id}
                      className="flex items-center justify-between p-4 rounded-lg border border-border hover:bg-muted/50 transition-colors"
                    >
                      <div>
                        <Link
                          to={`/topics/${topic.id}`}
                          className="font-medium text-primary hover:underline"
                        >
                          {topic.name}
                        </Link>
                        {topic.taxonomyPath && (
                          <p className="text-sm text-muted-foreground mt-1">
                            {topic.taxonomyPath}
                          </p>
                        )}
                      </div>
                      <div className="text-right">
                        <Badge variant="outline">
                          {(topic.similarity * 100).toFixed(0)}% similar
                        </Badge>
                      </div>
                    </div>
                  ))}
                </div>
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
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string | number;
  loading: boolean;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{label}</CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">
          {loading ? <Skeleton className="h-7 w-16" /> : value}
        </div>
      </CardContent>
    </Card>
  );
}

function EventCard({
  icon: Icon,
  type,
  count,
  color,
}: {
  icon: React.ComponentType<{ className?: string }>;
  type: string;
  count: number;
  color: string;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-sm font-medium capitalize">{type} Events</CardTitle>
        <Icon className={`h-4 w-4 ${color}`} />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{count}</div>
      </CardContent>
    </Card>
  );
}

function getEventIcon(eventType: string) {
  const baseClass = "h-8 w-8";
  switch (eventType) {
    case "growth":
      return <TrendingUp className={`${baseClass} text-green-500`} />;
    case "merge":
      return <GitMerge className={`${baseClass} text-amber-500`} />;
    case "split":
      return <GitBranch className={`${baseClass} text-purple-500`} />;
    case "decline":
      return <TrendingUp className={`${baseClass} text-red-500`} />;
    default:
      return <Activity className={`${baseClass} text-blue-500`} />;
  }
}

function calculateTrend(points: any[]): number {
  if (points.length < 2) return 0;
  
  const n = points.length;
  const x = Array.from({ length: n }, (_, i) => i);
  const y = points.map((p) => p.count);
  
  const sumX = x.reduce((a, b) => a + b, 0);
  const sumY = y.reduce((a, b) => a + b, 0);
  const sumXY = x.reduce((sum, xi, i) => sum + xi * y[i], 0);
  const sumXX = x.reduce((sum, xi) => sum + xi * xi, 0);
  
  const slope = (n * sumXY - sumX * sumY) / (n * sumXX - sumX * sumX);
  return slope;
}
