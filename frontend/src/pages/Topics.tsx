import React, { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { TopicClusterExplorer } from "../components/TopicClusterExplorer";
import { ComparativeVisualization } from "../components/ComparativeVisualization";
import { DiscoveryCharts } from "../components/DiscoveryCharts";
import { TopicFilter } from "../components/TopicFilter";
import { getDiscoveryStats, getTrendingTopics } from "../api/discoveries";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Skeleton } from "../components/ui/skeleton";
import { TrendingTopic } from "../types/api";
import { TrendingUp, Activity, Layers, Sparkles } from "lucide-react";

const numberFormatter = new Intl.NumberFormat("en-US");

export default function TopicsPage() {
    const [selectedTopic, setSelectedTopic] = useState<string | undefined>();

    const { data: stats, isLoading: statsLoading } = useQuery({
        queryKey: ["discovery-stats"],
        queryFn: getDiscoveryStats,
    });

    const {
        data: trendingTopics,
        isLoading: trendingLoading,
    } = useQuery({
        queryKey: ["topics-overview"],
        queryFn: () => getTrendingTopics({ limit: 12, windowDays: 30 }),
    });

    const topTopics = trendingTopics?.slice(0, 6) ?? [];
    const spotlightMeta = useMemo(() => {
        if (!selectedTopic || !trendingTopics) return undefined;
        return trendingTopics.find((topic) => topic.name === selectedTopic);
    }, [selectedTopic, trendingTopics]);

    return (
        <div className="space-y-6">
            <header className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">Topic Intelligence</h1>
                    <p className="text-muted-foreground">
                        Track emerging research areas, compare activity across topics, and identify merge or split candidates.
                    </p>
                </div>
                <div className="w-full md:w-80">
                    <TopicFilter selectedTopic={selectedTopic} onTopicSelect={setSelectedTopic} />
                </div>
            </header>

            <section className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                <InsightCard
                    label="Tracked Artifacts"
                    helper="Across all discovery sources"
                    icon={Layers}
                    loading={statsLoading}
                    value={stats ? numberFormatter.format(stats.totalArtifacts) : "-"}
                />
                <InsightCard
                    label="High-Value Discoveries"
                    helper=">70 discovery score"
                    icon={Sparkles}
                    loading={statsLoading}
                    value={stats ? numberFormatter.format(stats.totalDiscoveries) : "-"}
                />
                <InsightCard
                    label="Avg Discovery Score"
                    helper="Across last 30 days"
                    icon={TrendingUp}
                    loading={statsLoading}
                    value={stats ? stats.avgDiscoveryScore.toFixed(1) : "-"}
                />
                <InsightCard
                    label="Trending Topics"
                    helper="Active in past 30 days"
                    icon={Activity}
                    loading={trendingLoading}
                    value={trendingTopics ? trendingTopics.length : "-"}
                />
            </section>

            <section className="grid gap-6 xl:grid-cols-[2fr,1fr]">
                <TopicClusterExplorer selectedTopic={selectedTopic} onTopicSelect={setSelectedTopic} />
                <div className="space-y-4">
                    <SelectedTopicCard topic={spotlightMeta} />
                    <TrendingTopicsCard topics={topTopics} loading={trendingLoading} onSelect={setSelectedTopic} />
                </div>
            </section>

            <ComparativeVisualization className="mt-2" spotlightTopic={selectedTopic} />

            <DiscoveryCharts className="mt-2" />
        </div>
    );
}

function InsightCard({
    label,
    helper,
    value,
    icon: Icon,
    loading,
}: {
    label: string;
    helper: string;
    value: string | number;
    icon: React.ComponentType<{ className?: string }>;
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
                <p className="text-xs text-muted-foreground">{helper}</p>
            </CardContent>
        </Card>
    );
}

function SelectedTopicCard({ topic }: { topic?: TrendingTopic }) {
    return (
        <Card>
            <CardHeader>
                <CardTitle className="text-base font-semibold">Selected Topic</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
                {topic ? (
                    <>
                        <div>
                            <p className="text-lg font-semibold">{topic.name}</p>
                            <p className="text-sm text-muted-foreground">
                                {topic.artifactCount} artifacts · Avg score {topic.avgDiscoveryScore.toFixed(1)}
                            </p>
                        </div>
                        <p className="text-sm text-muted-foreground">
                            Use the cluster explorer to review merge candidates, or add the topic to a multi-topic comparison below.
                        </p>
                    </>
                ) : (
                    <p className="text-sm text-muted-foreground">
                        Choose a topic on the left or via the filter above to see detailed context and comparisons.
                    </p>
                )}
            </CardContent>
        </Card>
    );
}

function TrendingTopicsCard({
    topics,
    loading,
    onSelect,
}: {
    topics: TrendingTopic[];
    loading: boolean;
    onSelect: (topic: string | undefined) => void;
}) {
    return (
        <Card>
            <CardHeader>
                <CardTitle className="text-base font-semibold">Top Topics (30d)</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
                {loading ? (
                    <div className="space-y-2">
                        {[...Array(4)].map((_, idx) => (
                            <Skeleton key={idx} className="h-12 w-full" />
                        ))}
                    </div>
                ) : topics.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No trending topics available.</p>
                ) : (
                    topics.map((topic) => (
                        <button
                            key={topic.name}
                            type="button"
                            onClick={() => onSelect(topic.name)}
                            className="w-full rounded-lg border px-3 py-2 text-left hover:bg-muted"
                        >
                            <div className="flex items-center justify-between">
                                <div>
                                    <p className="font-medium">{topic.name}</p>
                                    <p className="text-xs text-muted-foreground">{topic.artifactCount} artifacts</p>
                                </div>
                                <Badge variant="outline">Avg {topic.avgDiscoveryScore.toFixed(1)}</Badge>
                            </div>
                        </button>
                    ))
                )}
            </CardContent>
        </Card>
    );
}
