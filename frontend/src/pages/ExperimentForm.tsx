import React, { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useExperiment, useCreateExperiment } from "../hooks/useExperiments";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { Badge } from "../components/ui/badge";
import { Slider } from "../components/ui/slider";
import { Skeleton } from "../components/ui/skeleton";
import { ArrowLeft, Save, Play } from "lucide-react";
import { useToast } from "../components/ui/use-toast";

// Scoring weight keys
const SCORING_WEIGHT_KEYS = [
  "novelty",
  "emergence",
  "obscurity",
  "confidence",
  "temporalDecay",
  "crossSource",
];

// Source filter options
const SOURCE_OPTIONS = [
  "arxiv",
  "github",
  "x",
  "crossref",
  "semantic",
  "facebook",
  "linkedin",
  "reddit",
  "hackernews",
];

export default function ExperimentFormPage() {
  const { experimentId } = useParams<{ experimentId: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();
  const isEditing = !!experimentId;

  // Form state
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [baselineId, setBaselineId] = useState("");
  const [minScoreThreshold, setMinScoreThreshold] = useState(70);
  const [lookbackDays, setLookbackDays] = useState(7);
  const [scoringWeights, setScoringWeights] = useState<Record<string, number>>({
    novelty: 0.25,
    emergence: 0.25,
    obscurity: 0.25,
    confidence: 0.25,
  });
  const [sourceFilters, setSourceFilters] = useState<string[]>([]);

  // Fetch experiment if editing
  const { data: experiment, isLoading } = useExperiment(experimentId || "");

  // Create experiment mutation
  const createExperimentMutation = useCreateExperiment();

  // Load experiment data when editing
  useEffect(() => {
    if (isEditing && experiment) {
      setName(experiment.name);
      setDescription(experiment.description || "");
      setBaselineId(experiment.baselineId || "");
      setMinScoreThreshold(experiment.config.minScoreThreshold || 70);
      setLookbackDays(experiment.config.lookbackDays || 7);
      setScoringWeights(experiment.config.scoringWeights || {});
      setSourceFilters(experiment.config.sourceFilters || []);
    }
  }, [experiment, isEditing]);

  // Calculate total weight
  const totalWeight = Object.values(scoringWeights).reduce((sum, w) => sum + w, 0);

  const handleWeightChange = (key: string, value: number) => {
    // Normalize other weights to maintain sum = 1.0
    const newWeights = { ...scoringWeights };
    const oldValue = newWeights[key];
    const change = value - oldValue;

    // Apply change to other weights proportionally
    const otherKeys = Object.keys(newWeights).filter((k) => k !== key);
    const otherTotal = otherKeys.reduce((sum, k) => sum + newWeights[k], 0);

    if (otherTotal > 0) {
      otherKeys.forEach((k) => {
        const proportion = newWeights[k] / otherTotal;
        newWeights[k] = Math.max(0, newWeights[k] - change * proportion);
      });
    }

    newWeights[key] = value;
    setScoringWeights(newWeights);
  };

  const handleSourceToggle = (source: string) => {
    setSourceFilters((prev) =>
      prev.includes(source)
        ? prev.filter((s) => s !== source)
        : [...prev, source]
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    try {
      if (isEditing) {
        // In a real implementation, this would call edit experiment
        toast({
          title: "Experiment Updated",
          description: `${name} has been updated.`,
        });
      } else {
        await createExperimentMutation.mutateAsync({
          name,
          description,
          config: {
            scoringWeights,
            sourceFilters: sourceFilters.length > 0 ? sourceFilters : undefined,
            minScoreThreshold,
            lookbackDays,
          },
          baselineId: baselineId || undefined,
        });

        toast({
          title: "Experiment Created",
          description: `${name} has been created successfully.`,
        });
      }

      navigate("/experiments");
    } catch (error) {
      toast({
        title: isEditing ? "Update Failed" : "Creation Failed",
        description: error instanceof Error ? error.message : "Unknown error",
        variant: "destructive",
      });
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <Card>
          <CardContent className="space-y-4 p-6">
            {[...Array(8)].map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div className="flex items-center gap-3">
        <Button
          type="button"
          variant="ghost"
          onClick={() => navigate("/experiments")}
        >
          <ArrowLeft className="h-4 w-4 mr-2" />
          Back
        </Button>
        <h1 className="text-2xl font-bold">
          {isEditing ? "Edit Experiment" : "Create New Experiment"}
        </h1>
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        {/* Basic Information */}
        <Card className="md:col-span-2">
          <CardHeader>
            <CardTitle>Basic Information</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <Label htmlFor="name">
                Name
                <span className="text-red-500 ml-1">*</span>
              </Label>
              <Input
                id="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g., Enhanced Novelty Scoring"
                required
              />
            </div>

            <div>
              <Label htmlFor="description">Description</Label>
              <Textarea
                id="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Describe what this experiment is testing..."
                rows={3}
              />
            </div>

            <div>
              <Label htmlFor="baselineId">Baseline Experiment (Optional)</Label>
              <Input
                id="baselineId"
                value={baselineId}
                onChange={(e) => setBaselineId(e.target.value)}
                placeholder="ID of baseline to compare against"
              />
              <p className="text-sm text-muted-foreground mt-1">
                Leave empty to use system default as baseline
              </p>
            </div>
          </CardContent>
        </Card>

        {/* Configuration */}
        <Card>
          <CardHeader>
            <CardTitle>Configuration</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <Label htmlFor="minScoreThreshold">
                Min Score Threshold: {minScoreThreshold}
              </Label>
              <Slider
                id="minScoreThreshold"
                value={[minScoreThreshold]}
                min={0}
                max={100}
                step={5}
                onValueChange={(value: number[]) => setMinScoreThreshold(value[0])}
              />
              <p className="text-sm text-muted-foreground mt-1">
                Minimum discovery score to consider
              </p>
            </div>

            <div>
              <Label htmlFor="lookbackDays">
                Lookback Days: {lookbackDays}
              </Label>
              <Slider
                id="lookbackDays"
                value={[lookbackDays]}
                min={1}
                max={30}
                step={1}
                onValueChange={(value: number[]) => setLookbackDays(value[0])}
              />
              <p className="text-sm text-muted-foreground mt-1">
                Days of data to include
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Scoring Weights */}
      <Card>
        <CardHeader>
          <CardTitle>Scoring Weights</CardTitle>
          <p className="text-sm text-muted-foreground">
            Distribute weight across scoring components (must sum to 100%)
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {SCORING_WEIGHT_KEYS.map((key) => (
              <div key={key} className="space-y-2">
                <Label className="capitalize">{key.replace("_", " ")}</Label>
                <Slider
                  value={[Math.round(scoringWeights[key] * 100)]}
                  min={0}
                  max={100}
                  step={5}
                  onValueChange={(value) =>
                    handleWeightChange(key, value[0] / 100)
                  }
                />
                <div className="flex justify-between text-sm text-muted-foreground">
                  <span>{Math.round(scoringWeights[key] * 100)}%</span>
                  <span className={totalWeight !== 1 ? "text-yellow-600" : "text-green-600"}>
                    Total: {(totalWeight * 100).toFixed(0)}%
                  </span>
                </div>
              </div>
            ))}
          </div>
          {totalWeight !== 1 && (
            <div className="rounded-md bg-yellow-50 p-3">
              <p className="text-sm text-yellow-800">
                ⚠️ Weights don't sum to 100%. Consider adjusting to ensure proper normalization.
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Source Filters */}
      <Card>
        <CardHeader>
          <CardTitle>Source Filters (Optional)</CardTitle>
          <p className="text-sm text-muted-foreground">
            Limit experiment to specific artifact sources. Leave empty to include all sources.
          </p>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            {SOURCE_OPTIONS.map((source) => (
              <Badge
                key={source}
                variant={sourceFilters.includes(source) ? "default" : "outline"}
                className="cursor-pointer"
                onClick={() => handleSourceToggle(source)}
              >
                {source.includes("_") ? source.split("_").join(" ") : source}
              </Badge>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Actions */}
      <div className="flex items-center justify-end gap-3">
        <Button
          type="button"
          variant="outline"
          onClick={() => navigate("/experiments")}
        >
          Cancel
        </Button>
        <Button type="submit">
          <Save className="h-4 w-4 mr-2" />
          {isEditing ? "Save Changes" : "Create Experiment"}
        </Button>
        {!isEditing && (
          <Button
            type="button"
            disabled={!name.trim()}
            onClick={async () => {
              try {
                await createExperimentMutation.mutateAsync({
                  name,
                  description,
                  config: {
                    scoringWeights,
                    sourceFilters: sourceFilters.length > 0 ? sourceFilters : undefined,
                    minScoreThreshold,
                    lookbackDays,
                  },
                  baselineId: baselineId || undefined,
                });
                navigate("/experiments");
              } catch (error) {
                toast({
                  title: "Failed to create and run",
                  variant: "destructive",
                });
              }
            }}
          >
            <Play className="h-4 w-4 mr-2" />
            Create & Run
          </Button>
        )}
      </div>
    </form>
  );
}
