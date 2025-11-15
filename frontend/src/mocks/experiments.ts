import {
  Experiment,
  ExperimentRun,
  ExperimentComparison,
  DiscoveryLabel,
  PaginatedLabels,
} from "../types/api";

// Mock experiment names and configurations
const experimentNames = [
  "Baseline Scoring",
  "Enhanced Embeddings",
  "Cross-Source Correlation",
  "Temporal Decay Weighting",
  "Novelty Boost Algorithm",
  "Multi-Field Normalization",
  "Semantic Similarity v2",
  "Citation Network Scoring",
  "Topic-Based Weighting",
  "Author Authority Score",
];

const scoringWeightPresets = [
  { novelty: 0.3, emergence: 0.3, obscurity: 0.2, confidence: 0.2 },
  { novelty: 0.4, emergence: 0.25, obscurity: 0.15, confidence: 0.2 },
  { novelty: 0.25, emergence: 0.35, obscurity: 0.25, confidence: 0.15 },
  { novelty: 0.2, emergence: 0.2, obscurity: 0.3, confidence: 0.3 },
  { novelty: 0.35, emergence: 0.2, obscurity: 0.2, confidence: 0.25 },
];

const statuses: Array<"draft" | "running" | "completed" | "failed"> = [
  "draft",
  "running",
  "completed",
  "failed",
];

// Generate timestamp within last 30 days
function getRandomTimestamp(): string {
  const now = Date.now();
  const thirtyDaysAgo = now - 30 * 24 * 60 * 60 * 1000;
  const randomTime = thirtyDaysAgo + Math.random() * (now - thirtyDaysAgo);
  return new Date(randomTime).toISOString();
}

export function mockGetExperiments(params?: {
  status?: string;
}): { experiments: Experiment[]; count: number } {
  const experiments: Experiment[] = experimentNames.map((name, index) => {
    const configPreset = scoringWeightPresets[index % scoringWeightPresets.length];
    const status =
      params?.status ||
      statuses[Math.floor(Math.random() * statuses.length)];

    return {
      id: `${index + 1}`,
      name,
      description:
        index % 3 === 0
          ? `Testing ${name.toLowerCase()} for improved precision`
          : undefined,
      config: {
        scoringWeights: configPreset as Record<string, number>,
        sourceFilters: ["arxiv", "github", "x"],
        minScoreThreshold: 70 + Math.random() * 20,
        lookbackDays: 7 + Math.floor(Math.random() * 21),
      },
      baselineId: index > 0 ? "1" : undefined,
      status: status as Experiment["status"],
      createdAt: getRandomTimestamp(),
      updatedAt: getRandomTimestamp(),
    };
  });

  return {
    experiments,
    count: experiments.length,
  };
}

export function mockGetExperimentDetail(id: string): Experiment {
  const experiments = mockGetExperiments().experiments;
  const experiment = experiments.find((e) => e.id === id) || experiments[0];
  return experiment;
}

export function mockGetExperimentRuns(experimentId: string): ExperimentRun[] {
  const numRuns = Math.floor(Math.random() * 8) + 3; // 3-10 runs
  const runs: ExperimentRun[] = [];
  const baseTime = Date.now() - 60 * 24 * 60 * 60 * 1000; // 60 days ago

  for (let i = 0; i < numRuns; i++) {
    const artifactCount = 100 + Math.floor(Math.random() * 400);
    const truePositives = Math.floor(artifactCount * (0.6 + Math.random() * 0.3));
    const falsePositives = Math.floor(artifactCount * (0.1 + Math.random() * 0.2));
    const trueNegatives = Math.floor(artifactCount * (0.05 + Math.random() * 0.15));
    const falseNegatives = artifactCount - truePositives - falsePositives - trueNegatives;

    const precision = truePositives / (truePositives + falsePositives) || 0;
    const recall = truePositives / (truePositives + falseNegatives) || 0;
    const f1Score =
      (2 * precision * recall) / (precision + recall) || 0;
    const accuracy =
      (truePositives + trueNegatives) / artifactCount || 0;

    // Each run is a few days apart
    const startedAt = baseTime + i * 3 * 24 * 60 * 60 * 1000;
    const completedAt = startedAt + (1 + Math.random() * 4) * 60 * 60 * 1000; // 1-5 hours later

    runs.push({
      id: `${experimentId}-run-${i + 1}`,
      experimentId,
      artifactCount,
      truePositives,
      falsePositives,
      trueNegatives,
      falseNegatives,
      precision,
      recall,
      f1Score,
      accuracy,
      startedAt: new Date(startedAt).toISOString(),
      completedAt: new Date(completedAt).toISOString(),
      status: "completed",
      metadata: {
        scoringModel: "v2",
        embeddingsModel: "all-MiniLM-L6-v2",
      },
    });
  }

  return runs.reverse(); // Most recent first
}

export function mockRunExperiment(
  experimentId: string
): { experimentId: string; runId: string } {
  return {
    experimentId,
    runId: `${experimentId}-run-${Date.now()}`,
  };
}

export function mockCompareExperiments(
  experimentA: string,
  experimentB: string
): ExperimentComparison {
  const runA = mockGetExperimentRuns(experimentA)[0];
  const runB = mockGetExperimentRuns(experimentB)[0];

  return {
    experimentA: {
      id: experimentA,
      precision: runA.precision,
      recall: runA.recall,
      f1Score: runA.f1Score,
      accuracy: runA.accuracy,
      artifactCount: runA.artifactCount,
    },
    experimentB: {
      id: experimentB,
      precision: runB.precision,
      recall: runB.recall,
      f1Score: runB.f1Score,
      accuracy: runB.accuracy,
      artifactCount: runB.artifactCount,
    },
    deltas: {
      precision: runB.precision - runA.precision,
      recall: runB.recall - runA.recall,
      f1Score: runB.f1Score - runA.f1Score,
      accuracy: runB.accuracy - runA.accuracy,
    },
    winner:
      runB.f1Score > runA.f1Score
        ? "experimentB"
        : runA.f1Score > runB.f1Score
        ? "experimentA"
        : "tie",
  };
}

export function mockGetLabels(params?: {
  label?: string;
}): PaginatedLabels {
  const labels = [
    "true_positive",
    "false_positive",
    "true_negative",
    "false_negative",
    "relevant",
    "irrelevant",
  ];

  const filteredLabels = params?.label
    ? labels.filter((l) => l === params.label)
    : labels;

  const mockLabels: DiscoveryLabel[] = [];
  const count = Math.floor(Math.random() * 50) + 20; // 20-70 labels

  for (let i = 0; i < count; i++) {
    const label =
      filteredLabels[Math.floor(Math.random() * filteredLabels.length)];
    const artifactId = `${Math.floor(Math.random() * 1000) + 1}`;

    mockLabels.push({
      id: `${i + 1}`,
      artifactId,
      label,
      confidence: Math.random() * 0.5 + 0.5, // 0.5 to 1.0
      annotator:
        Math.random() > 0.7
          ? ["user1", "user2", "user3"][Math.floor(Math.random() * 3)]
          : undefined,
      notes: Math.random() > 0.8 ? `Manually verified artifact ${artifactId}` : undefined,
      createdAt: getRandomTimestamp(),
      updatedAt: getRandomTimestamp(),
      artifactTitle: `Research Artifact ${artifactId}`,
      artifactSource: ["arxiv", "github", "x"][Math.floor(Math.random() * 3)],
    });
  }

  return {
    labels: mockLabels,
    count: mockLabels.length,
  };
}
