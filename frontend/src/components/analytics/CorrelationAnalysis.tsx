import React, { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { Skeleton } from "../ui/skeleton";
import { Badge } from "../ui/badge";
import { Network, Filter } from "lucide-react";
import { Input } from "../ui/input";
import { Button } from "../ui/button";

interface CorrelationAnalysisProps {
  data: any;
  isLoading: boolean;
}

export function CorrelationAnalysis({ data, isLoading }: CorrelationAnalysisProps) {
  const [minSources, setMinSources] = useState(2);
  const [searchTerm, setSearchTerm] = useState("");

  if (isLoading || !data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Network className="h-5 w-5" />
            Cross-Source Correlations
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-64 w-full" />
        </CardContent>
      </Card>
    );
  }

  const { correlations, time_window, summary } = data;

  // Filter correlations based on user input
  const filteredCorrelations = correlations.filter((corr: any) => {
    const matchesMinSources = corr.source_count >= minSources;
    const matchesSearch = searchTerm === "" || 
      corr.topic.toLowerCase().includes(searchTerm.toLowerCase());
    return matchesMinSources && matchesSearch;
  });

  const renderCorrelationCard = (correlation: any) => {
    const sources = Object.entries(correlation.sources).map(([source, data]: [string, any]) => ({
      source,
      count: data.count,
      daysActive: data.days_active,
    })).sort((a, b) => b.count - a.count);

    return (
      <div key={correlation.topic} className="rounded-lg border p-4 hover:bg-muted/50 transition-colors">
        <div className="flex items-start justify-between mb-3">
          <div className="flex-1">
            <h3 className="font-semibold text-lg">{correlation.topic}</h3>
            <div className="flex gap-2 mt-1">
              <Badge variant="outline">{correlation.source_count} sources</Badge>
              <Badge variant="secondary">{correlation.total_artifacts} artifacts</Badge>
            </div>
          </div>
        </div>

        <div className="space-y-2">
          {sources.map((source) => (
            <div key={source.source} className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-blue-500" />
                <span className="font-medium capitalize">{source.source}</span>
              </div>
              <div className="text-muted-foreground">
                {source.count} artifacts over {source.daysActive} days
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Network className="h-5 w-5" />
          Cross-Source Correlations
        </CardTitle>
        <div className="text-sm text-muted-foreground">
          Topics appearing in multiple sources ({time_window})
        </div>
      </CardHeader>
      <CardContent>
        {/* Filters */}
        <div className="flex flex-col sm:flex-row gap-4 mb-6">
          <div className="flex-1">
            <div className="relative">
              <Filter className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search topics..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-9"
              />
            </div>
          </div>
          <div className="flex gap-2">
            <Button
              variant={minSources === 2 ? "default" : "outline"}
              size="sm"
              onClick={() => setMinSources(2)}
            >
              2+ Sources
            </Button>
            <Button
              variant={minSources === 3 ? "default" : "outline"}
              size="sm"
              onClick={() => setMinSources(3)}
            >
              3+ Sources
            </Button>
            <Button
              variant={minSources === 4 ? "default" : "outline"}
              size="sm"
              onClick={() => setMinSources(4)}
            >
              4+ Sources
            </Button>
          </div>
        </div>

        {/* Summary Stats */}
        <div className="grid gap-4 sm:grid-cols-3 mb-6">
          <div className="rounded-lg border p-3">
            <div className="text-sm text-muted-foreground">Total Topics</div>
            <div className="mt-1 text-2xl font-semibold">{summary.total_correlated_topics}</div>
          </div>
          <div className="rounded-lg border p-3">
            <div className="text-sm text-muted-foreground">Filtered Topics</div>
            <div className="mt-1 text-2xl font-semibold">{filteredCorrelations.length}</div>
          </div>
          <div className="rounded-lg border p-3">
            <div className="text-sm text-muted-foreground">Avg Sources</div>
            <div className="mt-1 text-2xl font-semibold">{summary.avg_sources_per_topic}</div>
          </div>
        </div>

        {/* Correlations List */}
        {filteredCorrelations.length > 0 ? (
          <div className="space-y-4 max-h-[600px] overflow-y-auto">
            {filteredCorrelations.map(renderCorrelationCard)}
          </div>
        ) : (
          <div className="text-center py-8 text-muted-foreground">
            No correlations found matching your criteria
          </div>
        )}
      </CardContent>
    </Card>
  );
}