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

export type ArtifactType = "preprint" | "paper" | "repo" | "release" | "tweet" | "post";
export type ArtifactSource = "arxiv" | "github" | "x" | "crossref" | "semantic";
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

export type ApiErrorData = {
  message?: string;
  code?: string;
  details?: unknown;
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
