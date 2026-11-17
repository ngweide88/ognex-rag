import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { useLocation } from "react-router-dom";
import { ArrowUp, ChevronDown, Cpu, Square, TriangleAlert } from "lucide-react";
import { api, streamChat } from "../lib/api";
import { NO_RAG } from "../lib/constants";
import { extractMeta } from "../lib/richText";
import { newId } from "../lib/utils";
import type { ChatMessage, RuntimeSettings } from "../types";
import { AssistantBubble, UserBubble } from "../components/ChatMessages";
import { KnowledgeBasePicker } from "../components/KnowledgeBasePicker";
import { BrandMark } from "../components/Brand";
import { ContextMeter } from "../components/ContextMeter";
import { ModelSettingsModal } from "../components/ModelSettingsModal";
import { useToast } from "../components/Toast";

interface NavState {
  historyId?: number;
  title?: string;
  newChat?: number;
}

export function ChatPage() {
  const location = useLocation();
  const toast = useToast();

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessionId, setSessionId] = useState(newId);
  const [knowledgeBases, setKnowledgeBases] = useState<string[]>([NO_RAG]);
  const [selected, setSelected] = useState<string[]>([NO_RAG]);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState("New conversation");
  const [runtime, setRuntime] = useState<RuntimeSettings | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [contextUsed, setContextUsed] = useState<number | null>(null);

  const sessionIdRef = useRef(sessionId);
  const abortRef = useRef<AbortController | null>(null);
  const handledNavRef = useRef("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  useEffect(() => {
    api
      .knowledgeBaseNames()
      .then((data) => setKnowledgeBases(data.knowledge_base_names))
      .catch(() => setKnowledgeBases([NO_RAG]));

    api
      .settings()
      .then(setRuntime)
      .catch(() => undefined);
  }, []);

  const loadConversation = useCallback(async (historyId: number) => {
    try {
      const data = await api.historyById(historyId);
      const restored: ChatMessage[] = data.content.map((message, index) => ({
        id: `${historyId}-${index}`,
        role: message.sender === "user" ? "user" : "assistant",
        content:
          typeof message.content === "string" ? message.content : JSON.stringify(message.content),
        createdAt: Date.now(),
        contextUsed:
          typeof message.context_used === "number" ? message.context_used : undefined,
        contextWindow:
          typeof message.context_window === "number" ? message.context_window : undefined,
      }));
      setMessages(restored);
      setSessionId(`updateChatHistory_${historyId}`);
      const lastUsage = [...restored]
        .reverse()
        .find(
          (message) =>
            message.role === "assistant" && typeof message.contextUsed === "number",
        );
      setContextUsed(lastUsage?.contextUsed ?? null);
      if (lastUsage?.contextWindow) {
        const contextWindow = lastUsage.contextWindow;
        setRuntime((current) =>
          current ? { ...current, context_window: contextWindow } : current,
        );
      }
      setError(null);
    } catch (err) {
      toast.push(err instanceof Error ? err.message : "Could not load conversation", "error");
    }
  }, [toast]);

  const resetConversation = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
    setSessionId(newId());
    setSelected([NO_RAG]);
    setTitle("New conversation");
    setContextUsed(null);
    setError(null);
  }, []);

  // Sidebar navigation: load an existing chat or start a fresh one.
  useEffect(() => {
    const nav = location.state as NavState | null;
    if (!nav) return;

    if (nav.historyId) {
      const key = `history-${nav.historyId}`;
      if (handledNavRef.current === key) return;
      handledNavRef.current = key;
      if (nav.title) setTitle(nav.title);
      void loadConversation(nav.historyId);
    } else if (nav.newChat) {
      const key = `new-${nav.newChat}`;
      if (handledNavRef.current === key) return;
      handledNavRef.current = key;
      resetConversation();
    }
  }, [location.state, loadConversation, resetConversation]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages]);

  const saveConversation = useCallback(async () => {
    try {
      const result = await api.saveHistory(sessionIdRef.current);
      if (!sessionIdRef.current.startsWith("updateChatHistory") && result.id) {
        const next = `updateChatHistory_${result.id}`;
        sessionIdRef.current = next;
        setSessionId(next);
      }
      window.dispatchEvent(new Event("ognex:history-updated"));
    } catch {
      // Saving is best-effort; the conversation is still usable.
    }
  }, []);

  const undoLastTurn = useCallback(async () => {
    if (streaming) return;
    if (messages.length === 0) {
      toast.push("Nothing to undo", "info");
      return;
    }

    try {
      await api.undoChat(sessionIdRef.current);
    } catch (err) {
      toast.push(err instanceof Error ? err.message : "Undo failed", "error");
      return;
    }

    const trimmed = [...messages];
    if (trimmed.length > 0 && trimmed[trimmed.length - 1].role === "assistant") {
      trimmed.pop();
    }
    if (trimmed.length > 0 && trimmed[trimmed.length - 1].role === "user") {
      trimmed.pop();
    }

    setMessages(trimmed);
    const lastUsage = [...trimmed]
      .reverse()
      .find(
        (message) => message.role === "assistant" && typeof message.contextUsed === "number",
      );
    setContextUsed(lastUsage?.contextUsed ?? null);
    toast.push("Last turn removed", "success");
  }, [messages, streaming, toast]);

  const send = useCallback(
    async (text: string) => {
      const prompt = text.trim();
      if (!prompt || streaming) return;

      if (prompt.toLowerCase() === "/undo") {
        await undoLastTurn();
        return;
      }

      setError(null);
      const createdAt = Date.now();
      const assistantId = newId();

      setMessages((current) => [
        ...current,
        { id: newId(), role: "user", content: prompt, createdAt },
        { id: assistantId, role: "assistant", content: "", createdAt, streaming: true },
      ]);
      setStreaming(true);
      if (title === "New conversation") setTitle(prompt.slice(0, 60));

      const controller = new AbortController();
      abortRef.current = controller;
      let buffer = "";

      try {
        await streamChat(
          {
            chat_session_id: sessionIdRef.current,
            knowledge_base_names: selected,
            last_chat_message: prompt,
          },
          (chunk) => {
            buffer += chunk;
            setMessages((current) =>
              current.map((message) =>
                message.id === assistantId ? { ...message, content: buffer } : message,
              ),
            );
          },
          controller.signal,
        );
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          setError(err instanceof Error ? err.message : "The request failed");
        }
      } finally {
        const extracted = extractMeta(buffer);
        const meta = extracted.meta;
        const usage = meta?.usage ?? {};
        const reasoning = usage.reasoning_tokens ?? 0;
        const fallbackUsed =
          typeof usage.total_tokens === "number"
            ? usage.total_tokens - reasoning
            : (usage.prompt_tokens ?? 0) + (usage.completion_tokens ?? 0) - reasoning;
        const used =
          typeof meta?.context_used === "number"
            ? meta.context_used
            : Math.max(0, fallbackUsed);
        const metaWindow =
          typeof meta?.context_window === "number" ? meta.context_window : undefined;

        if (used > 0) setContextUsed(used);
        if (metaWindow) {
          setRuntime((current) =>
            current ? { ...current, context_window: metaWindow } : current,
          );
        }

        setMessages((current) =>
          current.map((message) =>
            message.id === assistantId
              ? {
                  ...message,
                  content: extracted.text || message.content,
                  streaming: false,
                  ...(used > 0 ? { contextUsed: used } : {}),
                  ...(metaWindow ? { contextWindow: metaWindow } : {}),
                }
              : message,
          ),
        );
        setStreaming(false);
        abortRef.current = null;
        await saveConversation();
      }
    },
    [saveConversation, selected, streaming, title, undoLastTurn],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const modelLabel = runtime?.model ?? "Model";
  const shortModel = modelLabel.includes(":") ? modelLabel.split(":")[0] : modelLabel;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 border-b border-[var(--border)] bg-[var(--surface)] px-4 py-3 sm:px-6">
        <h1 className="min-w-0 truncate text-sm font-semibold">{title}</h1>

        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            onClick={() => setSettingsOpen(true)}
            className="pill max-w-[170px]"
            title={runtime ? `${runtime.api_base} · ${runtime.model}` : "Select endpoint and model"}
          >
            <Cpu className="h-3.5 w-3.5 shrink-0" />
            <span className="hidden truncate sm:inline">{shortModel}</span>
            <ChevronDown className="h-3.5 w-3.5 shrink-0" />
          </button>
          <KnowledgeBasePicker
            options={knowledgeBases}
            selected={selected}
            onChange={setSelected}
            disabled={streaming}
          />
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="mx-auto w-full max-w-3xl space-y-6 px-4 py-6 sm:px-6">
            {messages.map((message) =>
              message.role === "user" ? (
                <UserBubble key={message.id} message={message} />
              ) : (
                <AssistantBubble key={message.id} message={message} />
              ),
            )}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {error && (
        <div className="mx-auto w-full max-w-3xl px-4 pb-2 sm:px-6">
          <div className="flex items-center gap-2 rounded-xl border border-rose-500/30 bg-rose-500/10 px-3.5 py-2.5 text-xs text-rose-600 dark:text-rose-300">
            <TriangleAlert className="h-4 w-4 shrink-0" />
            {error}
          </div>
        </div>
      )}

      <ContextMeter
        used={contextUsed}
        window={
          runtime?.context_window ??
          [...messages].reverse().find((message) => typeof message.contextWindow === "number")
            ?.contextWindow ??
          0
        }
      />
      <Composer streaming={streaming} onSend={send} onStop={stop} />

      <ModelSettingsModal
        open={settingsOpen}
        current={runtime}
        onClose={() => setSettingsOpen(false)}
        onSaved={(saved) => {
          setRuntime(saved);
          setContextUsed(null);
          toast.push("Model settings saved", "success");
        }}
      />
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex h-full flex-col items-center justify-center px-6 py-10 text-center">
      <div className="relative">
        <div className="absolute inset-0 -z-10 rounded-full bg-indigo-500/20 blur-2xl" />
        <BrandMark className="h-14 w-14" />
      </div>
      <h1 className="mt-5 text-2xl font-semibold tracking-tight sm:text-3xl">Ask your documents</h1>
    </div>
  );
}

