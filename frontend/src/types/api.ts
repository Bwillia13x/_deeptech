export type ID = string;

export type SignalStatus = "active" | "inactive" | "paused" | "error";

export type Signal = {
  id: ID;
  name: string;
  source: string;
  status: SignalStatus;
  tags?: string[];
  lastSeenAt?: string; // ISO string
  createdAt: string; // ISO string
  updatedAt: string; // ISO string
};

export type CreateSignalInput = {
  name: string;
  source: string;
  status: SignalStatus;
  tags?: string[];
};

export type UpdateSignalInput = Partial<CreateSignalInput>;

export type Paginated<T> = {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
};

export type SignalsListParams = {
  page?: number;
  pageSize?: number;
  search?: string;
  sort?: "name" | "status" | "lastSeenAt" | "createdAt" | "updatedAt";
  order?: "asc" | "desc";
  status?: SignalStatus;
  source?: string;
};

export type SignalsStats = {
  total: number;
  active: number;
  paused: number;
  error: number;
  inactive: number;
};

export type SnapshotStatus = "ready" | "processing" | "failed";

export type Snapshot = {
  id: ID;
  signalId: ID;
  signalName?: string;
  status: SnapshotStatus;
  sizeKb?: number;
  createdAt: string; // ISO string
};

export type SnapshotsListParams = {
  page?: number;
  pageSize?: number;
  search?: string;
  sort?: "createdAt" | "status";
  order?: "asc" | "desc";
  status?: SnapshotStatus;
  signalId?: string;
};

// Phase One: Deep Tech Discovery Types

export type ArtifactType =
  | "preprint"
  | "paper"
  | "repo"
  | "release"
  | "tweet"
  | "post"
  | "reddit_post"
  | "story"
  | "ask"
  | "show"
  | "comment"
  | "job";
export type ArtifactSource =
  | "arxiv"
  | "github"
  | "x"
  | "crossref"
  | "semantic"
  | "facebook"
  | "linkedin"
  | "reddit"
  | "hackernews"
  | "youtube";
export type EntityType = "person" | "lab" | "org";

export type Entity = {
  id: ID;
  type: EntityType;
  name: string;
  description?: string;
  homepageUrl?: string;
  createdAt: string;
  updatedAt?: string;
  accounts?: Account[];
  artifactCount?: number;
  accountCount?: number;
};

export type SimilarityBreakdown = {
  name: number;
  affiliation: number;
  domain: number;
  accounts: number;
};

export type EntityCandidate = {
  entity: Entity;
  similarity: number;
  components: SimilarityBreakdown;
};

export type EntityDecisionOption = "ignore" | "watch" | "needs_review";

export type EntityMergeHistoryItem = {
  id: number;
  primaryEntityId: number;
  candidateEntityId: number;
  decision: string;
  similarityScore?: number;
  reviewer?: string;
  notes?: string;
  createdAt: string;
  primaryName?: string;
  candidateName?: string;
};

export type MergeEntityInput = {
  candidateEntityId: number;
  similarityScore?: number;
  reviewer?: string;
  notes?: string;
};

export type EntityDecisionInput = MergeEntityInput & {
  decision: EntityDecisionOption;
};

export type Account = {
  id: ID;
  entityId: ID;
  platform: string;
  handleOrId: string;
  url?: string;
  confidence: number;
  createdAt: string;
};

export type Topic = {
  id: ID;
  name: string;
  taxonomyPath?: string;
  description?: string;
  createdAt: string;
};

export type Artifact = {
  id: ID;
  type: ArtifactType;
  source: ArtifactSource;
  sourceId: string;
  title?: string;
  text?: string;
  url?: string;
  publishedAt?: string;
  authorEntityIds?: string; // JSON array
  rawJson?: string;
  createdAt: string;
  updatedAt?: string;
  // Joined fields
  novelty?: number;
  emergence?: number;
  obscurity?: number;
  discoveryScore?: number;
  computedAt?: string;
};

export type Discovery = Artifact & {
  novelty: number;
  emergence: number;
  obscurity: number;
  discoveryScore: number;
  computedAt: string;
};

