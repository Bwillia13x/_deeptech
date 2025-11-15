import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Experiment,
  ExperimentRun,
  ExperimentComparison,
  DiscoveryLabel,
  PaginatedExperiments,
} from "../types/api";
import {
  getExperiments,
  getExperiment,
  getExperimentRuns,
  createExperiment,
  runExperiment,
  compareExperiments,
  getLabels,
  addLabel,
} from "../api/experiments";

export interface ListExperimentsParams {
  status?: string;
}

export interface GetExperimentDetailParams {
  experimentId: string;
}

// Experiments list query
export function useExperiments(params: ListExperimentsParams = {}) {
  return useQuery({
    queryKey: ["experiments", params],
    queryFn: async () => {
      const response = await getExperiments(params);
      return response;
    },
    placeholderData: (previousData) => previousData,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

// Single experiment query
export function useExperiment(experimentId?: string) {
  return useQuery({
    queryKey: ["experiment", experimentId],
    queryFn: async () => {
      const response = await getExperiment(experimentId ?? "");
      return response;
    },
    enabled: !!experimentId,
    staleTime: 5 * 60 * 1000,
  });
}

// Experiment runs query
export function useExperimentRuns(experimentId?: string) {
  return useQuery({
    queryKey: ["experiment", experimentId, "runs"],
    queryFn: async () => {
      const response = await getExperimentRuns(experimentId ?? "");
      return response;
    },
    enabled: !!experimentId,
    staleTime: 5 * 60 * 1000,
  });
}

// Best run (latest)
export function useBestExperimentRun(experimentId?: string) {
  const { data: runs = [], isLoading } = useExperimentRuns(experimentId);

  const bestRun = runs.length > 0 ? runs[0] : undefined; // Assuming runs are sorted by recency

  return {
    bestRun,
    isLoading,
  };
}

// Create experiment mutation
export function useCreateExperiment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (input: Parameters<typeof createExperiment>[0]) => {
      const response = await createExperiment(input);
      return response;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["experiments"] });
    },
  });
}

// Run experiment mutation
export function useRunExperiment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (experimentId: string) => {
      const response = await runExperiment(experimentId);
      return response;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["experiment", data.experimentId, "runs"] });
      queryClient.invalidateQueries({ queryKey: ["experiment", data.experimentId] });
    },
  });
}

// Compare experiments query
export interface CompareExperimentsParams {
  experimentA: string;
  experimentB: string;
}

export function useCompareExperiments(params: CompareExperimentsParams) {
  return useQuery({
    queryKey: ["experiments", "compare", params],
    queryFn: async () => {
      const response = await compareExperiments(params.experimentA, params.experimentB);
      return response;
    },
    enabled: !!params.experimentA && !!params.experimentB,
    staleTime: 5 * 60 * 1000,
  });
}

// Labels query
export interface GetLabelsParams {
  label?: string;
  page?: string;
}

export function useLabels(params: GetLabelsParams = {}) {
  return useQuery({
    queryKey: ["labels", params],
    queryFn: async () => {
      const response = await getLabels(params);
      return response;
    },
    staleTime: 5 * 60 * 1000,
  });
}

// Add label mutation
export function useAddLabel() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      artifactId,
      input,
    }: {
      artifactId: string;
      input: Parameters<typeof addLabel>[1];
    }) => {
      const response = await addLabel(artifactId, input);
      return response;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["labels"] });
    },
  });
}

// Experiment detail hook (combines multiple queries)
export interface UseExperimentDetailParams {
  experimentId?: string;  // Can be undefined if from useParams before routing validation
}

export function useExperimentDetail({ experimentId }: UseExperimentDetailParams) {
  // Parallel queries for experiment data
  const experimentQuery = useExperiment(experimentId);
  const runsQuery = useExperimentRuns(experimentId);
  const bestRunQuery = useBestExperimentRun(experimentId);

  // Check if any query is loading
  const isLoading =
    experimentQuery.isLoading || runsQuery.isLoading || bestRunQuery.isLoading;

  // Check if any query has error
  const isError =
    experimentQuery.isError || runsQuery.isError;

  // Combine error messages
  const error = isError
    ? {
        experiment: experimentQuery.error,
        runs: runsQuery.error,
      }
    : null;

  // Get latest 5 runs for chart
  const recentRuns = runsQuery.data ? runsQuery.data.slice(0, 5).reverse() : [];

  // Calculate metrics over time for trend analysis
  const metricsOverTime = {
    precision: recentRuns.map((r) => r.precision),
    recall: recentRuns.map((r) => r.recall),
    f1Score: recentRuns.map((r) => r.f1Score),
    accuracy: recentRuns.map((r) => r.accuracy),
    dates: recentRuns.map((r) => r.completedAt),
  };

  // Calculate distribution of TP/FP/TN/FN for the best run
  const confusionMatrix = bestRunQuery.bestRun
    ? {
        truePositives: bestRunQuery.bestRun.truePositives,
        falsePositives: bestRunQuery.bestRun.falsePositives,
        trueNegatives: bestRunQuery.bestRun.trueNegatives,
        falseNegatives: bestRunQuery.bestRun.falseNegatives,
      }
    : null;

  return {
    // Queries
    experimentQuery,
    runsQuery,
    bestRunQuery,

    // Combined data
    data: experimentQuery.data
      ? {
          experiment: experimentQuery.data,
          runs: runsQuery.data || [],
          bestRun: bestRunQuery.bestRun,
          metricsOverTime,
          confusionMatrix,
        }
      : null,

    // Loading and error states
    isLoading,
    isError,
    error,

    // Refetch function
    refetch: () => {
      experimentQuery.refetch();
      runsQuery.refetch();
    },
  };
}

// Experiments overview hook (for dashboard)
export function useExperimentsOverview(status?: string) {
  const experimentsQuery = useExperiments({ status });

  // Calculate statistics
  const completedExperiments =
    experimentsQuery.data?.experiments.filter((e) => e.status === "completed") ||
    [];

  const bestExperiment = completedExperiments.reduce(
    (best, exp) => {
      // This would need actual run data to determine best
      // For now, return the most recent
      return exp;
    },
    completedExperiments[0]
  );

  const averageImprovement = completedExperiments.length;

  return {
    experimentsQuery,
    stats: {
      total: experimentsQuery.data?.count || 0,
      draft:
        experimentsQuery.data?.experiments.filter((e) => e.status === "draft")
          .length || 0,
      running:
        experimentsQuery.data?.experiments.filter((e) => e.status === "running")
          .length || 0,
      completed: completedExperiments.length,
      failed:
        experimentsQuery.data?.experiments.filter((e) => e.status === "failed")
          .length || 0,
      bestExperiment,
      averageImprovement,
    },
  };
}
