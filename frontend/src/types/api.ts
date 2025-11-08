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
