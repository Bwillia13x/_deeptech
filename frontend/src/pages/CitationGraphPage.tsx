import React, { useState, useMemo } from "react";
import { useParams, Link } from "react-router-dom";
import { useCitationGraph } from "../hooks/useArtifactRelationships";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Skeleton } from "../components/ui/skeleton";
import { Slider } from "../components/ui/slider";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { 
  Network, 
  ZoomIn, 
  ZoomOut, 
  RefreshCw, 
  GitBranch,
  Filter,
  Info,
  Maximize2,
} from "lucide-react";
import { CitationGraphNode, CitationGraphEdge, RelationshipType } from "../types/api";
import { useToast } from "../components/ui/use-toast";
import { ResponsiveContainer, ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine } from "recharts";

const relationshipTypeColors: Record<RelationshipType, string> = {
  cite: "#3B82F6",      // blue
  reference: "#10B981",  // green
  discuss: "#8B5CF6",    // purple
  implement: "#F59E0B",  // amber
  mention: "#6B7280",    // gray
  related: "#EC4899",    // pink
};

const sourceColors: Record<string, string> = {
  arxiv: "#3B82F6",      // blue
  github: "#10B981",     // green
  x: "#F59E0B",          // amber
  crossref: "#8B5CF6",   // purple
  semantic: "#EC4899",   // pink
  facebook: "#1877F2",   // facebook blue
  linkedin: "#0A66C2",   // linkedin blue
  reddit: "#FF4500",     // reddit orange
  hackernews: "#FF6600", // hn orange
  youtube: "#FF0000",    // youtube red
};

