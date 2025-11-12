import React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { Skeleton } from "../ui/skeleton";
import { Badge } from "../ui/badge";
import { Activity, Database, Zap, Clock, AlertTriangle, CheckCircle, XCircle } from "lucide-react";

interface SystemHealthPanelProps {
  data: any;
  isLoading: boolean;
}

export function SystemHealthPanel({ data, isLoading }: SystemHealthPanelProps) {
  if (isLoading || !data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Activity className="h-5 w-5" />
            System Health
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-64 w-full" />
        </CardContent>
      </Card>
    );
  }

  const { status, timestamp, components } = data;

  const getStatusIcon = (componentStatus: string) => {
    switch (componentStatus) {
      case "healthy":
        return <CheckCircle className="h-5 w-5 text-green-500" />;
      case "warning":
        return <AlertTriangle className="h-5 w-5 text-yellow-500" />;
      case "unhealthy":
        return <XCircle className="h-5 w-5 text-red-500" />;
      default:
        return <Activity className="h-5 w-5 text-gray-500" />;
    }
  };

  const getStatusColor = (componentStatus: string) => {
    switch (componentStatus) {
      case "healthy":
        return "bg-green-100 text-green-800 border-green-200";
      case "warning":
        return "bg-yellow-100 text-yellow-800 border-yellow-200";
      case "unhealthy":
        return "bg-red-100 text-red-800 border-red-200";
      default:
        return "bg-gray-100 text-gray-800 border-gray-200";
    }
  };

  const renderDatabaseHealth = () => {
    const db = components.database;
    if (db.status === "error" || !db.artifact_count) {
      return (
        <div className="rounded-lg border border-red-200 p-4 bg-red-50">
          <div className="flex items-center gap-2 text-red-800">
            <XCircle className="h-5 w-5" />
            <span className="font-semibold">Database Error</span>
          </div>
          <div className="mt-2 text-sm text-red-700">{db.error}</div>
        </div>
      );
    }

    return (
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-lg border p-3">
            <div className="flex items-center gap-2">
              <Database className="h-4 w-4 text-muted-foreground" />
              <div className="text-sm text-muted-foreground">Database Size</div>
            </div>
            <div className="mt-1 text-xl font-semibold">{db.size_mb} MB</div>
          </div>
          <div className="rounded-lg border p-3">
            <div className="flex items-center gap-2">
              <Zap className="h-4 w-4 text-muted-foreground" />
              <div className="text-sm text-muted-foreground">Artifacts</div>
            </div>
            <div className="mt-1 text-xl font-semibold">{db.artifact_count.toLocaleString()}</div>
          </div>
          <div className="rounded-lg border p-3">
            <div className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-muted-foreground" />
              <div className="text-sm text-muted-foreground">Entities</div>
            </div>
            <div className="mt-1 text-xl font-semibold">{db.entity_count.toLocaleString()}</div>
          </div>
          <div className="rounded-lg border p-3">
            <div className="flex items-center gap-2">
              <Clock className="h-4 w-4 text-muted-foreground" />
              <div className="text-sm text-muted-foreground">Last 24h</div>
            </div>
            <div className="mt-1 text-xl font-semibold">{db.recent_artifacts_24h}</div>
          </div>
        </div>

        <div className="rounded-lg border p-4">
          <h3 className="font-semibold mb-3">Database Metrics</h3>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Topics:</span>
              <span className="font-medium">{db.topic_count}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Recent Activity:</span>
              <span className="font-medium">{db.recent_artifacts_24h} artifacts</span>
            </div>
          </div>
        </div>
      </div>
    );
  };

  const renderPipelineHealth = () => {
    const pipeline = components.pipeline;
    if (pipeline.status === "error" || pipeline.unanalyzed_artifacts === undefined) {
      return (
        <div className="rounded-lg border border-red-200 p-4 bg-red-50">
          <div className="flex items-center gap-2 text-red-800">
            <XCircle className="h-5 w-5" />
            <span className="font-semibold">Pipeline Error</span>
          </div>
          <div className="mt-2 text-sm text-red-700">{pipeline.error}</div>
        </div>
      );
    }

    const isHealthy = pipeline.unanalyzed_artifacts < 100;
    const isWarning = pipeline.unanalyzed_artifacts >= 100 && pipeline.unanalyzed_artifacts < 500;

    return (
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-lg border p-3">
            <div className="text-sm text-muted-foreground">Unanalyzed Artifacts</div>
            <div className={`mt-1 text-xl font-semibold ${
              isHealthy ? "text-green-600" : isWarning ? "text-yellow-600" : "text-red-600"
            }`}>
              {pipeline.unanalyzed_artifacts}
            </div>
            <div className="text-xs text-muted-foreground mt-1">
              {isHealthy ? "✓ Pipeline healthy" : isWarning ? "⚠ Processing backlog" : "⚠ Significant backlog"}
            </div>
          </div>
          <div className="rounded-lg border p-3">
            <div className="text-sm text-muted-foreground">Unscored Artifacts</div>
            <div className="mt-1 text-xl font-semibold">
              {pipeline.unscored_artifacts}
            </div>
          </div>
        </div>

        {(!isHealthy || pipeline.unscored_artifacts > 0) && (
          <div className="rounded-lg border border-yellow-200 p-4 bg-yellow-50">
            <div className="flex items-center gap-2 text-yellow-800">
              <AlertTriangle className="h-5 w-5" />
              <span className="font-semibold">Pipeline Recommendations</span>
            </div>
            <ul className="mt-2 text-sm text-yellow-700 list-disc list-inside">
              {pipeline.unanalyzed_artifacts >= 100 && (
                <li>Consider running the analysis pipeline to process backlog</li>
              )}
              {pipeline.unscored_artifacts > 0 && (
                <li>Run scoring pipeline to calculate discovery scores for unscored artifacts</li>
              )}
              <li>Monitor pipeline performance and adjust scheduling if needed</li>
            </ul>
          </div>
        )}
      </div>
    );
  };

  const renderComponentStatus = (name: string, component: any) => {
    const status = component.status;
    
    return (
      <div key={name} className="rounded-lg border p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            {getStatusIcon(status)}
            <h3 className="font-semibold capitalize">{name.replace('_', ' ')}</h3>
          </div>
          <Badge className={getStatusColor(status)}>
            {status}
          </Badge>
        </div>

        {name === 'database' && renderDatabaseHealth()}
        {name === 'pipeline' && renderPipelineHealth()}
        {name === 'api' && (
          <div className="text-sm text-muted-foreground">
            API is running and responding to requests
          </div>
        )}
      </div>
    );
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Activity className="h-5 w-5" />
          System Health
        </CardTitle>
        <div className="text-sm text-muted-foreground">
          Status: {status} • Last checked: {new Date(timestamp).toLocaleString()}
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-6">
          {Object.entries(components).map(([name, component]) => 
            renderComponentStatus(name, component)
          )}
        </div>
      </CardContent>
    </Card>
  );
}