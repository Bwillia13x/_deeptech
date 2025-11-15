import React, { useState } from "react";
import { useEntities, useEntitySearch } from "../hooks/useEntities";
import { DataTable } from "../components/ui/data-table";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Badge } from "../components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { User, Building2, Microscope, Search, X, ExternalLink, ChevronRight } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Skeleton } from "../components/ui/skeleton";
import { Entity } from "../types/api";

// Type icon component
function EntityTypeIcon({ type }: { type: string }) {
  switch (type) {
    case "person":
      return <User className="h-4 w-4" />;
    case "lab":
      return <Microscope className="h-4 w-4" />;
    case "org":
      return <Building2 className="h-4 w-4" />;
    default:
      return <User className="h-4 w-4" />;
  }
}

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

  return <Badge className={getColor(type)}>{type}</Badge>;
}

export default function EntitiesPage() {
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [searchInput, setSearchInput] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [entityType, setEntityType] = useState<string>("");

  const { data, isLoading, error } = useEntities({
    page,
    pageSize,
    entityType: entityType || undefined,
    search: searchQuery || undefined,
  });

  const { data: searchResults } = useEntitySearch({
    q: searchInput,
    limit: 10,
  });

  const handleSearch = () => {
    setSearchQuery(searchInput);
    setPage(1);
  };

  const handleClearSearch = () => {
    setSearchInput("");
    setSearchQuery("");
    setPage(1);
  };

  const handleViewDetails = (entityId: string) => {
    navigate(`/entities/${entityId}`);
  };

  // Define table columns
  const columns = [
    {
      header: "Type",
      accessor: "entityType" as const,
      render: (entity: Entity) => <EntityTypeIcon type={entity.type} />,
      className: "w-12",
    },
    {
      header: "Name",
      accessor: "name" as const,
      render: (entity: Entity) => (
        <div>
          <div className="font-medium">{entity.name}</div>
          {entity.description && (
            <div className="text-xs text-muted-foreground">
              {entity.description.length > 80
                ? `${entity.description.substring(0, 80)}...`
                : entity.description}
            </div>
          )}
        </div>
      ),
    },
    {
      header: "Artifacts",
      accessor: "artifactCount" as const,
      render: (entity: Entity) => (
        <Badge variant="outline">
          {entity.artifactCount || 0}
        </Badge>
      ),
      className: "w-20",
    },
    {
      header: "Accounts",
      accessor: "accountCount" as const,
      render: (entity: Entity) => (
        <Badge variant="outline">
          {entity.accountCount || 0}
        </Badge>
      ),
      className: "w-20",
    },
    {
      header: "Created",
      accessor: "createdAt" as const,
      render: (entity: Entity) => (
        <div className="text-sm text-muted-foreground">
          {entity.createdAt
            ? new Date(entity.createdAt).toLocaleDateString()
            : "-"}
        </div>
      ),
      className: "w-24",
    },
    {
      header: "",
      accessor: "id" as const,
      render: (entity: Entity) => (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => handleViewDetails(entity.id.toString())}
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
      ),
      className: "w-12",
    },
  ];

  if (error) {
    return (
      <Card>
        <CardContent>
          <div className="py-8 text-center text-destructive">
            Error loading entities: {error.message}
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Entities</h1>
          <p className="text-muted-foreground">
            Researchers, labs, and organizations discovered across sources
          </p>
        </div>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-col lg:flex-row gap-4">
            {/* Search */}
            <div className="flex-1">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search entities by name or description..."
                  value={searchInput}
                  onChange={(e) => setSearchInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                  className="pl-9"
                />
                {searchInput && (
                  <Button
                    variant="ghost"
                    size="icon"
                    className="absolute right-1 top-1/2 -translate-y-1/2"
                    onClick={handleClearSearch}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                )}
              </div>
              {searchInput.length > 2 && searchResults && searchResults.length > 0 && (
                <div className="mt-2 p-3 bg-muted rounded-md">
                  <div className="text-sm font-medium mb-2">Quick Suggestions:</div>
                  <div className="space-y-1">
                    {searchResults.slice(0, 5).map((result, i) => (
                      <Button
                        key={i}
                        variant="ghost"
                        size="sm"
                        className="w-full justify-start"
                        onClick={() => {
                          handleViewDetails(result.entity.id.toString());
                        }}
                      >
                        <EntityTypeIcon type={result.entity.type} />
                        <span className="ml-2">
                          {result.entity.name} ({result.relevanceScore.toFixed(2)})
                        </span>
                      </Button>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Entity Type Filter */}
            <div className="lg:w-48">
              <select
                value={entityType}
                onChange={(e) => {
                  setEntityType(e.target.value);
                  setPage(1);
                }}
                className="w-full px-3 py-2 bg-background border border-border rounded-md focus:outline-none focus:ring-2 focus:ring-ring"
              >
                <option value="">All Types</option>
                <option value="person">People</option>
                <option value="lab">Labs</option>
                <option value="org">Organizations</option>
              </select>
            </div>

            {/* Search Button */}
            <Button onClick={handleSearch}>
              <Search className="h-4 w-4 mr-2" />
              Search
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Results */}
      <Card>
        <CardHeader>
          <div className="flex justify-between items-center">
            <CardTitle>
              {searchQuery ? (
                <>
                  Search Results: “{searchQuery}” ({data?.total || 0} found)
                </>
              ) : (
                <>
                  All Entities ({data?.total || 0})
                </>
              )}
            </CardTitle>
            <EntityTypeBadge type={entityType || "all"} />
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-4">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : (
            <>
              {data && data.items.length > 0 ? (
                <>
                  <DataTable
                    data={data.items}
                    columns={columns}
                    getRowKey={(entity) => entity.id.toString()}
                  />
                  {data.total > pageSize && (
                    <div className="flex justify-between items-center mt-4">
                      <div className="text-sm text-muted-foreground">
                        Page {page} of {Math.ceil(data.total / pageSize)}
                        <span className="ml-2">(Total: {data.total})</span>
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
                          disabled={page >= Math.ceil(data.total / pageSize)}
                        >
                          Next
                        </Button>
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <div className="py-12 text-center text-muted-foreground">
                  <Search className="h-12 w-12 mx-auto mb-4 text-muted-foreground/50" />
                  <p className="text-lg font-medium">No entities found</p>
                  <p className="text-sm">
                    {searchQuery
                      ? `No entities match “${searchQuery}”`
                      : "No entities have been discovered yet"}
                  </p>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}