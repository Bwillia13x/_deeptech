import { http } from "../lib/http";
import { isMockMode } from "../lib/env";
import {
  Experiment,
  ExperimentRun,
  ExperimentComparison,
  DiscoveryLabel,
  PaginatedExperiments,
  PaginatedLabels,
  CreateExperimentInput,
  AddLabelInput,
} from "../types/api";
import {
  mockGetExperiments,
  mockGetExperimentDetail,
  mockGetExperimentRuns,
  mockRunExperiment,
  mockCompareExperiments,
  mockGetLabels,
} from "../mocks/experiments";

// API routes
const routes = {
  experiments: "/experiments",
  experiment: (id: string) => `/experiments/${id}`,
  experimentRuns: (id: string) => `/experiments/${id}/runs`,
  compare: "/experiments/compare",
  labels: "/labels",
};

/**
 * Get list of experiments with optional filtering
 */
export async function getExperiments(params?: {
  status?: string;
}): Promise<PaginatedExperiments> {
  if (isMockMode) {
    await new Promise((r) => setTimeout(r, 300));
    return mockGetExperiments(params);
  }

  return http.get<PaginatedExperiments>(routes.experiments, {
    query: params || {},
  });
}

/**
 * Get single experiment by ID
 */
export async function getExperiment(id: string): Promise<Experiment> {
  if (isMockMode) {
    await new Promise((r) => setTimeout(r, 300));
    return mockGetExperimentDetail(id);
  }

  return http.get<Experiment>(routes.experiment(id));
}

/**
 * Get runs for an experiment
 */
export async function getExperimentRuns(id: string): Promise<ExperimentRun[]> {
  if (isMockMode) {
    await new Promise((r) => setTimeout(r, 400));
    return mockGetExperimentRuns(id);
  }

  const response = await http.get<{ runs: ExperimentRun[]; experimentId: string }>(
    routes.experimentRuns(id)
  );
  return response.runs;
}

/**
 * Create a new experiment
 */
export async function createExperiment(input: CreateExperimentInput): Promise<Experiment> {
  if (isMockMode) {
    await new Promise((r) => setTimeout(r, 500));
    return mockGetExperimentDetail("0");
  }

  return http.post<Experiment>(routes.experiments, {
    json: input,
  });
}

/**
 * Run an experiment
 */
export async function runExperiment(id: string): Promise<{ experimentId: string; runId: string }> {
  if (isMockMode) {
    await new Promise((r) => setTimeout(r, 1000));
    return mockRunExperiment(id);
  }

  return http.post<{ experimentId: string; runId: string }>(
    `${routes.experiment(id)}/run`
  );
}

/**
 * Compare two experiments
 */
export async function compareExperiments(
  experimentA: string,
  experimentB: string
): Promise<ExperimentComparison> {
  if (isMockMode) {
    await new Promise((r) => setTimeout(r, 600));
    return mockCompareExperiments(experimentA, experimentB);
  }

  return http.get<ExperimentComparison>(routes.compare, {
    query: { experiment_a: experimentA, experiment_b: experimentB },
  });
}

/**
 * Get labeled artifacts for ground truth
 */
export async function getLabels(params?: {
  label?: string;
  page?: string;
}): Promise<PaginatedLabels> {
  if (isMockMode) {
    await new Promise((r) => setTimeout(r, 300));
    return mockGetLabels(params);
  }

  return http.get<PaginatedLabels>(routes.labels, {
    query: params || {},
  });
}

/**
 * Add label to an artifact
 */
export async function addLabel(
  artifactId: string,
  input: AddLabelInput
): Promise<DiscoveryLabel> {
  if (isMockMode) {
    await new Promise((r) => setTimeout(r, 400));
    return mockGetLabels().labels[0];
  }

  return http.post<DiscoveryLabel>(routes.labels, {
    json: {
      artifactId: artifactId,
      ...input,
    },
  });
}

/**
 * Export labels to CSV
 */
export async function exportLabels(): Promise<Blob> {
  if (isMockMode) {
    await new Promise((r) => setTimeout(r, 300));
    return new Blob(["artifact_id,label,confidence\n1,true_positive,1.0"], {
      type: "text/csv",
    });
  }

  return http.get<Blob>(`${routes.labels}/export`, {
    headers: { Accept: "text/csv" },
  });
}

/**
 * Import labels from CSV
 */
export async function importLabels(file: File): Promise<{ count: number }> {
  if (isMockMode) {
    await new Promise((r) => setTimeout(r, 1000));
    return { count: 42 };
  }

  const formData = new FormData();
  formData.append("file", file);

  return http.post<{ count: number }>(`${routes.labels}/import`, {
    body: formData,
  });
}
