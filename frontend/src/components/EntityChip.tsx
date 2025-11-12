import React from "react";
import { Badge } from "./ui/badge";
import { Avatar, AvatarFallback } from "./ui/avatar";
import { User, Building2, Microscope, ExternalLink } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { getEntity } from "../api/discoveries";
import { Entity } from "../types/api";
import { cn } from "../lib/utils";
import { Button } from "./ui/button";

interface EntityChipProps {
  entityId: string;
  showAvatar?: boolean;
  showLink?: boolean;
  className?: string;
}

export function EntityChip({ entityId, showAvatar = true, showLink = false, className }: EntityChipProps) {
  const { data: entity, isLoading } = useQuery({
    queryKey: ["entity", entityId],
    queryFn: () => getEntity(entityId),
    enabled: !!entityId,
  });

  if (isLoading) {
    return <Badge variant="outline" className={cn("animate-pulse", className)}>...</Badge>;
  }

  if (!entity) {
    return null;
  }

  const getEntityIcon = (type: string) => {
    switch (type) {
      case "person":
        return <User className="h-3 w-3" />;
      case "lab":
        return <Microscope className="h-3 w-3" />;
      case "org":
        return <Building2 className="h-3 w-3" />;
      default:
        return <User className="h-3 w-3" />;
    }
  };

  const getEntityColor = (type: string) => {
    switch (type) {
      case "person":
        return "bg-blue-100 text-blue-800 hover:bg-blue-200";
      case "lab":
        return "bg-purple-100 text-purple-800 hover:bg-purple-200";
      case "org":
        return "bg-gray-100 text-gray-800 hover:bg-gray-200";
      default:
        return "bg-gray-100 text-gray-800 hover:bg-gray-200";
    }
  };

  const getInitials = (name: string) => {
    return name
      .split(" ")
      .map((n) => n[0])
      .join("")
      .toUpperCase()
      .slice(0, 2);
  };

  const chipContent = (
    <>
      {showAvatar && (
        <Avatar className="h-5 w-5 mr-1">
          <AvatarFallback className="text-xs bg-primary text-primary-foreground">
            {getInitials(entity.name)}
          </AvatarFallback>
        </Avatar>
      )}
      {getEntityIcon(entity.type)}
      <span className="ml-1">{entity.name}</span>
      {showLink && entity.homepageUrl && (
        <ExternalLink className="h-3 w-3 ml-1" />
      )}
    </>
  );

  if (showLink && entity.homepageUrl) {
    return (
      <Badge
        variant="secondary"
        className={cn("cursor-pointer hover:opacity-80", getEntityColor(entity.type), className)}
        onClick={() => window.open(entity.homepageUrl, "_blank")}
      >
        {chipContent}
      </Badge>
    );
  }

  return (
    <Badge variant="secondary" className={cn(getEntityColor(entity.type), className)}>
      {chipContent}
    </Badge>
  );
}

interface EntityListProps {
  entityIds: string[];
  title?: string;
  className?: string;
}

export function EntityList({ entityIds, title, className }: EntityListProps) {
  if (!entityIds || entityIds.length === 0) {
    return null;
  }

  return (
    <div className={className}>
      {title && <h4 className="text-sm font-medium mb-2">{title}</h4>}
      <div className="flex flex-wrap gap-2">
        {entityIds.map((id) => (
          <EntityChip key={id} entityId={id} />
        ))}
      </div>
    </div>
  );
}

// Entity profile component for detailed view
interface EntityProfileProps {
  entity: Entity;
  onClose?: () => void;
}

export function EntityProfile({ entity, onClose }: EntityProfileProps) {
  const getEntityIcon = (type: string) => {
    switch (type) {
      case "person":
        return <User className="h-6 w-6" />;
      case "lab":
        return <Microscope className="h-6 w-6" />;
      case "org":
        return <Building2 className="h-6 w-6" />;
      default:
        return <User className="h-6 w-6" />;
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-start">
        <div className="flex items-center gap-4">
          <div className="p-3 bg-muted rounded-lg">
            {getEntityIcon(entity.type)}
          </div>
          <div>
            <h2 className="text-2xl font-bold">{entity.name}</h2>
            <Badge variant="secondary" className="mt-1">
              {entity.type}
            </Badge>
          </div>
        </div>
        {onClose && (
          <Button variant="ghost" size="sm" onClick={onClose}>
            ✕
          </Button>
        )}
      </div>

      {entity.description && (
        <div>
          <h3 className="text-lg font-semibold mb-2">Description</h3>
          <p className="text-muted-foreground">{entity.description}</p>
        </div>
      )}

      {entity.homepageUrl && (
        <div>
          <h3 className="text-lg font-semibold mb-2">Homepage</h3>
          <a
            href={entity.homepageUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary hover:underline flex items-center gap-1"
          >
            <ExternalLink className="h-4 w-4" />
            {entity.homepageUrl}
          </a>
        </div>
      )}

      {entity.accounts && entity.accounts.length > 0 && (
        <div>
          <h3 className="text-lg font-semibold mb-2">Accounts</h3>
          <div className="space-y-2">
            {entity.accounts.map((account: any) => (
              <div
                key={account.id}
                className="flex items-center justify-between p-3 bg-muted rounded-lg"
              >
                <div>
                  <div className="font-medium capitalize">{account.platform}</div>
                  <div className="text-sm text-muted-foreground">{account.handleOrId}</div>
                </div>
                <div className="text-right">
                  <div className="text-sm font-medium">
                    {(account.confidence * 100).toFixed(0)}% confidence
                  </div>
                  {account.url && (
                    <a
                      href={account.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-primary hover:underline flex items-center gap-1"
                    >
                      <ExternalLink className="h-3 w-3" />
                      View
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="text-sm text-muted-foreground">
        Created: {new Date(entity.createdAt).toLocaleDateString()}
      </div>
    </div>
  );
}