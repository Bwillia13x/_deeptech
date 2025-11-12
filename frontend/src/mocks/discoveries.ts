import { Discovery, DiscoveriesListParams, TrendingTopic, TrendingTopicsParams, Entity, TopicTimelinePoint } from "../types/api";

// Mock discoveries data
const mockDiscoveriesData: Discovery[] = [
  {
    id: "1",
    type: "preprint",
    source: "arxiv",
    sourceId: "2401.12345",
    title: "Quantum Error Correction with Surface Codes: A Novel Lattice Decoding Approach",
    text: "We present a novel approach to quantum error correction using surface codes with improved threshold rates. Our method achieves 99.9% fidelity with 15% lower overhead compared to previous approaches. This breakthrough enables more reliable quantum computation with fewer physical qubits.",
    url: "https://arxiv.org/abs/2401.12345",
    publishedAt: "2024-01-15T10:00:00Z",
    authorEntityIds: "[1, 2, 3]",
    createdAt: "2024-01-15T10:05:00Z",
    novelty: 85.5,
    emergence: 72.3,
    obscurity: 88.7,
    discoveryScore: 82.1,
    computedAt: "2024-01-15T11:00:00Z",
  },
  {
    id: "2",
    type: "repo",
    source: "github",
    sourceId: "openai/quantum-rl",
    title: "Quantum Reinforcement Learning Framework",
    text: "Open-source release of a quantum reinforcement learning framework that demonstrates quantum advantage in specific RL environments. Includes implementations of quantum policy gradients and quantum value iteration algorithms.",
    url: "https://github.com/openai/quantum-rl",
    publishedAt: "2024-01-14T14:30:00Z",
    authorEntityIds: "[4, 5]",
    createdAt: "2024-01-14T14:35:00Z",
    novelty: 78.9,
    emergence: 68.5,
    obscurity: 65.2,
    discoveryScore: 71.8,
    computedAt: "2024-01-14T15:00:00Z",
  },
  {
    id: "3",
    type: "preprint",
    source: "arxiv",
    sourceId: "2401.12346",
    title: "Photonic Quantum Computing with Integrated Silicon Waveguides",
    text: "Novel fabrication technique for photonic quantum processors using integrated silicon waveguides. Achieves 99.5% photon transmission efficiency and demonstrates 8-photon entanglement. Scalable approach to photonic quantum computing.",
    url: "https://arxiv.org/abs/2401.12346",
    publishedAt: "2024-01-13T09:15:00Z",
    authorEntityIds: "[6, 7, 8]",
    createdAt: "2024-01-13T09:20:00Z",
    novelty: 92.3,
    emergence: 58.7,
    obscurity: 91.5,
    discoveryScore: 77.4,
    computedAt: "2024-01-13T10:00:00Z",
  },
  {
    id: "4",
    type: "tweet",
    source: "x",
    sourceId: "1745678901234567890",
    title: "Breakthrough in protein folding prediction",
    text: "New preprint from @DeepMind shows 20% improvement in protein folding accuracy using quantum-inspired neural networks. The method combines attention mechanisms with quantum state representations.",
    url: "https://twitter.com/i/web/status/1745678901234567890",
    publishedAt: "2024-01-12T16:45:00Z",
    authorEntityIds: "[9]",
    createdAt: "2024-01-12T16:50:00Z",
    novelty: 71.2,
    emergence: 81.4,
    obscurity: 45.8,
    discoveryScore: 68.3,
    computedAt: "2024-01-12T17:00:00Z",
  },
  {
    id: "5",
    type: "release",
    source: "github",
    sourceId: "google-research/quantum-algorithms/v2.1.0",
    title: "Quantum Algorithms Library v2.1.0",
    text: "Major release including implementations of Shor's algorithm, Grover's search, and quantum Fourier transform. New quantum simulation backend with 2x performance improvement.",
    url: "https://github.com/google-research/quantum-algorithms/releases/v2.1.0",
    publishedAt: "2024-01-11T11:20:00Z",
    authorEntityIds: "[10, 11]",
    createdAt: "2024-01-11T11:25:00Z",
    novelty: 62.8,
    emergence: 55.3,
    obscurity: 72.1,
    discoveryScore: 62.7,
    computedAt: "2024-01-11T12:00:00Z",
  },
  {
    id: "6",
    type: "preprint",
    source: "arxiv",
    sourceId: "2401.12347",
    title: "Topological Quantum Computing with Majorana Zero Modes",
    text: "Experimental demonstration of topologically protected quantum gates using Majorana zero modes in semiconductor-superconductor heterostructures. First evidence of topological quantum computation.",
    url: "https://arxiv.org/abs/2401.12347",
    publishedAt: "2024-01-10T08:00:00Z",
    authorEntityIds: "[12, 13, 14]",
    createdAt: "2024-01-10T08:05:00Z",
    novelty: 95.7,
    emergence: 85.2,
    obscurity: 93.4,
    discoveryScore: 90.8,
    computedAt: "2024-01-10T09:00:00Z",
  },
];

