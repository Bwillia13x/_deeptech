import React, { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useArtifactRelationships, useRelationshipStatsOverview, useRunRelationshipDetection } from "../hooks/useArtifactRelationships";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Skeleton } from "../components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { 
  GitBranch, 
  Activity, 
  TrendingUp, 
  Settings,
  RefreshCw,
  Filter,
  ChevronRight,
  Network,
} from "lucide-react";
import { DataTable } from "../components/ui/data-table";
import { ColumnDef } from "@tanstack/react-table";
import { ArtifactRelationship, RelationshipType } from "../types/api";
import { useToast } from "../components/ui/use-toast";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Slider } from "../components/ui/slider";

const numberFormatter = new Intl.NumberFormat("en-US");

const relationshipTypeLabels: Record<RelationshipType, string> = {
  cite: "Citation",
  reference: "Reference",
  discuss: "Discussion",
  implement: "Implementation",
  mention: "Mention",
  related: "Related",
};

const relationshipTypeColors: Record<RelationshipType, string> = {
  cite: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
  reference: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  discuss: "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200",
  implement: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200",
  mention: "bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200",
  related: "bg-pink-100 text-pink-800 dark:bg-pink-900 dark:text-pink-200",
};

export default function ArtifactRelationshipsPage() {
  const { artifactId } = useParams<{ artifactId: string }>();
  const [direction, setDirection] = useState<"incoming" | "outgoing" | "both">("both");
  const [relationshipType, setRelationshipType] = useState<RelationshipType | "all">("all");
  const [minConfidence, setMinConfidence] = useState(0.5);
  const { toast } = useToast();

  // Parse artifact ID - can be undefined for system-wide view
  const parsedArtifactId = artifactId ? parseInt(artifactId, 10) : undefined;

  // Fetch relationships
  const { 
    data: relationshipsData, 
    isLoading: relationshipsLoading,
    error: relationshipsError 
  } = useArtifactRelationships({
    artifactId: parsedArtifactId || 1, // Default to 1 if not provided, will be filtered
    direction,
    relationshipType: relationshipType === "all" ? undefined : relationshipType,
    minConfidence,
    page: 1,
    pageSize: 50,
  });

  // Fetch relationship stats
  const {
    typeDistribution,
    isLoading: statsLoading,
    isError: statsError,
    statsQuery
  } = useRelationshipStatsOverview();

  // Run detection mutation
  const runDetectionMutation = useRunRelationshipDetection();

  // Show error toasts
  if (relationshipsError) {
    toast({
      title: "Error loading relationships",
      description: relationshipsError.message,
      variant: "destructive",
    });
  }
  if (statsError && statsQuery.error) {
    toast({
      title: "Error loading stats",
      description: statsQuery.error.message,
      variant: "destructive",
    });
  }

  // Handle run detection
  const handleRunDetection = async () => {
    try {
      await runDetectionMutation.mutateAsync({
        enableSemantic: true,
        semanticThreshold: 0.8,
      });
      toast({
        title: "Relationship detection completed",
        description: "Successfully discovered new relationships",
      });
    } catch (error) {
      toast({
        title: "Detection failed",
        description: error instanceof Error ? error.message : "Unknown error",
        variant: "destructive",
      });
    }
  };

  // Define columns for relationships table
  const relationshipColumns: ColumnDef<ArtifactRelationship>[] = [
    {
      accessorKey: "sourceTitle",
      header: "Source",
      cell: ({ row }) => (
        <div className="space-y-1">
          <div className="font-medium text-sm line-clamp-2">
            {row.original.sourceTitle}
          </div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Badge variant="outline" className="text-xs">
              {row.original.sourceType}
            </Badge>
            <Badge variant="secondary" className="text-xs">
              {row.original.sourceSource}
            </Badge>
          </div>
        </div>
      ),
    },
    {
      id: "arrow",
      header: "",
      cell: () => (
        <div className="flex justify-center">
          <ChevronRight className="h-4 w-4 text-muted-foreground" />
        </div>
      ),
    },
    {
      accessorKey: "targetTitle",
      header: "Target",
      cell: ({ row }) => (
        <div className="space-y-1">
          <div className="font-medium text-sm line-clamp-2">
            {row.original.targetTitle}
          </div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Badge variant="outline" className="text-xs">
              {row.original.targetType}
            </Badge>
            <Badge variant="secondary" className="text-xs">
              {row.original.targetSource}
            </Badge>
          </div>
        </div>
      ),
    },
    {
      accessorKey: "relationshipType",
      header: "Type",
      cell: ({ row }) => (
        <Badge className={relationshipTypeColors[row.original.relationshipType]}>
          {relationshipTypeLabels[row.original.relationshipType]}
        </Badge>
      ),
    },
    {
      accessorKey: "confidence",
      header: "Confidence",
      cell: ({ row }) => (
        <div className="flex items-center gap-2">
          <div className="h-2 w-20 bg-muted rounded-full overflow-hidden">
            <div
              className="h-full bg-primary transition-all"
              style={{ width: `${row.original.confidence * 100}%` }}
            />
          </div>
          <span className="text-sm font-medium">
            {(row.original.confidence * 100).toFixed(0)}%
          </span>
        </div>
      ),
    },
    {
      accessorKey: "detectionMethod",
      header: "Detected By",
      cell: ({ row }) => (
        <Badge variant="outline" className="text-xs">
          {row.original.detectionMethod.replace("_", " ")}
        </Badge>
      ),
    },
    {
      id: "actions",
      header: "Actions",
      cell: ({ row }) => (
        <div className="flex gap-2">
          <Link to={`/artifacts/${row.original.sourceArtifactId}/graph`}>
            <Button variant="ghost" size="sm">
              <Network className="h-4 w-4" />
            </Button>
          </Link>
          <Link to={`/artifacts/${row.original.targetArtifactId}`}>
            <Button variant="ghost" size="sm">
              View
            </Button>
          </Link>
        </div>
      ),
    },
  ];

  const isLoading = relationshipsLoading || statsLoading;

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">
            {parsedArtifactId ? "Artifact Relationships" : "Cross-Source Corroboration"}
          </h1>
          <p className="text-muted-foreground">
            {parsedArtifactId 
              ? "Explore citation patterns and cross-source relationships for this artifact"
              : "Discover connections between papers, code, and discussions across sources"
            }
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button
            onClick={handleRunDetection}
            disabled={runDetectionMutation.isPending}
            variant="outline"
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${runDetectionMutation.isPending ? "animate-spin" : ""}`} />
            {runDetectionMutation.isPending ? "Running..." : "Run Detection"}
          </Button>
          {parsedArtifactId && (
            <Link to={`/artifacts/${parsedArtifactId}/graph`}>
              <Button>
                <Network className="h-4 w-4 mr-2" />
                View Graph
              </Button>
            </Link>
          )}
        </div>
      </header>

      {/* Stats Overview */}
      <section className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          icon={GitBranch}
          label="Total Relationships"
          value={relationshipsData?.relationships.length || 0}
          loading={isLoading}
          color="text-blue-500"
        />
        <StatCard
          icon={Activity}
          label="Avg Confidence"
          value={Math.round(((relationshipsData?.relationships || []).reduce((acc, r) => acc + r.confidence, 0) / (relationshipsData?.relationships.length || 1)) * 100)}
          loading={isLoading}
          color="text-green-500"
          suffix="%"
        />
        <StatCard
          icon={TrendingUp}
          label="Top Type"
          value={typeDistribution[0]?.type || "-"}
          loading={statsLoading}
          color="text-purple-500"
        />
        <StatCard
          icon={Network}
          label="Connected Artifacts"
          value={new Set(relationshipsData?.relationships.flatMap(r => [r.sourceArtifactId, r.targetArtifactId])).size || 0}
          loading={isLoading}
          color="text-amber-500"
        />
      </section>

      {/* Filters */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Filter className="h-4 w-4" />
            Filters
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">Direction</label>
              <Select value={direction} onValueChange={(value: any) => setDirection(value)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="both">Both</SelectItem>
                  <SelectItem value="incoming">Incoming</SelectItem>
                  <SelectItem value="outgoing">Outgoing</SelectItem>
                </SelectContent>
              </Select>
            </div>
            
            <div className="space-y-2">
              <label className="text-sm font-medium">Type</label>
              <Select value={relationshipType} onValueChange={(value: any) => setRelationshipType(value)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Types</SelectItem>
                  <SelectItem value="cite">Citations</SelectItem>
                  <SelectItem value="reference">References</SelectItem>
                  <SelectItem value="discuss">Discussions</SelectItem>
                  <SelectItem value="implement">Implementations</SelectItem>
                  <SelectItem value="mention">Mentions</SelectItem>
                  <SelectItem value="related">Related</SelectItem>
                </SelectContent>
              </Select>
            </div>
            
            <div className="space-y-2 md:col-span-2">
              <label className="text-sm font-medium">Min Confidence: {(minConfidence * 100).toFixed(0)}%</label>
              <Slider
                value={[minConfidence * 100]}
                min={0}
                max={100}
                step={5}
                onValueChange={(value: number[]) => setMinConfidence(value[0] / 100)}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Main Content */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span>Relationships</span>
            <Badge variant="secondary">
              {numberFormatter.format(relationshipsData?.count || 0)} relationships
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-2">
              {[...Array(10)].map((_, i) => (
                <Skeleton key={i} className="h-16 w-full" />
              ))}
            </div>
          ) : relationshipsData?.relationships.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              No relationships found matching your filters
            </div>
          ) : (
            <DataTable
              columns={relationshipColumns}
              data={relationshipsData?.relationships || []}
              getRowKey={(relationship) => relationship.id}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  loading,
  color,
  suffix = "",
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: number | string;
  loading: boolean;
  color: string;
  suffix?: string;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{label}</CardTitle>
        <Icon className={`h-4 w-4 ${color}`} />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">
          {loading ? (
            <Skeleton className="h-7 w-16" />
          ) : (
            <>
              {typeof value === "number" ? numberFormatter.format(value) : value}
              {suffix}
            </>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