interface ComposerProps {
  streaming: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
}

function Composer({ streaming, onSend, onStop }: ComposerProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const element = textareaRef.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, 160)}px`;
  }, [value]);

  useEffect(() => {
    if (!streaming) textareaRef.current?.focus();
  }, [streaming]);

  const submit = () => {
    const text = value.trim();
    if (!text || streaming) return;
    onSend(text);
    setValue("");
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <div className="border-t border-[var(--border)] bg-[var(--canvas)]/80 backdrop-blur">
      <div className="safe-bottom mx-auto w-full max-w-3xl px-4 pt-3 sm:px-6">
        <div className="surface flex items-end gap-2 rounded-2xl p-2 pl-4">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(event) => setValue(event.target.value)}
            onKeyDown={onKeyDown}
            rows={1}
            placeholder="Ask a question about your documents…"
            className="max-h-40 min-h-[40px] flex-1 resize-none bg-transparent py-2 text-sm leading-relaxed outline-none placeholder:text-[var(--ink-muted)]"
          />
          {streaming ? (
            <button
              type="button"
              onClick={onStop}
              className="btn h-9 w-9 shrink-0 rounded-xl bg-[var(--ink)] text-[var(--surface)] hover:opacity-80"
              aria-label="Stop generating"
              title="Stop generating"
            >
              <Square className="h-3.5 w-3.5" />
            </button>
          ) : (
            <button
              type="button"
              onClick={submit}
              disabled={!value.trim()}
              className="btn h-9 w-9 shrink-0 rounded-xl bg-[var(--brand)] text-white hover:brightness-110"
              aria-label="Send message"
              title="Send"
            >
              <ArrowUp className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}