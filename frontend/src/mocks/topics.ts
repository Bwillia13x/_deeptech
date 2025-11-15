import {
  TopicStats,
  TopicEmergenceMetrics,
  TopicGrowthPrediction,
  TopicMergeCandidate,
  TopicSplitDetection,
  Topic,
} from "../types/api";

/**
 * Mock topic stats data
 */
export function mockGetTopicStats(topicId: string, windowDays: number = 30): TopicStats {
  const topics: Record<string, Topic> = {
    "1": { id: "1", name: "quantum computing", taxonomyPath: "physics/computing", createdAt: "2024-01-15T00:00:00Z" },
    "2": { id: "2", name: "machine learning", taxonomyPath: "ai/ml", createdAt: "2024-01-20T00:00:00Z" },
    "3": { id: "3", name: "robotics", taxonomyPath: "engineering/robotics", createdAt: "2024-02-01T00:00:00Z" },
    "4": { id: "4", name: "climate tech", taxonomyPath: "environment/tech", createdAt: "2024-02-10T00:00:00Z" },
  };

  const topic = topics[topicId] || topics["1"];

  const emergenceMetrics: TopicEmergenceMetrics = {
    growthRate: 0.15,
    acceleration: 0.02,
    velocity: 2.3,
    emergenceScore: 78.5,
  };

  const growthPrediction: TopicGrowthPrediction = {
    dailyGrowthRate: 0.12,
    predictedCounts: [25, 28, 32, 36, 40, 45, 50, 55, 61, 68, 75, 83, 92, 102],
    confidence: 0.85,
    trend: "emerging",
    predictionWindowDays: 14,
  };

  const relatedTopics = [
    { id: "5", name: "quantum algorithms", taxonomyPath: "physics/computing/algorithms", similarity: 0.92 },
    { id: "6", name: "quantum error correction", taxonomyPath: "physics/computing/qec", similarity: 0.88 },
    { id: "7", name: "quantum cryptography", taxonomyPath: "physics/computing/crypto", similarity: 0.75 },
    { id: "8", name: "quantum sensing", taxonomyPath: "physics/sensing", similarity: 0.68 },
  ];

  return {
    topicId: topic.id,
    name: topic.name,
    taxonomyPath: topic.taxonomyPath,
    totalArtifacts: 245,
    avgDiscoveryScore: 72.3,
    emergenceMetrics,
    growthPrediction,
    relatedTopics,
    recentEvents: [
      {
        id: "evt_1",
        topicId: topic.id,
        eventType: "growth",
        eventStrength: 0.78,
        eventDate: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString(), // 7 days ago
        description: "Significant growth detected in quantum computing publications",
      },
      {
        id: "evt_2",
        topicId: topic.id,
        eventType: "merge",
        relatedTopicIds: ["9"],
        eventStrength: 0.65,
        eventDate: new Date(Date.now() - 14 * 24 * 60 * 60 * 1000).toISOString(), // 14 days ago
        description: "Potential merge candidate with 'quantum information theory'",
      },
    ],
    timeline: generateMockTimeline(windowDays),
  };
}

/**
 * Generate mock timeline data
 */
function generateMockTimeline(days: number): any[] {
  const points: any[] = [];
  const now = new Date();

  for (let i = days - 1; i >= 0; i--) {
    const date = new Date(now);
    date.setDate(date.getDate() - i);
    
    const baseCount = Math.floor(Math.random() * 15) + 5;
    const trendFactor = 1 + (days - i) * 0.03; // Gradual upward trend
    
    points.push({
      date: date.toISOString().split("T")[0],
      count: Math.floor(baseCount * trendFactor),
      avgScore: 60 + Math.random() * 25,
    });
  }

  return points;
}

/**
 * Mock topic merge candidates
 */
export function mockGetMergeCandidates(): TopicMergeCandidate[] {
  return [
    {
      primaryTopic: { id: "1", name: "quantum computing", taxonomyPath: "physics/computing", createdAt: "2024-01-15T00:00:00Z" },
      secondaryTopic: { id: "9", name: "quantum information theory", taxonomyPath: "physics/information", createdAt: "2024-02-01T00:00:00Z" },
      currentSimilarity: 0.92,
      overlapTrend: 0.15,
      confidence: 0.88,
      eventType: "merge",
      timestamp: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(), // 3 days ago
    },
    {
      primaryTopic: { id: "2", name: "machine learning", taxonomyPath: "ai/ml", createdAt: "2024-01-20T00:00:00Z" },
      secondaryTopic: { id: "10", name: "deep learning", taxonomyPath: "ai/dl", createdAt: "2024-01-25T00:00:00Z" },
      currentSimilarity: 0.89,
      overlapTrend: 0.12,
      confidence: 0.85,
      eventType: "merge",
      timestamp: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(), // 5 days ago
    },
    {
      primaryTopic: { id: "3", name: "robotics", taxonomyPath: "engineering/robotics", createdAt: "2024-02-01T00:00:00Z" },
      secondaryTopic: { id: "11", name: "autonomous systems", taxonomyPath: "engineering/autonomous", createdAt: "2024-02-05T00:00:00Z" },
      currentSimilarity: 0.86,
      overlapTrend: 0.08,
      confidence: 0.78,
      eventType: "merge",
      timestamp: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString(), // 7 days ago
    },
  ];
}

/**
 * Mock topic split candidates
 */
export function mockGetSplitCandidates(): TopicSplitDetection[] {
  return [
    {
      primaryTopic: { id: "12", name: "artificial intelligence", taxonomyPath: "ai", createdAt: "2024-01-01T00:00:00Z" },
      coherenceDrop: 0.35,
      subClusters: [
        {
          artifacts: [{ id: "1", title: "Neural networks paper" }, { id: "2", title: "Deep learning research" }],
          size: 2,
        },
        {
          artifacts: [{ id: "3", title: "Symbolic reasoning approach" }, { id: "4", title: "Logic-based AI system" }],
          size: 2,
        },
        {
          artifacts: [{ id: "5", title: "Evolutionary algorithms" }, { id: "6", title: "Genetic programming" }],
          size: 2,
        },
      ],
      confidence: 0.82,
      eventType: "split",
      timestamp: new Date(Date.now() - 4 * 24 * 60 * 60 * 1000).toISOString(), // 4 days ago
    },
    {
      primaryTopic: { id: "13", name: "blockchain", taxonomyPath: "tech/blockchain", createdAt: "2024-01-10T00:00:00Z" },
      coherenceDrop: 0.28,
      subClusters: [
        {
          artifacts: [{ id: "7", title: "Cryptocurrency research" }, { id: "8", title: "DeFi protocols" }],
          size: 2,
        },
        {
          artifacts: [{ id: "9", title: "Smart contracts" }, { id: "10", title: "Solidity programming" }],
          size: 2,
        },
      ],
      confidence: 0.75,
      eventType: "split",
      timestamp: new Date(Date.now() - 6 * 24 * 60 * 60 * 1000).toISOString(), // 6 days ago
    },
  ];
}
