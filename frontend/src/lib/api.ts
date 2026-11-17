const BASE = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

function headers(extra?: HeadersInit): Headers {
  return new Headers(extra);
}

async function toError(response: Response): Promise<ApiError> {
  let message = `Request failed (${response.status})`;
  try {
    const body = await response.json();
    if (body?.error || body?.message) message = body.error || body.message;
  } catch {
    /* non-JSON error body */
  }
  return new ApiError(message, response.status);
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  formData?: FormData;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, formData } = options;
  const init: RequestInit = { method, headers: headers() };

  if (formData) {
    init.body = formData;
  } else if (body !== undefined) {
    init.headers = headers({ "Content-Type": "application/json" });
    init.body = JSON.stringify(body);
  }

  const response = await fetch(`${BASE}${path}`, init);
  if (!response.ok) throw await toError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export async function streamChat(
  payload: unknown,
  onChunk: (text: string) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: headers({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
    signal,
  });

  if (!response.ok || !response.body) throw await toError(response);

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const text = decoder.decode(value, { stream: true });
    if (text) onChunk(text);
  }
}

export const api = {
  // endpoint / model selection
  settings: () => request<import("../types").RuntimeSettings>("/settings"),
  saveSettings: (payload: {
    api_base: string;
    api_key?: string;
    model: string;
    context_window?: number;
  }) =>
    request<import("../types").RuntimeSettings>("/settings", {
      method: "PUT",
      body: payload,
    }),
  models: (payload: { api_base?: string; api_key?: string } = {}) =>
    request<import("../types").ModelsResponse>("/models", { method: "POST", body: payload }),

  // knowledge bases
  knowledgeBaseNames: () =>
    request<{ knowledge_base_names: string[] }>("/list_knowledge_base_names"),
  knowledgeBases: () =>
    request<{ knowledge_bases: import("../types").KnowledgeBaseMeta[] }>(
      "/list_knowledge_base_with_metadata",
    ),
  uploadKnowledgeBase: (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return request<{ success: boolean; task_id: string; knowledge_base: string }>(
      "/add_new_knowledge_base",
      { method: "POST", formData },
    );
  },
  deleteKnowledgeBase: (name: string) =>
    request<{ success: boolean }>("/delete_knowledge_base", {
      method: "DELETE",
      body: { knowledge_base_name: name },
    }),
  tasks: () => request<{ tasks: import("../types").IngestTask[] }>("/list_knowledge_base_tasks"),

  // chat history
  history: () => request<{ result: import("../types").HistoryGroup[] }>("/list_chat_history"),
  historyById: (id: number) =>
    request<{ id: number; content: import("../types").HistoryMessage[] }>(
      "/get_chat_history_by_id",
      { method: "POST", body: { id } },
    ),
  saveHistory: (sessionId: string) =>
    request<{ success: boolean; id?: number; empty?: boolean }>("/save_chat_history", {
      method: "POST",
      body: { chat_session_id: sessionId },
    }),
  undoChat: (sessionId: string) =>
    request<{ success: boolean; remaining?: number }>("/undo_chat", {
      method: "POST",
      body: { chat_session_id: sessionId },
    }),
  renameHistory: (id: number, name: string) =>
    request<{ success: boolean }>("/rename_chat_history_by_id", {
      method: "POST",
      body: { id, name },
    }),
  deleteHistory: (id: number) =>
    request<{ success: boolean }>("/delete_chat_history_by_id", {
      method: "DELETE",
      body: { id },
    }),
};