export default function CitationGraphPage() {
  const { artifactId } = useParams<{ artifactId: string }>();
  const [depth, setDepth] = useState(2);
  const [minConfidence, setMinConfidence] = useState(0.5);
  const [zoom, setZoom] = useState(1);
  const [showLabels, setShowLabels] = useState(true);
  const [selectedNode, setSelectedNode] = useState<number | null>(null);
  const { toast } = useToast();

  // Parse artifact ID
  const parsedArtifactId = artifactId ? parseInt(artifactId, 10) : 1;

  // Fetch citation graph
  const { 
    data: graphData, 
    isLoading: graphLoading,
    error: graphError,
    refetch 
  } = useCitationGraph({
    artifactId: parsedArtifactId,
    depth,
    minConfidence,
  });

  // Show error toast
  if (graphError) {
    toast({
      title: "Error loading citation graph",
      description: graphError.message,
      variant: "destructive",
    });
  }

  // Create a force-directed layout simulation
  const positionedNodes = useMemo(() => {
    if (!graphData?.nodes) return [];

    const nodes = [...graphData.nodes];
    const edges = graphData.edges;
    
    // Simple force-directed layout
    const positions = new Map<number, { x: number; y: number }>();
    const centerX = 0;
    const centerY = 0;
    const radius = 200;

    // Position root node at center
    const rootNode = nodes.find(n => n.id === parsedArtifactId);
    if (rootNode) {
      positions.set(rootNode.id, { x: centerX, y: centerY });
    }

    // Position other nodes in a circle with slight randomness
    const otherNodes = nodes.filter(n => n.id !== parsedArtifactId);
    otherNodes.forEach((node, index) => {
      const angle = (index / otherNodes.length) * 2 * Math.PI;
      const randomOffset = (Math.random() - 0.5) * 100;
      positions.set(node.id, {
        x: Math.cos(angle) * radius + randomOffset,
        y: Math.sin(angle) * radius + randomOffset,
      });
    });

    // Simple spring layout iterations
    for (let iteration = 0; iteration < 50; iteration++) {
      // Apply attractive forces along edges
      edges.forEach(edge => {
        const sourcePos = positions.get(edge.source);
        const targetPos = positions.get(edge.target);
        
        if (sourcePos && targetPos) {
          const dx = targetPos.x - sourcePos.x;
          const dy = targetPos.y - sourcePos.y;
          const distance = Math.sqrt(dx * dx + dy * dy) || 1;
          
          // Attractive force (Hooke's law)
          const force = (distance - 150) * 0.01;
          const fx = (dx / distance) * force;
          const fy = (dy / distance) * force;
          
          sourcePos.x += fx;
          sourcePos.y += fy;
          targetPos.x -= fx;
          targetPos.y -= fy;
        }
      });

      // Repulsive forces between all nodes
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const pos1 = positions.get(nodes[i].id);
          const pos2 = positions.get(nodes[j].id);
          
          if (pos1 && pos2) {
            const dx = pos2.x - pos1.x;
            const dy = pos2.y - pos1.y;
            const distance = Math.sqrt(dx * dx + dy * dy) || 1;
            
            if (distance < 100) {
              const force = 500 / (distance * distance);
              const fx = (dx / distance) * force;
              const fy = (dy / distance) * force;
              
              pos1.x -= fx;
              pos1.y -= fy;
              pos2.x += fx;
              pos2.y += fy;
            }
          }
        }
      }

      // Pull all nodes towards center
      nodes.forEach(node => {
        const pos = positions.get(node.id);
        if (pos && node.id !== parsedArtifactId) {
          const dx = centerX - pos.x;
          const dy = centerY - pos.y;
          pos.x += dx * 0.01;
          pos.y += dy * 0.01;
        }
      });
    }

    // Convert to display coordinates
    return nodes.map(node => {
      const pos = positions.get(node.id)!;
      return {
        ...node,
        x: pos.x,
        y: pos.y,
      };
    });
  }, [graphData, parsedArtifactId]);

  // Prepare scatter plot data
  const scatterData = useMemo(() => {
    if (!positionedNodes.length) return [];
    
    return positionedNodes.map(node => ({
      id: node.id,
      x: node.x,
      y: node.y,
      title: node.title,
      source: node.source,
      type: node.type,
      discoveryScore: node.discoveryScore || 50,
      size: Math.sqrt((node.discoveryScore || 50)) * 2, // Size based on discovery score
    }));
  }, [positionedNodes]);

  // Filter edges based on selected node
  const filteredEdges = useMemo(() => {
    if (!selectedNode || !graphData) return graphData?.edges || [];
    
    return graphData.edges.filter(
      edge => edge.source === selectedNode || edge.target === selectedNode
    );
  }, [selectedNode, graphData]);

  const handleNodeClick = (nodeId: number) => {
    setSelectedNode(selectedNode === nodeId ? null : nodeId);
  };

  const handleZoomIn = () => setZoom(Math.min(zoom * 1.2, 3));
  const handleZoomOut = () => setZoom(Math.max(zoom / 1.2, 0.5));
  const handleResetZoom = () => setZoom(1);

  if (graphLoading) {
    return (
      <div className="space-y-6">
        <header className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <Skeleton className="h-8 w-64" />
            <Skeleton className="h-4 w-96 mt-2" />
          </div>
        </header>
        <Card>
          <CardHeader>
            <Skeleton className="h-6 w-32" />
          </CardHeader>
          <CardContent>
            <Skeleton className="h-[600px] w-full" />
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Citation Graph Explorer</h1>
          <p className="text-muted-foreground">
            Visualize connections between artifacts, papers, code repositories, and discussions
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button onClick={() => refetch()} variant="outline" size="sm">
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
          <Link to={`/artifacts/${parsedArtifactId}/relationships`}>
            <Button size="sm">
              <GitBranch className="h-4 w-4 mr-2" />
              List View
            </Button>
          </Link>
        </div>
      </header>

      {/* Graph Controls */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span className="flex items-center gap-2">
              <Network className="h-4 w-4" />
              Graph Controls
            </span>
            <div className="flex items-center gap-2">
              <Button size="sm" variant="outline" onClick={handleZoomOut}>
                <ZoomOut className="h-4 w-4" />
              </Button>
              <span className="text-sm font-medium px-2">{Math.round(zoom * 100)}%</span>
              <Button size="sm" variant="outline" onClick={handleZoomIn}>
                <ZoomIn className="h-4 w-4" />
              </Button>
              <Button size="sm" variant="outline" onClick={handleResetZoom}>
                Reset
              </Button>
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-2">
              <label className="text-sm font-medium">Graph Depth: {depth}</label>
              <Slider
                value={[depth]}
                min={1}
                max={3}
                step={1}
                onValueChange={(value: number[]) => setDepth(value[0])}
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Min Confidence: {(minConfidence * 100).toFixed(0)}%</label>
              <Slider
                value={[minConfidence * 100]}
                min={0}
                max={100}
                step={5}
                onValueChange={(value: number[]) => setMinConfidence(value[0] / 100)}
              />
            </div>
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium">Show Labels</label>
              <select
                value={showLabels ? "true" : "false"}
                onChange={(e) => setShowLabels(e.target.value === "true")}
                className="rounded-md border border-input bg-background px-3 py-2 text-sm"
              >
                <option value="true">Yes</option>
                <option value="false">No</option>
              </select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Main Graph and Info Panel */}
      <div className="grid gap-6 lg:grid-cols-4">
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <span>Citation Network</span>
              <div className="flex items-center gap-4 text-sm">
                <Badge variant="outline">
                  {graphData?.nodeCount || 0} nodes
                </Badge>
                <Badge variant="outline">
                  {graphData?.edgeCount || 0} edges
                </Badge>
              </div>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[600px] w-full">
              {graphData?.nodes.length ? (
                <ResponsiveContainer width="100%" height="100%">
                  <ScatterChart margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis type="number" dataKey="x" hide />
                    <YAxis type="number" dataKey="y" hide />
                    
                    {/* Render edges as lines */}
                    {scatterData.length > 0 && filteredEdges.map((edge, index) => {
                      const sourceNode = scatterData.find(n => n.id === edge.source);
                      const targetNode = scatterData.find(n => n.id === edge.target);
                      
                      if (!sourceNode || !targetNode) return null;
                      
                      return (
                        <g key={`edge-${index}`}>
                          <line
                            x1={sourceNode.x * zoom + 300}
                            y1={-sourceNode.y * zoom + 300}
                            x2={targetNode.x * zoom + 300}
                            y2={-targetNode.y * zoom + 300}
                            stroke={relationshipTypeColors[edge.relationshipType]}
                            strokeWidth={Math.max(0.5, edge.confidence * 3)}
                            strokeOpacity={0.6}
                          />
                        </g>
                      );
                    })}
                    
                    {/* Render nodes */}
                    <Scatter
                      data={scatterData}
                      fill="#3B82F6"
                    >
                      {scatterData.map((entry, index) => (
                        <circle
                          key={`node-${index}`}
                          r={entry.size}
                          fill={selectedNode === entry.id ? "#EF4444" : sourceColors[entry.source] || "#6B7280"}
                          stroke={selectedNode === entry.id ? "#DC2626" : "#FFFFFF"}
                          strokeWidth={selectedNode === entry.id ? 3 : 1}
                          opacity={selectedNode && selectedNode !== entry.id ? 0.5 : 1}
                          onClick={() => handleNodeClick(entry.id)}
                          style={{ cursor: "pointer" }}
                        />
                      ))}
                    </Scatter>
                    
                    {/* Show labels if enabled */}
                    {showLabels && scatterData.map((node) => (
                      <text
                        key={`label-${node.id}`}
                        x={node.x * zoom + 300 + 15}
                        y={-node.y * zoom + 300}
                        fill="#374151"
                        fontSize="12"
                        className="dark:fill-gray-300"
                      >
                        {node.title.length > 30 ? `${node.title.substring(0, 30)}...` : node.title}
                      </text>
                    ))}
                  </ScatterChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex items-center justify-center h-full text-muted-foreground">
                  No graph data available
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Info Panel */}
        <div className="space-y-4">
          {/* Selected Node Info */}
          {selectedNode && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Info className="h-4 w-4" />
                  Node Details
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {(() => {
                  const node = scatterData.find(n => n.id === selectedNode);
                  if (!node) return null;
                  
                  return (
                    <>
                      <div>
                        <div className="text-sm font-medium">Title</div>
                        <div className="text-sm text-muted-foreground">{node.title}</div>
                      </div>
                      <div>
                        <div className="text-sm font-medium">Source</div>
                        <Badge variant="secondary" className="mt-1">
                          {node.source}
                        </Badge>
                      </div>
                      <div>
                        <div className="text-sm font-medium">Type</div>
                        <Badge variant="outline" className="mt-1">
                          {node.type}
                        </Badge>
                      </div>
                      <div>
                        <div className="text-sm font-medium">Discovery Score</div>
                        <div className="text-lg font-bold mt-1">{node.discoveryScore?.toFixed(1) || "-"}</div>
                      </div>
                      <Link to={`/artifacts/${node.id}`}>
                        <Button size="sm" className="w-full">
                          View Artifact
                        </Button>
                      </Link>
                    </>
                  );
                })()}
              </CardContent>
            </Card>
          )}

          {/* Relationship Type Legend */}
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Relationship Types</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {Object.entries(relationshipTypeColors).map(([type, color]) => (
                <div key={type} className="flex items-center gap-2">
                  <div 
                    className="h-3 w-3 rounded-full" 
                    style={{ backgroundColor: color }}
                  />
                  <span className="text-sm capitalize">{type}</span>
                </div>
              ))}
            </CardContent>
          </Card>

          {/* Source Legend */}
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Artifact Sources</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {Object.entries(sourceColors).map(([source, color]) => (
                <div key={source} className="flex items-center gap-2">
                  <div 
                    className="h-3 w-3 rounded-full" 
                    style={{ backgroundColor: color }}
                  />
                  <span className="text-sm capitalize">{source}</span>
                </div>
              ))}
            </CardContent>
          </Card>

          {/* Controls Help */}
          <Card>
            <CardHeader>
              <CardTitle className="text-sm flex items-center gap-2">
                <Maximize2 className="h-4 w-4" />
                Controls
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm text-muted-foreground">
              <p>• Click nodes to select/highlight</p>
              <p>• Use zoom controls to adjust view</p>
              <p>• Filter by confidence and depth</p>
              <p>• Node size = discovery score</p>
              <p>• Edge thickness = confidence</p>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
