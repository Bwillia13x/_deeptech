import React, { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/tabs";
import { Button } from "./ui/button";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";
import { useQuery } from "@tanstack/react-query";
import { getDiscoveryStats } from "../api/discoveries";
import { format, parseISO } from "date-fns";
import { Calendar, BarChart3, PieChartIcon, Activity } from "lucide-react";

interface DiscoveryChartsProps {
  className?: string;
}

interface TimeSeriesData {
  date: string;
  arxiv: number;
  github: number;
  x: number;
  facebook: number;
  total: number;
  avgScore: number;
}

interface SourceData {
  source: string;
  count: number;
  avgScore: number;
  fill?: string;
}

interface TopicData {
  topic: string;
  count: number;
  avgScore: number;
}

const COLORS = {
  arxiv: "#e74c3c",
  github: "#2c3e50",
  x: "#1da1f2",
  facebook: "#1877f2",
  reddit: "#ff4500",
  hackernews: "#ffb347",
  score: "#27ae60",
};

export function DiscoveryCharts({ className }: DiscoveryChartsProps) {
  const [timeWindow, setTimeWindow] = useState(14); // days
  const [selectedSources, setSelectedSources] = useState<string[]>(["arxiv", "github", "x", "facebook"]);

  const { data: stats } = useQuery({
    queryKey: ["discovery-stats"],
    queryFn: getDiscoveryStats,
  });

  // Generate mock time series data
  const timeSeriesData: TimeSeriesData[] = generateTimeSeriesData(timeWindow, selectedSources);
  
  // Generate source distribution data
  const sourceData: SourceData[] = generateSourceData(stats, selectedSources);
  
  // Generate topic data
  const topicData: TopicData[] = generateTopicData(stats);

  const toggleSource = (source: string) => {
    setSelectedSources(prev => 
      prev.includes(source) 
        ? prev.filter(s => s !== source)
        : [...prev, source]
    );
  };

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Activity className="h-5 w-5" />
          Discovery Analytics
        </CardTitle>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue="timeline">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="timeline" className="flex items-center gap-2">
              <Calendar className="h-4 w-4" />
              Timeline
            </TabsTrigger>
            <TabsTrigger value="sources" className="flex items-center gap-2">
              <PieChartIcon className="h-4 w-4" />
              Sources
            </TabsTrigger>
            <TabsTrigger value="topics" className="flex items-center gap-2">
              <BarChart3 className="h-4 w-4" />
              Topics
            </TabsTrigger>
          </TabsList>

          <TabsContent value="timeline" className="space-y-4">
            <div className="flex justify-between items-center">
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
              
              <div className="flex gap-1">
                {Object.entries(COLORS).slice(0, 4).map(([source, color]) => (
                  <Button
                    key={source}
                    variant="outline"
                    size="sm"
                    onClick={() => toggleSource(source)}
                    className={`${
                      selectedSources.includes(source) ? '' : 'opacity-50'
                    }`}
                    style={{ borderColor: selectedSources.includes(source) ? color : undefined }}
                  >
                    <span 
                      className="w-2 h-2 rounded-full mr-1" 
                      style={{ backgroundColor: color }}
                    />
                    {source}
                  </Button>
                ))}
              </div>
            </div>

            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={timeSeriesData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis 
                    dataKey="date" 
                    tickFormatter={(value) => format(parseISO(value), 'MMM dd')}
                  />
                  <YAxis yAxisId="left" />
                  <YAxis yAxisId="right" orientation="right" />
                  <Tooltip 
                    labelFormatter={(value) => format(parseISO(value as string), 'MMM dd, yyyy')}
                  />
                  <Legend />
                  
                  {selectedSources.includes("arxiv") && (
                    <Area
                      yAxisId="left"
                      type="monotone"
                      dataKey="arxiv"
                      stroke={COLORS.arxiv}
                      fill={`${COLORS.arxiv}20`}
                      name="arXiv"
                    />
                  )}
                  
                  {selectedSources.includes("github") && (
                    <Area
                      yAxisId="left"
                      type="monotone"
                      dataKey="github"
                      stroke={COLORS.github}
                      fill={`${COLORS.github}20`}
                      name="GitHub"
                    />
                  )}
                  
                  {selectedSources.includes("x") && (
                    <Area
                      yAxisId="left"
                      type="monotone"
                      dataKey="x"
                      stroke={COLORS.x}
                      fill={`${COLORS.x}20`}
                      name="X/Twitter"
                    />
                  )}
                  
                  {selectedSources.includes("facebook") && (
                    <Area
                      yAxisId="left"
                      type="monotone"
                      dataKey="facebook"
                      stroke={COLORS.facebook}
                      fill={`${COLORS.facebook}20`}
                      name="Facebook"
                    />
                  )}
                  
                  <Area
                    yAxisId="right"
                    type="monotone"
                    dataKey="avgScore"
                    stroke={COLORS.score}
                    fill={`${COLORS.score}20`}
                    name="Avg Score"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </TabsContent>

          <TabsContent value="sources" className="space-y-4">
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={sourceData}
                    cx="50%"
                    cy="50%"
                    labelLine={false}
                    label={(entry) => `${entry.source}: ${entry.count}`}
                    outerRadius={80}
                    fill="#8884d8"
                    dataKey="count"
                  >
                    {sourceData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.fill} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </div>
            
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
              {sourceData.map((source) => (
                <Card key={source.source}>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium">
                      {source.source.charAt(0).toUpperCase() + source.source.slice(1)}
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold">{source.count}</div>
                    <p className="text-xs text-muted-foreground">
                      Avg Score: {source.avgScore.toFixed(1)}
                    </p>
                  </CardContent>
                </Card>
              ))}
            </div>
          </TabsContent>

          <TabsContent value="topics" className="space-y-4">
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={topicData} layout="horizontal">
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" />
                  <YAxis 
                    dataKey="topic" 
                    type="category" 
                    width={120}
                    tick={{ fontSize: 12 }}
                  />
                  <Tooltip />
                  <Bar dataKey="count" fill="#3b82f6" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}

// Helper functions to generate mock data
function generateTimeSeriesData(days: number, selectedSources: string[]): TimeSeriesData[] {
  const data: TimeSeriesData[] = [];
  const now = new Date();
  
  for (let i = days - 1; i >= 0; i--) {
    const date = new Date(now);
    date.setDate(date.getDate() - i);
    
    const dayData: TimeSeriesData = {
      date: date.toISOString().split('T')[0],
      arxiv: 0,
      github: 0,
      x: 0,
      facebook: 0,
      total: 0,
      avgScore: 0,
    };
    
    let totalScore = 0;
    let totalCount = 0;
    
    // Generate data for each source
    if (selectedSources.includes("arxiv")) {
      const base = 8 + Math.sin(i / 4) * 4;
      const random = Math.random() * 3;
      dayData.arxiv = Math.max(0, Math.round(base + random));
      totalCount += dayData.arxiv;
      totalScore += dayData.arxiv * (65 + Math.random() * 25);
    }
    
    if (selectedSources.includes("github")) {
      const base = 6 + Math.sin(i / 5) * 3;
      const random = Math.random() * 4;
      dayData.github = Math.max(0, Math.round(base + random));
      totalCount += dayData.github;
      totalScore += dayData.github * (60 + Math.random() * 30);
    }
    
    if (selectedSources.includes("x")) {
      const base = 4 + Math.sin(i / 3) * 2;
      const random = Math.random() * 3;
      dayData.x = Math.max(0, Math.round(base + random));
      totalCount += dayData.x;
      totalScore += dayData.x * (55 + Math.random() * 20);
    }
    
    if (selectedSources.includes("facebook")) {
      const base = 3 + Math.sin(i / 6) * 2;
      const random = Math.random() * 2;
      dayData.facebook = Math.max(0, Math.round(base + random));
      totalCount += dayData.facebook;
      totalScore += dayData.facebook * (50 + Math.random() * 25);
    }
    
    dayData.total = dayData.arxiv + dayData.github + dayData.x + dayData.facebook;
    dayData.avgScore = totalCount > 0 ? totalScore / totalCount : 0;
    
    data.push(dayData);
  }
  
  return data;
}

function generateSourceData(stats: any, selectedSources: string[]): SourceData[] {
  const defaultSources: SourceData[] = [
    { source: "arxiv", count: 650, avgScore: 72.5, fill: COLORS.arxiv },
    { source: "github", count: 420, avgScore: 68.3, fill: COLORS.github },
    { source: "x", count: 180, avgScore: 55.7, fill: COLORS.x },
    { source: "facebook", count: 85, avgScore: 52.1, fill: COLORS.facebook },
  ];

  const combined = new Map(defaultSources.map((item) => [item.source, item]));

  (stats?.sources ?? []).forEach((entry: { source: string; count: number }) => {
    const existing = combined.get(entry.source);
    combined.set(entry.source, {
      source: entry.source,
      count: entry.count ?? existing?.count ?? 0,
      avgScore: existing?.avgScore ?? 0,
      fill: existing?.fill ?? COLORS[entry.source as keyof typeof COLORS] ?? "#8b5cf6",
    });
  });

  return Array.from(combined.values())
    .filter((source) => selectedSources.includes(source.source))
    .map((source) => ({
      source: source.source,
      count: source.count,
      avgScore: source.avgScore,
      fill: source.fill,
    }));
}

function generateTopicData(stats: any): TopicData[] {
  if (stats?.topTopics?.length) {
    return stats.topTopics.map((topic: any) => ({
      topic: topic.name,
      count: topic.count,
      avgScore: topic.avgDiscoveryScore ?? 0,
    }));
  }

  return [
    { topic: "quantum computing", count: 23, avgScore: 78.5 },
    { topic: "machine learning", count: 18, avgScore: 65.2 },
    { topic: "robotics", count: 15, avgScore: 71.8 },
    { topic: "photonics", count: 12, avgScore: 82.3 },
    { topic: "protein folding", count: 8, avgScore: 68.7 },
    { topic: "optimization", count: 7, avgScore: 62.4 },
    { topic: "computer vision", count: 6, avgScore: 58.9 },
    { topic: "deep learning", count: 5, avgScore: 64.1 },
  ];
}
