import React, { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Badge } from "./ui/badge";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  Legend
} from "recharts";
import { useQuery } from "@tanstack/react-query";
import { getTrendingTopics, getTopicTimeline } from "../api/discoveries";
import { format, parseISO } from "date-fns";
import {
  GitBranch,
  BarChart3,
  TrendingUp,
  Plus,
  X,
  GitCompare,
  Target
} from "lucide-react";

interface ComparativeVisualizationProps {
  className?: string;
}

interface ComparisonItem {
  id: string;
  type: "topic" | "source";
  name: string;
  color: string;
  data?: any[];
}

interface MetricComparison {
  metric: string;
  items: Record<string, number>;
}

const COLORS = ["#3b82f6", "#ef4444", "#10b981", "#f59e0b", "#8b5cf6", "#ec4899"];

export function ComparativeVisualization({ className }: ComparativeVisualizationProps) {
  const [selectedTopics, setSelectedTopics] = useState<string[]>([]);
  const [topicSearch, setTopicSearch] = useState("");
  const [comparisonType, setComparisonType] = useState<"timeline" | "metrics" | "distribution">("timeline");
  const [comparisons, setComparisons] = useState<ComparisonItem[]>([]);
  const [timeWindow, setTimeWindow] = useState(14);

  const { data: trendingTopics } = useQuery({
    queryKey: ["trending-topics"],
    queryFn: () => getTrendingTopics({ limit: 50 }),
  });

  const filteredTopics = trendingTopics?.filter(topic =>
    topic.name.toLowerCase().includes(topicSearch.toLowerCase()) &&
    !selectedTopics.includes(topic.name)
  ) || [];

  const addTopicComparison = async (topicName: string) => {
    if (selectedTopics.includes(topicName) || comparisons.length >= 6) return;

    const color = COLORS[comparisons.length % COLORS.length];

    // Fetch timeline data for the topic
    try {
      const timelineData = await getTopicTimeline({
        topic: topicName,
        days: timeWindow
      });

      const newComparison: ComparisonItem = {
        id: `topic-${topicName}`,
        type: "topic",
        name: topicName,
        color,
        data: timelineData
      };

      setComparisons(prev => [...prev, newComparison]);
      setSelectedTopics(prev => [...prev, topicName]);
    } catch (error) {
      console.error("Error fetching topic timeline:", error);
    }
  };

  const removeComparison = (id: string) => {
    const comparison = comparisons.find(c => c.id === id);
    if (comparison?.type === "topic") {
      setSelectedTopics(prev => prev.filter(t => t !== comparison.name));
    }
    setComparisons(prev => prev.filter(c => c.id !== id));
  };

  const clearAll = () => {
    setComparisons([]);
    setSelectedTopics([]);
  };

  // Prepare data for timeline comparison
  const timelineChartData = React.useMemo(() => {
    if (comparisons.length === 0) return [];

    // Get all unique dates
    const allDates = new Set<string>();
    comparisons.forEach(comp => {
      comp.data?.forEach((point: any) => allDates.add(point.date));
    });

    // Sort dates
    const sortedDates = Array.from(allDates).sort();

    // Build chart data
    return sortedDates.map(date => {
      const dataPoint: any = { date };

      comparisons.forEach(comp => {
        const point = comp.data?.find((p: any) => p.date === date);
        dataPoint[comp.name] = point ? point.count : 0;
      });

      return dataPoint;
    });
  }, [comparisons]);

  // Prepare data for metrics comparison
  const metricsData = React.useMemo((): MetricComparison[] => {
    const metrics = ["novelty", "emergence", "obscurity", "discoveryScore"];

    return metrics.map(metric => {
      const items: Record<string, number> = {};

      comparisons.forEach(comp => {
        // Mock metric values based on topic characteristics
        const baseValues: Record<string, Record<string, number>> = {
          "quantum computing": { novelty: 85, emergence: 70, obscurity: 80, discoveryScore: 78 },
          "machine learning": { novelty: 70, emergence: 85, obscurity: 60, discoveryScore: 72 },
          "robotics": { novelty: 75, emergence: 75, obscurity: 70, discoveryScore: 73 },
          "photonics": { novelty: 90, emergence: 65, obscurity: 85, discoveryScore: 80 },
          "protein folding": { novelty: 80, emergence: 80, obscurity: 75, discoveryScore: 78 },
        };

        const topicMetrics = baseValues[comp.name] || {
          novelty: 60 + Math.random() * 30,
          emergence: 60 + Math.random() * 30,
          obscurity: 60 + Math.random() * 30,
          discoveryScore: 60 + Math.random() * 30,
        };

        items[comp.name] = topicMetrics[metric];
      });

      return { metric, items };
    });
  }, [comparisons]);

  return (
    <Card className={className}>
      <CardHeader>
        <div className="flex justify-between items-center">
          <CardTitle className="flex items-center gap-2">
            <GitCompare className="h-5 w-5" />
            Comparative Analysis
          </CardTitle>
          {comparisons.length > 0 && (
            <Button variant="outline" size="sm" onClick={clearAll}>
              Clear All
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Topic Selection */}
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <Target className="h-4 w-4 text-muted-foreground" />
            <h3 className="font-semibold">Select Topics to Compare</h3>
          </div>

          <div className="flex gap-2">
            <Input
              placeholder="Search topics..."
              value={topicSearch}
              onChange={(e) => setTopicSearch(e.target.value)}
              className="flex-1"
            />
          </div>

          <div className="flex flex-wrap gap-2">
            {filteredTopics.slice(0, 10).map(topic => (
              <Button
                key={topic.name}
                variant="outline"
                size="sm"
                onClick={() => addTopicComparison(topic.name)}
                className="flex items-center gap-1"
              >
                <Plus className="h-3 w-3" />
                {topic.name}
                <Badge variant="secondary" className="ml-1">
                  {topic.artifactCount}
                </Badge>
              </Button>
            ))}
          </div>

          {/* Selected Comparisons */}
          {comparisons.length > 0 && (
            <div className="flex flex-wrap gap-2 pt-2 border-t">
              {comparisons.map(comp => (
                <Badge
                  key={comp.id}
                  variant="outline"
                  className="flex items-center gap-1"
                  style={{
                    borderColor: comp.color,
                    backgroundColor: `${comp.color}20`
                  }}
                >
                  <span
                    className="w-2 h-2 rounded-full"
                    style={{ backgroundColor: comp.color }}
                  />
                  {comp.name}
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-4 w-4 p-0 ml-1 hover:bg-transparent"
                    onClick={() => removeComparison(comp.id)}
                  >
                    <X className="h-3 w-3" />
                  </Button>
                </Badge>
              ))}
            </div>
          )}
        </div>

        {/* Comparison Type Selection */}
        {comparisons.length > 0 && (
          <div className="flex gap-2">
            <Button
              variant={comparisonType === "timeline" ? "default" : "outline"}
              size="sm"
              onClick={() => setComparisonType("timeline")}
              className="flex items-center gap-1"
            >
              <TrendingUp className="h-3 w-3" />
              Timeline
            </Button>
            <Button
              variant={comparisonType === "metrics" ? "default" : "outline"}
              size="sm"
              onClick={() => setComparisonType("metrics")}
              className="flex items-center gap-1"
            >
              <BarChart3 className="h-3 w-3" />
              Metrics
            </Button>
            <Button
              variant={comparisonType === "distribution" ? "default" : "outline"}
              size="sm"
              onClick={() => setComparisonType("distribution")}
              className="flex items-center gap-1"
            >
              <GitBranch className="h-3 w-3" />
              Distribution
            </Button>
          </div>
        )}

        {/* Charts */}
        {comparisons.length > 0 && (
          <div className="space-y-6">
            {comparisonType === "timeline" && (
              <div className="space-y-4">
                <div className="flex justify-between items-center">
                  <h4 className="font-semibold">Activity Timeline</h4>
                  <div className="flex gap-2">
                    <Button
                      variant={timeWindow === 7 ? "default" : "outline"}
                      size="sm"
                      onClick={() => setTimeWindow(7)}
                    >
                      7 days
                    </Button>
                    <Button
                      variant={timeWindow === 14 ? "default" : "outline"}
                      size="sm"
                      onClick={() => setTimeWindow(14)}
                    >
                      14 days
                    </Button>
                    <Button
                      variant={timeWindow === 30 ? "default" : "outline"}
                      size="sm"
                      onClick={() => setTimeWindow(30)}
                    >
                      30 days
                    </Button>
                  </div>
                </div>

                <div className="h-96">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={timelineChartData}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis
                        dataKey="date"
                        tickFormatter={(value) => format(parseISO(value), 'MMM dd')}
                      />
                      <YAxis />
                      <Tooltip
                        labelFormatter={(value) => format(parseISO(value as string), 'MMM dd, yyyy')}
                      />
                      <Legend />
                      {comparisons.map(comp => (
                        <Line
                          key={comp.id}
                          type="monotone"
                          dataKey={comp.name}
                          stroke={comp.color}
                          strokeWidth={2}
                          dot={false}
                          name={comp.name}
                        />
                      ))}
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}

            {comparisonType === "metrics" && (
              <div className="space-y-4">
                <h4 className="font-semibold">Metrics Comparison</h4>

                <div className="h-96">
                  <ResponsiveContainer width="100%" height="100%">
                    <RadarChart data={metricsData}>
                      <PolarGrid />
                      <PolarAngleAxis dataKey="metric" />
                      <PolarRadiusAxis angle={90} domain={[0, 100]} />
                      {comparisons.map(comp => (
                        <Radar
                          key={comp.id}
                          name={comp.name}
                          dataKey={(data: any) => data.items[comp.name] || 0}
                          stroke={comp.color}
                          fill={comp.color}
                          fillOpacity={0.3}
                        />
                      ))}
                      <Legend />
                    </RadarChart>
                  </ResponsiveContainer>
                </div>

                {/* Metrics Table */}
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b">
                        <th className="text-left py-2">Metric</th>
                        {comparisons.map(comp => (
                          <th key={comp.id} className="text-center py-2" style={{ color: comp.color }}>
                            {comp.name}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {metricsData.map(row => (
                        <tr key={row.metric} className="border-b">
                          <td className="py-2 capitalize">{row.metric.replace(/([A-Z])/g, ' $1').trim()}</td>
                          {comparisons.map(comp => (
                            <td key={comp.id} className="text-center py-2">
                              {row.items[comp.name]?.toFixed(1) || 0}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {comparisonType === "distribution" && (
              <div className="space-y-4">
                <h4 className="font-semibold">Score Distribution</h4>

                <div className="grid gap-4 md:grid-cols-2">
                  {comparisons.map(comp => {
                    // Generate mock distribution data
                    const distribution = Array.from({ length: 10 }, (_, i) => ({
                      range: `${i * 10}-${(i + 1) * 10}`,
                      count: Math.floor(Math.random() * 20) + (i === 7 || i === 8 ? 15 : 0), // More in 70-90 range
                    }));

                    return (
                      <Card key={comp.id}>
                        <CardHeader>
                          <CardTitle className="text-sm font-medium flex items-center gap-2">
                            <span
                              className="w-3 h-3 rounded-full"
                              style={{ backgroundColor: comp.color }}
                            />
                            {comp.name}
                          </CardTitle>
                        </CardHeader>
                        <CardContent>
                          <div className="h-48">
                            <ResponsiveContainer width="100%" height="100%">
                              <BarChart data={distribution}>
                                <CartesianGrid strokeDasharray="3 3" />
                                <XAxis dataKey="range" tick={{ fontSize: 10 }} />
                                <YAxis />
                                <Tooltip />
                                <Bar dataKey="count" fill={comp.color} />
                              </BarChart>
                            </ResponsiveContainer>
                          </div>
                        </CardContent>
                      </Card>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Empty State */}
        {comparisons.length === 0 && (
          <div className="text-center py-12 text-muted-foreground">
            <GitCompare className="h-12 w-12 mx-auto mb-4 text-muted-foreground/50" />
            <h3 className="text-lg font-semibold mb-2">No comparisons selected</h3>
            <p>Search and select topics above to start comparing</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}