export type DiscoveriesListParams = {
  minScore?: number;
  hours?: number;
  limit?: number;
  topic?: string;
  source?: ArtifactSource;
  sort?: "discoveryScore" | "publishedAt" | "novelty" | "emergence" | "obscurity";
  order?: "asc" | "desc";
};

export type TrendingTopic = Topic & {
  artifactCount: number;
  avgDiscoveryScore: number;
};

export type TrendingTopicsParams = {
  windowDays?: number;
  limit?: number;
  minArtifactCount?: number;
};

export type RefreshParams = {
  type?: "discovery" | "all";
  sources?: string[];
  limit?: number;
};

export type TopicTimelinePoint = {
  date: string; // ISO date string
  count: number;
  avgScore: number;
};

export type TopicEvolutionEvent = {
  id: string;
  topicId: string;
  eventType: "emerge" | "merge" | "split" | "decline" | "growth";
  relatedTopicIds?: string[];
  eventStrength?: number; // 0-1 confidence score
  eventDate: string; // ISO string
  description?: string;
  createdAt?: string; // ISO string
};

export type TopicMergeCandidate = {
  primaryTopic: Topic;
  secondaryTopic: Topic;
  currentSimilarity: number;
  overlapTrend: number;
  confidence: number;
  eventType: "merge";
  timestamp: string; // ISO string
};

export type TopicSplitDetection = {
  primaryTopic: Topic;
  coherenceDrop: number;
  subClusters?: Array<{
    artifacts: any[];
    size: number;
  }>;
  confidence: number;
  eventType: "split";
  timestamp: string; // ISO string
};

export type TopicEmergenceMetrics = {
  growthRate: number;
  acceleration: number;
  velocity: number;
  emergenceScore: number; // 0-100 composite score
};

export type TopicGrowthPrediction = {
  dailyGrowthRate: number;
  predictedCounts: number[];
  confidence: number;
  trend: "rapidly_emerging" | "emerging" | "stable" | "declining" | "insufficient_data";
  predictionWindowDays: number;
};

export type RelatedTopic = {
  id: string;
  name: string;
  taxonomyPath?: string;
  similarity: number;
};

export type TopicStats = {
  topicId: string;
  name: string;
  taxonomyPath?: string;
  totalArtifacts: number;
  avgDiscoveryScore: number;
  emergenceMetrics?: TopicEmergenceMetrics;
  growthPrediction?: TopicGrowthPrediction;
  relatedTopics?: RelatedTopic[];
  recentEvents?: TopicEvolutionEvent[];
  timeline?: TopicTimelinePoint[];
};

export type ApiErrorData = {
  message?: string;
  code?: string;
  details?: unknown;
};

export type EntityStats = {
  entityId: number;
  artifactCount: number;
  avgDiscoveryScore: number;
  totalImpact: number;
  hIndexProxy: number;
  activeDays: number;
  collaborationCount: number;
  topTopics: Array<{
    name: string;
    count: number;
    avgScore: number;
  }>;
  sourceBreakdown: Array<{
    source: string;
    count: number;
    avgScore: number;
  }>;
  activityTimeline: Array<{
    date: string;
    count: number;
  }>;
};

// Cross-Source Corroboration Types

export type RelationshipType = "cite" | "reference" | "discuss" | "implement" | "mention" | "related";

export type RelationshipDirection = "incoming" | "outgoing" | "both";

export type ArtifactRelationship = {
  id: string;
  sourceArtifactId: number;
  targetArtifactId: number;
  sourceTitle: string;
  sourceType: string;
  sourceSource: string;
  targetTitle: string;
  targetType: string;
  targetSource: string;
  relationshipType: RelationshipType;
  confidence: number; // 0.0 to 1.0
  detectionMethod: string;
  createdAt: string; // ISO string
  metadata?: {
    arxivId?: string;
    githubRepo?: string;
    similarityScore?: number;
    [key: string]: any;
  };
};

export type PaginationParams = {
  page?: number;
  pageSize?: number;
};

