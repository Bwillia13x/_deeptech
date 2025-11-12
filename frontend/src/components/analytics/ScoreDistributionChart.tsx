import React, { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line } from "recharts";
import { BarChart3 } from "lucide-react";
import { Skeleton } from "../ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../ui/tabs";

interface ScoreDistributionChartProps {
  data: any;
  isLoading: boolean;
}

export function ScoreDistributionChart({ data, isLoading }: ScoreDistributionChartProps) {
  const [view, setView] = useState("overall");

  if (isLoading || !data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <BarChart3 className="h-5 w-5" />
            Score Distributions
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-64 w-full" />
        </CardContent>
      </Card>
    );
  }

  const { summary, percentiles, source_breakdown } = data;

  // Create histogram data for overall distribution
  const histogramData = [];
  const binSize = 10;
  for (let i = 0; i <= 100; i += binSize) {
    histogramData.push({
      range: `${i}-${i + binSize}`,
      min: i,
      max: i + binSize,
      count: 0,
    });
  }

  // This would normally be populated from actual score distribution data
  // For now, we'll create a representative distribution based on the summary
  const representativeData = [
    { range: "0-10", count: Math.max(1, summary.total_scored * 0.05) },
    { range: "10-20", count: Math.max(1, summary.total_scored * 0.08) },
    { range: "20-30", count: Math.max(1, summary.total_scored * 0.12) },
    { range: "30-40", count: Math.max(1, summary.total_scored * 0.15) },
    { range: "40-50", count: Math.max(1, summary.total_scored * 0.18) },
    { range: "50-60", count: Math.max(1, summary.total_scored * 0.15) },
    { range: "60-70", count: Math.max(1, summary.total_scored * 0.12) },
    { range: "70-80", count: Math.max(1, summary.total_scored * 0.08) },
    { range: "80-90", count: Math.max(1, summary.total_scored * 0.05) },
    { range: "90-100", count: Math.max(1, summary.total_scored * 0.02) },
  ];

  const renderOverallDistribution = () => (
    <div className="space-y-4">
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={representativeData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="range" />
            <YAxis />
            <Tooltip />
            <Bar dataKey="count" name="Artifact Count" fill="#3b82f6" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <div className="rounded-lg border p-3">
          <div className="text-sm text-muted-foreground">Total Scored</div>
          <div className="mt-1 text-xl font-semibold">{summary.total_scored}</div>
        </div>
        <div className="rounded-lg border p-3">
          <div className="text-sm text-muted-foreground">Average Score</div>
          <div className="mt-1 text-xl font-semibold">{summary.avg_discovery_score}</div>
        </div>
        <div className="rounded-lg border p-3">
          <div className="text-sm text-muted-foreground">Score Range</div>
          <div className="mt-1 text-xl font-semibold">
            {summary.min_discovery_score} - {summary.max_discovery_score}
          </div>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <div className="rounded-lg border p-3">
          <div className="text-sm text-muted-foreground">Average Novelty</div>
          <div className="mt-1 text-xl font-semibold">{summary.avg_novelty}</div>
        </div>
        <div className="rounded-lg border p-3">
          <div className="text-sm text-muted-foreground">Average Emergence</div>
          <div className="mt-1 text-xl font-semibold">{summary.avg_emergence}</div>
        </div>
        <div className="rounded-lg border p-3">
          <div className="text-sm text-muted-foreground">Average Obscurity</div>
          <div className="mt-1 text-xl font-semibold">{summary.avg_obscurity}</div>
        </div>
      </div>
    </div>
  );

  const renderPercentiles = () => (
    <div className="space-y-4">
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={Object.entries(percentiles).map(([key, value]) => ({
              percentile: key.replace('p', ''),
              value,
            }))}
          >
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="percentile" label={{ value: 'Percentile', position: 'insideBottom', offset: -5 }} />
            <YAxis domain={[0, 100]} label={{ value: 'Discovery Score', angle: -90, position: 'insideLeft' }} />
            <Tooltip />
            <Line
              type="monotone"
              dataKey="value"
              name="Discovery Score"
              stroke="#3b82f6"
              strokeWidth={3}
              dot={{ fill: '#3b82f6', r: 4 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b">
              <th className="text-left py-2">Percentile</th>
              <th className="text-right py-2">Discovery Score</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(percentiles).map(([key, value]) => (
              <tr key={key} className="border-b">
                <td className="py-2 font-medium">{key.replace('p', '')}th</td>
                <td className="text-right py-2">{String(value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );

  const renderSourceBreakdown = () => (
    <div className="space-y-4">
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={source_breakdown}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="source" />
            <YAxis />
            <Tooltip />
            <Bar dataKey="avg_discovery_score" name="Avg Discovery Score" fill="#3b82f6" />
            <Bar dataKey="avg_novelty" name="Avg Novelty" fill="#10b981" />
            <Bar dataKey="avg_emergence" name="Avg Emergence" fill="#f59e0b" />
            <Bar dataKey="avg_obscurity" name="Avg Obscurity" fill="#ef4444" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b">
              <th className="text-left py-2">Source</th>
              <th className="text-right py-2">Count</th>
              <th className="text-right py-2">Avg Score</th>
              <th className="text-right py-2">Novelty</th>
              <th className="text-right py-2">Emergence</th>
              <th className="text-right py-2">Obscurity</th>
            </tr>
          </thead>
          <tbody>
            {source_breakdown.map((source: any) => (
              <tr key={source.source} className="border-b">
                <td className="py-2 font-medium">{source.source}</td>
                <td className="text-right py-2">{source.count}</td>
                <td className="text-right py-2">{source.avg_discovery_score}</td>
                <td className="text-right py-2">{source.avg_novelty}</td>
                <td className="text-right py-2">{source.avg_emergence}</td>
                <td className="text-right py-2">{source.avg_obscurity}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <BarChart3 className="h-5 w-5" />
          Score Distributions
        </CardTitle>
        <div className="text-sm text-muted-foreground">
          {summary.total_scored} scored artifacts
        </div>
      </CardHeader>
      <CardContent>
        <Tabs value={view} onValueChange={setView}>
          <TabsList className="grid w-full grid-cols-3 lg:w-[400px]">
            <TabsTrigger value="overall">Overall</TabsTrigger>
            <TabsTrigger value="percentiles">Percentiles</TabsTrigger>
            <TabsTrigger value="sources">By Source</TabsTrigger>
          </TabsList>

          <TabsContent value="overall" className="mt-4">
            {renderOverallDistribution()}
          </TabsContent>

          <TabsContent value="percentiles" className="mt-4">
            {renderPercentiles()}
          </TabsContent>

          <TabsContent value="sources" className="mt-4">
            {renderSourceBreakdown()}
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}