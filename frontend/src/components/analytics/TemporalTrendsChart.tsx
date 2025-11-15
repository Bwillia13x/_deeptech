import React, { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar } from "recharts";
import { TrendingUp } from "lucide-react";
import { Skeleton } from "../ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../ui/tabs";

interface TemporalTrendsChartProps {
  data: any;
  isLoading: boolean;
}

export function TemporalTrendsChart({ data, isLoading }: TemporalTrendsChartProps) {
  const [view, setView] = useState("artifacts");

  if (isLoading || !data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <TrendingUp className="h-5 w-5" />
            Temporal Trends
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-80 w-full" />
        </CardContent>
      </Card>
    );
  }

  const { daily_trends, days, summary } = data;

  // Prepare data for charts
  const dates = Object.keys(daily_trends).sort();
  
  const chartData = dates.map((date) => {
    const dayData = daily_trends[date];
    const sources = dayData.sources;
    
    return {
      date,
      total: dayData.totals.count,
      avg_score: dayData.totals.avg_score,
      arxiv: sources.arxiv?.count || 0,
      github: sources.github?.count || 0,
      x: sources.x?.count || 0,
      facebook: sources.facebook?.count || 0,
      arxiv_score: sources.arxiv?.avg_discovery_score || 0,
      github_score: sources.github?.avg_discovery_score || 0,
      x_score: sources.x?.avg_discovery_score || 0,
      facebook_score: sources.facebook?.avg_discovery_score || 0,
    };
  });

  const renderArtifactTrends = () => (
    <div className="h-80">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis 
            dataKey="date" 
            tickFormatter={(value) => {
              const date = new Date(value);
              return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
            }}
          />
          <YAxis />
          <Tooltip 
            labelFormatter={(value) => {
              const date = new Date(value);
              return date.toLocaleDateString('en-US', { 
                weekday: 'long', 
                year: 'numeric', 
                month: 'long', 
                day: 'numeric' 
              });
            }}
          />
          <Line type="monotone" dataKey="total" name="Total" stroke="#3b82f6" strokeWidth={2} />
          <Line type="monotone" dataKey="arxiv" name="arXiv" stroke="#10b981" strokeWidth={2} />
          <Line type="monotone" dataKey="github" name="GitHub" stroke="#f59e0b" strokeWidth={2} />
          <Line type="monotone" dataKey="x" name="X/Twitter" stroke="#ef4444" strokeWidth={2} />
          <Line type="monotone" dataKey="facebook" name="Facebook" stroke="#8b5cf6" strokeWidth={2} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );

  const renderScoreTrends = () => (
    <div className="h-80">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis 
            dataKey="date" 
            tickFormatter={(value) => {
              const date = new Date(value);
              return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
            }}
          />
          <YAxis domain={[0, 100]} />
          <Tooltip 
            labelFormatter={(value) => {
              const date = new Date(value);
              return date.toLocaleDateString('en-US', { 
                weekday: 'long', 
                year: 'numeric', 
                month: 'long', 
                day: 'numeric' 
              });
            }}
          />
          <Line type="monotone" dataKey="avg_score" name="Overall Avg" stroke="#3b82f6" strokeWidth={3} dot={false} />
          <Line type="monotone" dataKey="arxiv_score" name="arXiv Avg" stroke="#10b981" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="github_score" name="GitHub Avg" stroke="#f59e0b" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="x_score" name="X/Twitter Avg" stroke="#ef4444" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="facebook_score" name="Facebook Avg" stroke="#8b5cf6" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );

  const renderWeeklyAggregation = () => {
    // Aggregate by week
    const weeklyData = [];
    for (let i = 0; i < chartData.length; i += 7) {
      const weekData = chartData.slice(i, i + 7);
      if (weekData.length > 0) {
        const weekSum = weekData.reduce((acc, day) => ({
          total: acc.total + day.total,
          arxiv: acc.arxiv + day.arxiv,
          github: acc.github + day.github,
          x: acc.x + day.x,
          facebook: acc.facebook + day.facebook,
        }), { total: 0, arxiv: 0, github: 0, x: 0, facebook: 0 });
        
        weeklyData.push({
          week: `Week ${Math.floor(i / 7) + 1}`,
          ...weekSum,
        });
      }
    }

    return (
      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={weeklyData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="week" />
            <YAxis />
            <Tooltip />
            <Bar dataKey="arxiv" name="arXiv" fill="#10b981" />
            <Bar dataKey="github" name="GitHub" fill="#f59e0b" />
            <Bar dataKey="x" name="X/Twitter" fill="#ef4444" />
            <Bar dataKey="facebook" name="Facebook" fill="#8b5cf6" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    );
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <TrendingUp className="h-5 w-5" />
          Temporal Trends
        </CardTitle>
        <div className="text-sm text-muted-foreground">
          {summary.total_artifacts} artifacts over {days} days
          <div className="mt-1 text-xs">
            Avg daily: {summary.avg_daily_artifacts} artifacts
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <Tabs value={view} onValueChange={setView}>
          <TabsList className="grid w-full grid-cols-3 lg:w-[400px]">
            <TabsTrigger value="artifacts">Artifacts</TabsTrigger>
            <TabsTrigger value="scores">Scores</TabsTrigger>
            <TabsTrigger value="weekly">Weekly</TabsTrigger>
          </TabsList>
          
          <TabsContent value="artifacts" className="mt-4">
            {renderArtifactTrends()}
          </TabsContent>
          
          <TabsContent value="scores" className="mt-4">
            {renderScoreTrends()}
          </TabsContent>
          
          <TabsContent value="weekly" className="mt-4">
            {renderWeeklyAggregation()}
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}
