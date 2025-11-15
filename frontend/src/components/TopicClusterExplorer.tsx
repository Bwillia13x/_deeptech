import React, { useState, useMemo, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/tabs";
import {
  Network,
  TrendingUp,
  Calendar,
  Filter,
  X,
  ChevronRight,
  Clock,
  Activity,
  Tag
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { getTrendingTopics, getTopicTimeline } from "../api/discoveries";
import { TrendingTopic, TopicTimelinePoint } from "../types/api";
import { XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Area, AreaChart } from "recharts";
import { format, parseISO } from "date-fns";

interface TopicClusterExplorerProps {
  selectedTopic?: string;
  onTopicSelect: (topic: string | undefined) => void;
}

interface TopicCluster {
  primary: TrendingTopic;
  related: TrendingTopic[];
  timeline: TopicTimelinePoint[];
  mergeCandidates: TrendingTopic[];
  splitIndicators: string[];
}

export function TopicClusterExplorer({ selectedTopic, onTopicSelect }: TopicClusterExplorerProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCluster, setSelectedCluster] = useState<TopicCluster | null>(null);
  const [timeWindow, setTimeWindow] = useState(14); // days

  const { data: trendingTopics } = useQuery({
    queryKey: ["trending-topics", timeWindow],
    queryFn: () => getTrendingTopics({ limit: 50, windowDays: timeWindow }),
  });

  // Group topics into clusters based on name similarity and co-occurrence
  const topicClusters = useMemo(() => {
    if (!trendingTopics) return [];

    const clusters: TopicCluster[] = [];
    const processed = new Set<string>();

    // Simple clustering based on substring matching
    for (const topic of trendingTopics) {
      if (processed.has(topic.name)) continue;

      const cluster: TopicCluster = {
        primary: topic,
        related: [],
        timeline: [],
        mergeCandidates: [],
        splitIndicators: []
      };

      processed.add(topic.name);

      // Find related topics (substring matches)
      for (const other of trendingTopics) {
        if (processed.has(other.name)) continue;

        const isRelated =
          topic.name.includes(other.name) ||
          other.name.includes(topic.name) ||
          hasCommonWords(topic.name, other.name);

        if (isRelated) {
          cluster.related.push(other);
          processed.add(other.name);
        }
      }

      clusters.push(cluster);
    }

    return clusters;
  }, [trendingTopics]);

  useEffect(() => {
    if (!selectedTopic) {
      setSelectedCluster(null);
      return;
    }
    const matchingCluster = topicClusters.find((cluster) => cluster.primary.name === selectedTopic);
    if (matchingCluster) {
      setSelectedCluster(matchingCluster);
    }
  }, [selectedTopic, topicClusters]);

  // Find merge candidates (very similar topics)
  const findMergeCandidates = (cluster: TopicCluster): TrendingTopic[] => {
    const candidates: TrendingTopic[] = [];

    for (const topic of cluster.related) {
      const similarity = calculateStringSimilarity(cluster.primary.name, topic.name);
      if (similarity > 0.8) {
        candidates.push(topic);
      }
    }

    return candidates;
  };

  // Detect split indicators (topics that might be too broad)
  const detectSplitIndicators = (cluster: TopicCluster): string[] => {
    const indicators: string[] = [];

    // If primary topic has many related topics with different sub-topics
    if (cluster.related.length > 5) {
      const subTopics = new Set(
        cluster.related.map(t => t.name.replace(cluster.primary.name, '').trim())
          .filter(s => s.length > 0)
      );

      if (subTopics.size > 3) {
        indicators.push(`May be too broad - consider splitting into ${Array.from(subTopics).slice(0, 3).join(', ')}`);
      }
    }

    return indicators;
  };

  const handleClusterSelect = async (cluster: TopicCluster) => {
    setSelectedCluster(cluster);

    // Fetch timeline data for the primary topic
    try {
      const timeline = await getTopicTimeline({
        topic: cluster.primary.name,
        days: timeWindow
      });

      setSelectedCluster({
        ...cluster,
        timeline,
        mergeCandidates: findMergeCandidates(cluster),
        splitIndicators: detectSplitIndicators(cluster)
      });
    } catch (error) {
      console.error("Error fetching timeline:", error);
    }
  };

  const filteredClusters = topicClusters.filter(cluster =>
    cluster.primary.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    cluster.related.some(t => t.name.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Network className="h-5 w-5" />
          Topic Cluster Explorer
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Search and Filters */}
        <div className="space-y-4">
          <div className="flex gap-2">
            <Input
              placeholder="Search topics..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="flex-1"
            />
            {searchQuery && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setSearchQuery("")}
              >
                <X className="h-4 w-4" />
              </Button>
            )}
          </div>

          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm text-muted-foreground">Time window:</span>
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

        {/* Topic Clusters */}
        <div className="space-y-4">
          <h3 className="font-semibold flex items-center gap-2">
            <TrendingUp className="h-4 w-4" />
            Topic Clusters ({filteredClusters.length})
          </h3>

          <div className="space-y-3">
            {filteredClusters.map((cluster) => (
              <Card
                key={cluster.primary.name}
                className={`cursor-pointer transition-colors hover:bg-muted ${selectedCluster?.primary.name === cluster.primary.name ? 'ring-2 ring-primary' : ''
                  }`}
                onClick={() => handleClusterSelect(cluster)}
              >
                <CardContent className="p-4">
                  <div className="flex justify-between items-start">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-2">
                        <h4 className="font-semibold">{cluster.primary.name}</h4>
                        <Badge variant="secondary">
                          {cluster.primary.artifactCount} artifacts
                        </Badge>
                        <Badge variant="outline">
                          Avg: {cluster.primary.avgDiscoveryScore?.toFixed(1) || 0}
                        </Badge>
                      </div>

                      {cluster.related.length > 0 && (
                        <div className="flex flex-wrap gap-1">
                          <span className="text-xs text-muted-foreground">Related:</span>
                          {cluster.related.slice(0, 3).map((topic) => (
                            <Badge key={topic.name} variant="outline" className="text-xs">
                              {topic.name}
                            </Badge>
                          ))}
                          {cluster.related.length > 3 && (
                            <Badge variant="outline" className="text-xs">
                              +{cluster.related.length - 3} more
                            </Badge>
                          )}
                        </div>
                      )}
                    </div>

                    <ChevronRight className="h-4 w-4 text-muted-foreground" />
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>

        {/* Selected Cluster Details */}
        {selectedCluster && (
          <div className="space-y-6 pt-6 border-t">
            <Tabs defaultValue="overview">
              <TabsList>
                <TabsTrigger value="overview">Overview</TabsTrigger>
                <TabsTrigger value="timeline">Timeline</TabsTrigger>
                <TabsTrigger value="merges">Merges/Splits</TabsTrigger>
              </TabsList>

              <TabsContent value="overview" className="space-y-4">
                <div className="grid gap-4 md:grid-cols-3">
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-medium flex items-center gap-2">
                        <Activity className="h-4 w-4" />
                        Primary Topic
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="text-2xl font-bold">{selectedCluster.primary.name}</div>
                      <p className="text-xs text-muted-foreground mt-1">
                        {selectedCluster.primary.artifactCount} artifacts
                      </p>
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-medium flex items-center gap-2">
                        <Network className="h-4 w-4" />
                        Related Topics
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="text-2xl font-bold">{selectedCluster.related.length}</div>
                      <p className="text-xs text-muted-foreground mt-1">
                        Directly connected
                      </p>
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-medium flex items-center gap-2">
                        <TrendingUp className="h-4 w-4" />
                        Avg Score
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="text-2xl font-bold">
                        {selectedCluster.primary.avgDiscoveryScore?.toFixed(1) || 0}
                      </div>
                      <p className="text-xs text-muted-foreground mt-1">
                        Discovery score
                      </p>
                    </CardContent>
                  </Card>
                </div>

                <div className="space-y-2">
                  <h4 className="font-semibold flex items-center gap-2">
                    <Tag className="h-4 w-4" />
                    Related Topics
                  </h4>
                  <div className="flex flex-wrap gap-2">
                    {selectedCluster.related.map((topic) => (
                      <Badge
                        key={topic.name}
                        variant="outline"
                        className="cursor-pointer hover:bg-secondary"
                        onClick={() => onTopicSelect(topic.name)}
                      >
                        {topic.name} ({topic.artifactCount})
                      </Badge>
                    ))}
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="timeline" className="space-y-4">
                <div className="flex items-center gap-2 mb-4">
                  <Calendar className="h-4 w-4 text-muted-foreground" />
                  <span className="text-sm text-muted-foreground">
                    Activity over last {timeWindow} days
                  </span>
                </div>

                {selectedCluster.timeline.length > 0 ? (
                  <ResponsiveContainer width="100%" height={300}>
                    <AreaChart data={selectedCluster.timeline}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis
                        dataKey="date"
                        tickFormatter={(value) => format(parseISO(value), 'MMM dd')}
                      />
                      <YAxis />
                      <Tooltip
                        labelFormatter={(value) => format(parseISO(value as string), 'MMM dd, yyyy')}
                      />
                      <Area
                        type="monotone"
                        dataKey="count"
                        stroke="#3b82f6"
                        fill="#93c5fd"
                        name="Artifacts"
                      />
                      <Area
                        type="monotone"
                        dataKey="avgScore"
                        stroke="#10b981"
                        fill="#86efac"
                        name="Avg Score"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="text-center py-8 text-muted-foreground">
                    <Clock className="h-8 w-8 mx-auto mb-2 text-muted-foreground/50" />
                    <p>No timeline data available</p>
                  </div>
                )}
              </TabsContent>

              <TabsContent value="merges" className="space-y-4">
                <div className="space-y-4">
                  {/* Merge Candidates */}
                  {selectedCluster.mergeCandidates.length > 0 && (
                    <div>
                      <h4 className="font-semibold mb-2">Merge Candidates</h4>
                      <p className="text-sm text-muted-foreground mb-3">
                        These topics are very similar and could be merged:
                      </p>
                      <div className="space-y-2">
                        {selectedCluster.mergeCandidates.map((topic) => (
                          <Card key={topic.name}>
                            <CardContent className="p-3">
                              <div className="flex justify-between items-center">
                                <div>
                                  <div className="font-medium">{topic.name}</div>
                                  <div className="text-sm text-muted-foreground">
                                    {topic.artifactCount} artifacts • Similarity: {calculateStringSimilarity(selectedCluster.primary.name, topic.name).toFixed(2)}
                                  </div>
                                </div>
                                <Button size="sm" variant="outline">
                                  Propose Merge
                                </Button>
                              </div>
                            </CardContent>
                          </Card>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Split Indicators */}
                  {selectedCluster.splitIndicators.length > 0 && (
                    <div>
                      <h4 className="font-semibold mb-2">Split Indicators</h4>
                      <div className="space-y-2">
                        {selectedCluster.splitIndicators.map((indicator, i) => (
                          <div key={i} className="flex items-start gap-2 p-3 bg-yellow-50 rounded-lg">
                            <div className="w-2 h-2 bg-yellow-400 rounded-full mt-2" />
                            <p className="text-sm">{indicator}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {selectedCluster.mergeCandidates.length === 0 && selectedCluster.splitIndicators.length === 0 && (
                    <div className="text-center py-8 text-muted-foreground">
                      <p>No merge or split recommendations for this topic</p>
                    </div>
                  )}
                </div>
              </TabsContent>
            </Tabs>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// Helper function to calculate string similarity
function calculateStringSimilarity(str1: string, str2: string): number {
  const longer = str1.length > str2.length ? str1 : str2;
  const shorter = str1.length > str2.length ? str2 : str1;

  if (longer.length === 0) return 1.0;

  const editDistance = levenshteinDistance(longer, shorter);
  return (longer.length - editDistance) / longer.length;
}

// Helper function for Levenshtein distance
function levenshteinDistance(str1: string, str2: string): number {
  const matrix: number[][] = [];

  for (let i = 0; i <= str2.length; i++) {
    matrix[i] = [i];
  }

  for (let j = 0; j <= str1.length; j++) {
    matrix[0][j] = j;
  }

  for (let i = 1; i <= str2.length; i++) {
    for (let j = 1; j <= str1.length; j++) {
      if (str2.charAt(i - 1) === str1.charAt(j - 1)) {
        matrix[i][j] = matrix[i - 1][j - 1];
      } else {
        matrix[i][j] = Math.min(
          matrix[i - 1][j - 1] + 1,
          matrix[i][j - 1] + 1,
          matrix[i - 1][j] + 1
        );
      }
    }
  }

  return matrix[str2.length][str1.length];
}

// Helper function to check for common words
function hasCommonWords(str1: string, str2: string): boolean {
  const words1 = new Set(str1.toLowerCase().split(/\s+/));
  const words2 = new Set(str2.toLowerCase().split(/\s+/));

  // Remove common stop words
  const stopWords = new Set(['the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by']);

  const meaningfulWords1 = new Set([...words1].filter(w => !stopWords.has(w) && w.length > 2));
  const meaningfulWords2 = new Set([...words2].filter(w => !stopWords.has(w) && w.length > 2));

  // Check for intersection
  for (const word of meaningfulWords1) {
    if (meaningfulWords2.has(word)) {
      return true;
    }
  }

  return false;
}
