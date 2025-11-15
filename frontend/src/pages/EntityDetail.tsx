import React, { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  useEntity,
  useEntityStats,
  useEntityArtifacts,
  useEntityResolutionCandidates,
  useMergeEntity,
  useEntityDecision,
  useEntityMergeHistory,
} from "../hooks/useEntities";
import { Button } from "../components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "../components/ui/card";
import {
  User,
  Building2,
  Microscope,
  ArrowLeft,
  ExternalLink,
  Award,
  Users,
  Calendar,
  FileText,
  TrendingUp,
  Activity,
} from "lucide-react";
import { Badge } from "../components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../components/ui/tabs";
import { Skeleton } from "../components/ui/skeleton";
import { EntityProfile } from "../components/EntityChip";
import { Entity, EntityCandidate, EntityDecisionOption } from "../types/api";
import ErrorBoundary from "../components/ErrorBoundary";
import { DataTable } from "../components/ui/data-table";
import { formatDistanceToNow } from "date-fns";
import { useToast } from "../hooks/use-toast";
import { useConfirm } from "../components/ConfirmDialog";

// Entity type badge
function EntityTypeBadge({ type }: { type: string }) {
  const getColor = (type: string) => {
    switch (type) {
      case "person":
        return "bg-blue-100 text-blue-800";
      case "lab":
        return "bg-purple-100 text-purple-800";
      case "org":
        return "bg-gray-100 text-gray-800";
      default:
        return "bg-gray-100 text-gray-800";
    }
  };

  const getLabel = (type: string) => {
    switch (type) {
      case "person":
        return "Person";
      case "lab":
        return "Research Lab";
      case "org":
        return "Organization";
      default:
        return type;
    }
  };

  return <Badge className={getColor(type)}>{getLabel(type)}</Badge>;
}

// Stat card component
function StatCard({
  title,
  value,
  change,
  icon,
}: {
  title: string;
  value: string | number;
  change?: string;
  icon: React.ReactNode;
}) {
  return (
    <Card>
      <CardContent className="p-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-muted-foreground">{title}</p>
            <p className="text-2xl font-bold mt-2">{value}</p>
            {change && (
              <p className="text-xs text-muted-foreground mt-1">{change}</p>
            )}
          </div>
          <div className="p-2 bg-muted rounded-lg">{icon}</div>
        </div>
      </CardContent>
    </Card>
  );
}

// Entity stats grid
function EntityStatsGrid({ entityId }: { entityId: string }) {
  const { data: stats, isLoading, error } = useEntityStats(entityId, 30);

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
      </div>
    );
  }

  if (error || !stats) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        Unable to load statistics
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      <StatCard
        title="Total Artifacts"
        value={stats.artifactCount}
        icon={<FileText className="h-5 w-5" />}
      />
      <StatCard
        title="Avg Discovery Score"
        value={stats.avgDiscoveryScore?.toFixed(1) || 0}
        change={`${stats.totalImpact?.toFixed(0)} total impact`}
        icon={<TrendingUp className="h-5 w-5" />}
      />
      <StatCard
        title="H-Index Proxy"
        value={stats.hIndexProxy}
        change={`${stats.activeDays} active days`}
        icon={<Award className="h-5 w-5" />}
      />
      <StatCard
        title="Collaborators"
        value={stats.collaborationCount}
        icon={<Users className="h-5 w-5" />}
      />
    </div>
  );
}