// Mock trending topics
const mockTrendingTopicsData: TrendingTopic[] = [
  {
    id: "1",
    name: "quantum computing",
    taxonomyPath: "quantum/algorithms",
    description: "Quantum computing algorithms and implementations",
    createdAt: "2024-01-01T00:00:00Z",
    artifactCount: 23,
    avgDiscoveryScore: 78.5,
  },
  {
    id: "2",
    name: "machine learning",
    taxonomyPath: "ai/ml",
    description: "Machine learning and artificial intelligence",
    createdAt: "2024-01-01T00:00:00Z",
    artifactCount: 18,
    avgDiscoveryScore: 65.2,
  },
  {
    id: "3",
    name: "robotics",
    taxonomyPath: "robotics/manipulation",
    description: "Robotics and autonomous systems",
    createdAt: "2024-01-01T00:00:00Z",
    artifactCount: 15,
    avgDiscoveryScore: 71.8,
  },
  {
    id: "4",
    name: "photonics",
    taxonomyPath: "photonics/quantum",
    description: "Photonic quantum technologies",
    createdAt: "2024-01-01T00:00:00Z",
    artifactCount: 12,
    avgDiscoveryScore: 82.3,
  },
  {
    id: "5",
    name: "protein folding",
    taxonomyPath: "bio/protein-design",
    description: "Protein structure prediction and design",
    createdAt: "2024-01-01T00:00:00Z",
    artifactCount: 8,
    avgDiscoveryScore: 68.7,
  },
];

// Mock entities
const mockEntitiesData: Entity[] = [
  {
    id: "1",
    type: "person",
    name: "Alice Smith",
    description: "Quantum computing researcher at MIT",
    homepageUrl: "https://mit.edu/~alice",
    createdAt: "2024-01-01T00:00:00Z",
    accounts: [
      {
        id: "1",
        entityId: "1",
        platform: "arxiv",
        handleOrId: "alice_smith",
        url: "https://arxiv.org/a/alice_smith",
        confidence: 0.95,
        createdAt: "2024-01-01T00:00:00Z",
      },
      {
        id: "2",
        entityId: "1",
        platform: "github",
        handleOrId: "alice-smith",
        url: "https://github.com/alice-smith",
        confidence: 0.9,
        createdAt: "2024-01-01T00:00:00Z",
      },
    ],
  },
  {
    id: "2",
    type: "person",
    name: "Bob Johnson",
    description: "Postdoctoral researcher in quantum error correction",
    homepageUrl: "https://bobjohnson.org",
    createdAt: "2024-01-01T00:00:00Z",
    accounts: [
      {
        id: "3",
        entityId: "2",
        platform: "arxiv",
        handleOrId: "b_johnson",
        url: "https://arxiv.org/a/b_johnson",
        confidence: 0.92,
        createdAt: "2024-01-01T00:00:00Z",
      },
    ],
  },
  {
    id: "3",
    type: "lab",
    name: "MIT Quantum Lab",
    description: "MIT research laboratory focused on quantum computing",
    homepageUrl: "https://quantum.mit.edu",
    createdAt: "2024-01-01T00:00:00Z",
    accounts: [],
  },
];

export function mockListDiscoveries(params: DiscoveriesListParams): Discovery[] {
  let discoveries = [...mockDiscoveriesData];

  // Filter by minimum score
  if (params.minScore !== undefined) {
    discoveries = discoveries.filter(d => d.discoveryScore >= params.minScore!);
  }

  // Filter by source
  if (params.source) {
    discoveries = discoveries.filter(d => d.source === params.source);
  }

  // Filter by topic (simplified - would check artifact_topics in real implementation)
  if (params.topic) {
    discoveries = discoveries.filter(d => 
      (d.title || "").toLowerCase().includes(params.topic!.toLowerCase()) ||
      (d.text || "").toLowerCase().includes(params.topic!.toLowerCase())
    );
  }

  // Sort
  const sortBy = params.sort || "discoveryScore";
  const order = params.order || "desc";
  
  discoveries.sort((a, b) => {
    let aVal: any = (a as any)[sortBy];
    let bVal: any = (b as any)[sortBy];
    
    if (sortBy === "publishedAt") {
      aVal = new Date(aVal).getTime();
      bVal = new Date(bVal).getTime();
    }
    
    if (order === "asc") {
      return aVal > bVal ? 1 : -1;
    } else {
      return aVal < bVal ? 1 : -1;
    }
  });

  // Limit results
  const limit = params.limit || 50;
  return discoveries.slice(0, limit);
}

export function mockGetTrendingTopics(params: TrendingTopicsParams): TrendingTopic[] {
  let topics = [...mockTrendingTopicsData];

  // Filter by minimum artifact count
  if (params.minArtifactCount) {
    topics = topics.filter(t => t.artifactCount >= params.minArtifactCount!);
  }

  // Sort by artifact count (descending) then by avg score
  topics.sort((a, b) => {
    if (b.artifactCount !== a.artifactCount) {
      return b.artifactCount - a.artifactCount;
    }
    return b.avgDiscoveryScore - a.avgDiscoveryScore;
  });

  // Limit results
  const limit = params.limit || 20;
  return topics.slice(0, limit);
}

export function mockGetEntity(id: string): Entity | null {
  return mockEntitiesData.find(e => e.id === id) || null;
}

export function mockGetTopicTimeline(params: { topic: string; days?: number }): TopicTimelinePoint[] {
  const days = params.days || 14;
  const data: TopicTimelinePoint[] = [];
  
  // Generate mock timeline data
  for (let i = days - 1; i >= 0; i--) {
    const date = new Date();
    date.setDate(date.getDate() - i);
    
    // Simulate varying activity with some randomness
    const baseActivity = 5 + Math.sin(i / 3) * 3; // Wave pattern
    const randomVariation = (Math.random() - 0.5) * 4;
    const count = Math.max(0, Math.round(baseActivity + randomVariation));
    
    const avgScore = 60 + Math.random() * 30 + (count > 8 ? 10 : 0); // Higher scores when more active
    
    data.push({
      date: date.toISOString().split('T')[0],
      count,
      avgScore: Math.min(100, avgScore),
    });
  }
  
  return data;
}