export interface KnowledgeBaseMeta {
  name: string;
  timestamp: number;
  bytes: number;
  chunk_sizes?: number[];
}

export interface HistoryChat {
  id: number;
  title: string;
}

export interface HistoryGroup {
  category: string;
  chats: HistoryChat[];
}

export interface IngestTask {
  task_id: string;
  kb_name: string;
  timestamp: number;
  status: "Pending" | "Completed" | "Failed";
  status_text: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: number;
  streaming?: boolean;
  contextUsed?: number;
  contextWindow?: number;
}

export interface HistoryMessage {
  sender: string;
  content: unknown;
  context_used?: number;
  context_window?: number;
}

export interface RuntimeSettings {
  api_base: string;
  model: string;
  context_window: number;
  api_key_set: boolean;
}

export interface ModelInfo {
  id: string;
  context_length?: number;
  max_model_len?: number;
  owned_by?: string;
  [key: string]: unknown;
}

export interface ModelsResponse {
  ok: boolean;
  models: ModelInfo[];
  error: string | null;
  api_base?: string;
  fetched_at?: number | null;
}

export interface ChatTurnMeta {
  usage?: Record<string, number>;
  context_used?: number;
  context_window?: number;
  model?: string;
}