export type GetRelationshipsParams = PaginationParams & {
  direction?: RelationshipDirection;
  relationshipType?: RelationshipType;
  minConfidence?: number;
};

export type GetRelationshipsResponse = {
  artifactId: number;
  count: number;
  relationships: ArtifactRelationship[];
  pagination: {
    page: number;
    pageSize: number;
    totalPages: number;
  };
};

export type CitationGraphNode = {
  id: number;
  title: string;
  source: string;
  type: string;
  discoveryScore?: number;
};

export type CitationGraphEdge = {
  source: number;
  target: number;
  relationshipType: RelationshipType;
  confidence: number;
  detectionMethod: string;
};

export type CitationGraphResponse = {
  rootArtifactId: number;
  depth: number;
  minConfidence: number;
  nodes: CitationGraphNode[];
  edges: CitationGraphEdge[];
  nodeCount: number;
  edgeCount: number;
};

export type RelationshipStats = {
  totalRelationships: number;
  byType: Record<RelationshipType, number>;
  byMethod: Record<string, number>;
  averageConfidence: number;
  artifactsWithRelationships: number;
  lastUpdated: string; // ISO string
};

export type RelationshipDetectionParams = {
  artifactId?: number;
  enableSemantic?: boolean;
  semanticThreshold?: number;
};

export type RelationshipDetectionStats = {
  processed: number;
  relationshipsCreated: number;
  byType: Record<string, number>;
  byMethod: Record<string, number>;
};

// Experiments & A/B Testing Types

export type ExperimentStatus = "draft" | "running" | "completed" | "failed";

export type Experiment = {
  id: string;
  name: string;
  description?: string;
  config: {
    scoringWeights: Record<string, number>;
    sourceFilters?: string[];
    minScoreThreshold?: number;
    lookbackDays?: number;
  };
  baselineId?: string;
  status: ExperimentStatus;
  createdAt: string;
  updatedAt: string;
};

export type ExperimentRun = {
  id: string;
  experimentId: string;
  artifactCount: number;
  truePositives: number;
  falsePositives: number;
  trueNegatives: number;
  falseNegatives: number;
  precision: number;
  recall: number;
  f1Score: number;
  accuracy: number;
  startedAt: string;
  completedAt: string;
  status: "completed" | "failed" | "running";
  metadata?: Record<string, any>;
};

export type ExperimentComparison = {
  experimentA: {
    id: string;
    precision: number;
    recall: number;
    f1Score: number;
    accuracy: number;
    artifactCount: number;
  };
  experimentB: {
    id: string;
    precision: number;
    recall: number;
    f1Score: number;
    accuracy: number;
    artifactCount: number;
  };
  deltas: {
    precision: number;
    recall: number;
    f1Score: number;
    accuracy: number;
  };
  winner: "experimentA" | "experimentB" | "tie";
};

export type DiscoveryLabel = {
  id: string;
  artifactId: string;
  label: string; // 'true_positive', 'false_positive', 'true_negative', 'false_negative', 'relevant', 'irrelevant'
  confidence: number; // 0.0 to 1.0
  annotator?: string;
  notes?: string;
  createdAt: string;
  updatedAt: string;
  artifactTitle?: string;
  artifactSource?: string;
};

export type LabelDistribution = {
  truePositive: number;
  falsePositive: number;
  trueNegative: number;
  falseNegative: number;
  relevant: number;
  irrelevant: number;
  total: number;
};

export type CreateExperimentInput = {
  name: string;
  description?: string;
  config: {
    scoringWeights: Record<string, number>;
    sourceFilters?: string[];
    minScoreThreshold?: number;
    lookbackDays?: number;
  };
  baselineId?: string;
};

export type AddLabelInput = {
  label: string;
  confidence?: number;
  annotator?: string;
  notes?: string;
};

export type PaginatedExperiments = {
  experiments: Experiment[];
  count: number;
};

export type PaginatedLabels = {
  labels: DiscoveryLabel[];
  count: number;
};

export class ApiError extends Error {
  status: number;
  data?: ApiErrorData | unknown;

  constructor(message: string, status: number, data?: any) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}