// Entity artifacts tab
function EntityArtifactsTab({ entityId }: { entityId: string }) {
  const [page, setPage] = useState(1);
  const limit = 10;
  const offset = (page - 1) * limit;

  const { data, isLoading, error } = useEntityArtifacts({
    entityId,
    limit,
    offset,
  });

  const columns = [
    {
      header: "Title",
      accessor: "title" as const,
      render: (artifact: any) => (
        <div>
          <div className="font-medium">
            {artifact.title || "Untitled"}
          </div>
          <div className="text-xs text-muted-foreground">
            {artifact.source} • {artifact.type}
          </div>
        </div>
      ),
    },
    {
      header: "Score",
      accessor: "discoveryScore" as const,
      render: (artifact: any) => (
        <Badge variant={artifact.discoveryScore > 70 ? "default" : "secondary"}>
          {artifact.discoveryScore?.toFixed(1)}
        </Badge>
      ),
    },
    {
      header: "Date",
      accessor: "publishedAt" as const,
      render: (artifact: any) => (
        <div className="text-sm text-muted-foreground">
          {artifact.publishedAt
            ? new Date(artifact.publishedAt).toLocaleDateString()
            : "-"}
        </div>
      ),
    },
    {
      header: "",
      accessor: "url" as const,
      render: (artifact: any) =>
        artifact.url ? (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => window.open(artifact.url, "_blank")}
          >
            <ExternalLink className="h-4 w-4" />
          </Button>
        ) : null,
    },
  ];

  if (error) {
    return <div className="py-8 text-center text-destructive">Error loading artifacts</div>;
  }

  return (
    <>
      {isLoading ? (
        <div className="space-y-4">
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
        </div>
      ) : (
        <>
          {data && data.items.length > 0 ? (
            <>
              <DataTable
                data={data.items}
                columns={columns}
                getRowKey={(artifact) => artifact.id.toString()}
              />
              {data.hasMore && (
                <div className="flex justify-between items-center mt-4">
                  <div className="text-sm text-muted-foreground">
                    Page {page} (Total: {data.total})
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                      disabled={page === 1}
                    >
                      Previous
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setPage((p) => p + 1)}
                      disabled={!data.hasMore}
                    >
                      Next
                    </Button>
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="py-12 text-center text-muted-foreground">
              No artifacts found
            </div>
          )}
        </>
      )}
    </>
  );
}

