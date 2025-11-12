import React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend } from "recharts";
import { Database } from "lucide-react";
import { Skeleton } from "../ui/skeleton";

interface SourceDistributionChartProps {
  data: any;
  isLoading: boolean;
  detailed?: boolean;
}

const COLORS = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899"];

export function SourceDistributionChart({ data, isLoading, detailed = false }: SourceDistributionChartProps) {
  if (isLoading || !data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Database className="h-5 w-5" />
            Source Distribution
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-64 w-full" />
        </CardContent>
      </Card>
    );
  }

  const { sources, total_artifacts, time_window } = data;

  // Prepare data for charts
  const chartData = sources.map((source: any) => ({
    source: source.source,
    count: source.count,
    percentage: source.percentage,
    avg_score: source.avg_discovery_score,
    avg_novelty: source.avg_novelty,
    avg_emergence: source.avg_emergence,
    avg_obscurity: source.avg_obscurity,
  }));

  const renderSimpleView = () => (
    <div className="grid gap-4 lg:grid-cols-2">
      {/* Pie Chart */}
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={chartData}
              dataKey="count"
              nameKey="source"
              cx="50%"
              cy="50%"
              outerRadius={80}
              label={({ source, percent }) => `${source}: ${(percent * 100).toFixed(0)}%`}
            >
              {chartData.map((entry: any, index: number) => (
                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip />
            <Legend />
          </PieChart>
        </ResponsiveContainer>
      </div>

      {/* Summary Stats */}
      <div className="space-y-3">
        <div className="text-sm text-muted-foreground">
          Total artifacts: <span className="font-semibold">{total_artifacts}</span>
        </div>
        {sources.slice(0, 5).map((source: any, idx: number) => (
          <div key={source.source} className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div
                className="w-3 h-3 rounded-full"
                style={{ backgroundColor: COLORS[idx % COLORS.length] }}
              />
              <span className="font-medium">{source.source}</span>
            </div>
            <div className="text-sm text-muted-foreground">
              {source.count} ({source.percentage}%)
            </div>
          </div>
        ))}
        {sources.length > 5 && (
          <div className="text-sm text-muted-foreground">
            +{sources.length - 5} more sources
          </div>
        )}
      </div>
    </div>
  );

  const renderDetailedView = () => (
    <div className="space-y-6">
      {/* Summary */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-lg border p-4">
          <div className="text-sm text-muted-foreground">Total Artifacts</div>
          <div className="mt-2 text-2xl font-semibold">{total_artifacts}</div>
        </div>
        <div className="rounded-lg border p-4">
          <div className="text-sm text-muted-foreground">Time Window</div>
          <div className="mt-2 text-2xl font-semibold">{time_window}</div>
        </div>
        <div className="rounded-lg border p-4">
          <div className="text-sm text-muted-foreground">Sources Tracked</div>
          <div className="mt-2 text-2xl font-semibold">{sources.length}</div>
        </div>
        <div className="rounded-lg border p-4">
          <div className="text-sm text-muted-foreground">Top Source</div>
          <div className="mt-2 text-2xl font-semibold">
            {sources[0]?.source} ({sources[0]?.percentage}%)
          </div>
        </div>
      </div>

      {/* Bar Chart */}
      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="source" />
            <YAxis />
            <Tooltip />
            <Legend />
            <Bar dataKey="count" name="Artifact Count" fill="#3b82f6" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Detailed Metrics Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b">
              <th className="text-left py-2">Source</th>
              <th className="text-right py-2">Count</th>
              <th className="text-right py-2">Percentage</th>
              <th className="text-right py-2">Avg Score</th>
              <th className="text-right py-2">Novelty</th>
              <th className="text-right py-2">Emergence</th>
              <th className="text-right py-2">Obscurity</th>
            </tr>
          </thead>
          <tbody>
            {sources.map((source: any) => (
              <tr key={source.source} className="border-b">
                <td className="py-2 font-medium">{source.source}</td>
                <td className="text-right py-2">{source.count}</td>
                <td className="text-right py-2">{source.percentage}%</td>
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
          <Database className="h-5 w-5" />
          Source Distribution
        </CardTitle>
        <div className="text-sm text-muted-foreground">
          {total_artifacts} artifacts from {sources.length} sources ({time_window})
        </div>
      </CardHeader>
      <CardContent>
        {detailed ? renderDetailedView() : renderSimpleView()}
      </CardContent>
    </Card>
  );
}