// Entity stats tab
function EntityStatsTab({ entityId }: { entityId: string }) {
  const { data: stats, isLoading, error } = useEntityStats(entityId, 30);

  if (isLoading) {
    return <div className="py-8 text-center">Loading statistics...</div>;
  }

  if (error || !stats) {
    return (
      <div className="py-8 text-center text-muted-foreground">
        Unable to load detailed statistics
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Top Topics */}
      {stats.topTopics && stats.topTopics.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Top Topics</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {stats.topTopics.map((topic: any, i: number) => (
                <div key={i} className="flex items-center justify-between p-3 bg-muted rounded-lg">
                  <div className="font-medium">{topic.name}</div>
                  <div className="text-sm text-muted-foreground">
                    {topic.count} artifacts (avg: {topic.avgScore?.toFixed(1)})
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Source Breakdown */}
      {stats.sourceBreakdown && stats.sourceBreakdown.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Source Breakdown</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {stats.sourceBreakdown.map((source: any, i: number) => (
                <div key={i} className="p-4 border rounded-lg">
                  <div className="text-sm text-muted-foreground mb-1 capitalize">
                    {source.source}
                  </div>
                  <div className="text-2xl font-bold">{source.count}</div>
                  <div className="text-sm text-muted-foreground">
                    avg {source.avgScore?.toFixed(1)}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Activity Timeline */}
      {stats.activityTimeline && stats.activityTimeline.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Activity Timeline (Last 30 Days)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-64 overflow-y-auto">
              <div className="space-y-2">
                {stats.activityTimeline.map((activity: any, i: number) => (
                  <div key={i} className="flex items-center justify-between py-2 border-b">
                    <div className="flex items-center gap-2">
                      <Calendar className="h-4 w-4 text-muted-foreground" />
                      {activity.date}
                    </div>
                    <Badge variant="outline">{activity.count} artifacts</Badge>
                  </div>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function SimilarityMeter({ label, value }: { label: string; value: number }) {
  const percent = Math.round(Math.min(Math.max(value, 0), 1) * 100);
  return (
    <div>
      <div className="flex items-center justify-between text-xs font-medium text-muted-foreground">
        <span>{label}</span>
        <span>{percent}%</span>
      </div>
      <progress
        value={percent}
        max={100}
        className="mt-1 h-2 w-full overflow-hidden rounded-full bg-muted [&::-webkit-progress-bar]:bg-muted [&::-webkit-progress-value]:bg-primary [&::-moz-progress-bar]:bg-primary"
      />
    </div>
  );
}

function EntityResolutionTab({ entityId, entity }: { entityId: string; entity: Entity }) {
  const { toast } = useToast();
  const { confirm, Confirm } = useConfirm();
  const { data: candidates = [], isLoading, error, refetch } = useEntityResolutionCandidates(entityId);
  const { data: history = [], isLoading: historyLoading } = useEntityMergeHistory(entityId);
  const mergeMutation = useMergeEntity(entityId);
  const decisionMutation = useEntityDecision(entityId);
  const isActing = mergeMutation.isPending || decisionMutation.isPending;

  const toNumberId = (value: string | number) => {
    const numeric = typeof value === "number" ? value : Number(value);
    if (Number.isNaN(numeric)) {
      throw new Error("Invalid entity identifier");
    }
    return numeric;
  };

  const handleActionError = (err: unknown, fallback: string) => {
    const message = err instanceof Error ? err.message : fallback;
    toast({ title: fallback, description: message, variant: "destructive" });
  };

  const handleMerge = async (candidate: EntityCandidate) => {
    const confirmed = await confirm({
      title: `Merge ${candidate.entity.name}?`,
      description: `This will merge ${candidate.entity.name} into ${entity.name}. The operation cannot be undone.`,
      confirmText: "Merge entities",
      tone: "destructive",
    });
    if (!confirmed) return;

    try {
      await mergeMutation.mutateAsync({
        candidateEntityId: toNumberId(candidate.entity.id),
        similarityScore: candidate.similarity,
      });
      toast({
        title: "Entities merged",
        description: `${candidate.entity.name} is now merged into ${entity.name}.`,
      });
      refetch();
    } catch (err) {
      handleActionError(err, "Merge failed");
    }
  };

  const handleDecision = async (
    candidate: EntityCandidate,
    decision: EntityDecisionOption,
  ) => {
    try {
      await decisionMutation.mutateAsync({
        candidateEntityId: toNumberId(candidate.entity.id),
        decision,
        similarityScore: candidate.similarity,
      });
      const labels: Record<EntityDecisionOption, string> = {
        ignore: "Ignored",
        watch: "Watching",
        needs_review: "Needs review",
      };
      toast({
        title: `Decision recorded: ${labels[decision]}`,
        description: `${candidate.entity.name} marked as ${labels[decision].toLowerCase()}.`,
      });
    } catch (err) {
      handleActionError(err, "Decision failed");
    }
  };

  return (
    <>
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle>Merge Candidates</CardTitle>
              <p className="text-sm text-muted-foreground">
                Potential duplicates ranked by similarity score.
              </p>
            </div>
            <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isLoading}>
              Refresh
            </Button>
          </CardHeader>
          <CardContent>
            {error && (
              <div className="py-6 text-center text-destructive">
                Unable to load candidates
              </div>
            )}

            {isLoading ? (
              <div className="space-y-4">
                <Skeleton className="h-32 w-full" />
                <Skeleton className="h-32 w-full" />
              </div>
            ) : candidates.length === 0 ? (
              <div className="py-10 text-center text-muted-foreground">
                No potential duplicates detected.
              </div>
            ) : (
              <div className="space-y-4">
                {candidates.map((candidate) => (
                  <Card key={candidate.entity.id} className="border-border/60">
                    <CardContent className="pt-6">
                      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                        <div>
                          <div className="flex items-center gap-2">
                            <EntityTypeBadge type={candidate.entity.type} />
                            <h3 className="text-lg font-semibold">{candidate.entity.name}</h3>
                          </div>
                          {candidate.entity.description && (
                            <p className="mt-2 text-sm text-muted-foreground line-clamp-3">
                              {candidate.entity.description}
                            </p>
                          )}
                          <div className="mt-2 text-xs text-muted-foreground">
                            Last updated {candidate.entity.updatedAt
                              ? formatDistanceToNow(new Date(candidate.entity.updatedAt), { addSuffix: true })
                              : "recently"}
                          </div>
                        </div>
                        <Badge variant="secondary" className="text-base">
                          {Math.round(candidate.similarity * 100)}% match
                        </Badge>
                      </div>

                      <div className="mt-4 grid gap-3 md:grid-cols-2">
                        <SimilarityMeter label="Name" value={candidate.components.name} />
                        <SimilarityMeter label="Affiliation" value={candidate.components.affiliation} />
                        <SimilarityMeter label="Domain" value={candidate.components.domain} />
                        <SimilarityMeter label="Accounts" value={candidate.components.accounts} />
                      </div>

                      <div className="mt-4 flex flex-wrap gap-2">
                        <Button size="sm" onClick={() => handleMerge(candidate)} disabled={isActing}>
                          Merge into {entity.name}
                        </Button>
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => handleDecision(candidate, "watch")}
                          disabled={isActing}
                        >
                          Watch
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleDecision(candidate, "needs_review")}
                          disabled={isActing}
                        >
                          Needs Review
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => handleDecision(candidate, "ignore")}
                          disabled={isActing}
                        >
                          Ignore
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-muted-foreground" />
              <span>Resolution History</span>
            </CardTitle>
            <p className="text-sm text-muted-foreground">
              Track recent merge decisions for this entity.
            </p>
          </CardHeader>
          <CardContent>
            {historyLoading ? (
              <div className="space-y-3">
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
              </div>
            ) : history.length === 0 ? (
              <div className="text-sm text-muted-foreground">
                No resolution decisions recorded yet.
              </div>
            ) : (
              <div className="space-y-3">
                {history.map((item) => (
                  <div key={item.id} className="rounded-lg border p-3">
                    <div className="flex items-center justify-between">
                      <div className="font-medium">{item.candidateName || `Entity #${item.candidateEntityId}`}</div>
                      <Badge variant="outline">{item.decision}</Badge>
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {formatDistanceToNow(new Date(item.createdAt), { addSuffix: true })}
                      {item.similarityScore ? ` • ${Math.round(item.similarityScore * 100)}% match` : ""}
                    </div>
                    {item.notes && (
                      <p className="mt-2 text-sm text-muted-foreground">{item.notes}</p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
      {Confirm}
    </>
  );
}

export default function EntityDetailPage() {
  const { entityId } = useParams<{ entityId: string }>();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState("overview");

  const { data: entity, isLoading, error } = useEntity(entityId || "");

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (error || !entity) {
    return (
      <Card>
        <CardContent className="pt-6">
          <div className="text-center py-8 text-muted-foreground">
            <p className="text-lg font-medium mb-2">Entity not found</p>
            <p className="text-sm mb-4">
              Unable to load entity
              {entityId && `: ${entityId}`}
            </p>
            <Button onClick={() => navigate("/entities")}>Back to Entities</Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Back button */}
      <Button variant="ghost" size="sm" onClick={() => navigate("/entities")}>
        <ArrowLeft className="h-4 w-4 mr-2" />
        Back to Entities
      </Button>

      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-4">
          <div className="p-4 bg-muted rounded-lg">
            {entity.type === "person" && <User className="h-8 w-8" />}
            {entity.type === "lab" && <Microscope className="h-8 w-8" />}
            {entity.type === "org" && <Building2 className="h-8 w-8" />}
          </div>
          <div>
            <h1 className="text-3xl font-bold tracking-tight">{entity.name}</h1>
            <div className="mt-2">
              <EntityTypeBadge type={entity.type} />
            </div>
          </div>
        </div>
        <Button variant="outline" size="sm">
          <ExternalLink className="h-4 w-4 mr-2" />
          View Profile
        </Button>
      </div>

      {/* Stats Grid */}
      <EntityStatsGrid entityId={entityId!} />

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-4 lg:w-[500px]">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="artifacts">Artifacts</TabsTrigger>
          <TabsTrigger value="stats">Stats</TabsTrigger>
          <TabsTrigger value="resolution">Resolution</TabsTrigger>
        </TabsList>

        <div className="mt-6">
          <TabsContent value="overview">
            <ErrorBoundary>
              <EntityProfile entity={entity} />
            </ErrorBoundary>
          </TabsContent>

          <TabsContent value="artifacts">
            <ErrorBoundary>
              <EntityArtifactsTab entityId={entityId!} />
            </ErrorBoundary>
          </TabsContent>

          <TabsContent value="stats">
            <ErrorBoundary>
              <EntityStatsTab entityId={entityId!} />
            </ErrorBoundary>
          </TabsContent>

          <TabsContent value="resolution">
            <ErrorBoundary>
              <EntityResolutionTab entityId={entityId!} entity={entity} />
            </ErrorBoundary>
          </TabsContent>
        </div>
      </Tabs>
    </div>
  );
}