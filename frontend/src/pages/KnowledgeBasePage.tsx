import { useCallback, useEffect, useRef, useState } from "react";
import {
  CheckCircle2,
  Database,
  Loader2,
  Trash2,
  TriangleAlert,
  UploadCloud,
} from "lucide-react";
import { api } from "../lib/api";
import { formatBytes, formatDate } from "../lib/utils";
import type { IngestTask, KnowledgeBaseMeta } from "../types";
import { Modal } from "../components/Modal";
import { useToast } from "../components/Toast";

function StatusBadge({ task }: { task: IngestTask }) {
  if (task.status === "Completed") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
        <CheckCircle2 className="h-3 w-3" /> Completed
      </span>
    );
  }
  if (task.status === "Failed") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-rose-500/10 px-2 py-0.5 text-[11px] font-medium text-rose-600 dark:text-rose-400">
        <TriangleAlert className="h-3 w-3" /> Failed
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 px-2 py-0.5 text-[11px] font-medium text-amber-600 dark:text-amber-400">
      <Loader2 className="h-3 w-3 animate-spin" /> {task.status_text || "Pending"}
    </span>
  );
}

export function KnowledgeBasePage() {
  const toast = useToast();
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBaseMeta[]>([]);
  const [tasks, setTasks] = useState<IngestTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<KnowledgeBaseMeta | null>(null);
  const [busy, setBusy] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const previousPending = useRef<Set<string>>(new Set());

  const loadKnowledgeBases = useCallback(async () => {
    try {
      const data = await api.knowledgeBases();
      setKnowledgeBases(
        [...data.knowledge_bases].sort((a, b) => b.timestamp - a.timestamp),
      );
    } catch (error) {
      toast.push(error instanceof Error ? error.message : "Could not load knowledge bases", "error");
    } finally {
      setLoading(false);
    }
  }, [toast]);

  const loadTasks = useCallback(async () => {
    try {
      const data = await api.tasks();
      setTasks(data.tasks);
    } catch {
      /* the task feed is supplementary */
    }
  }, []);

  useEffect(() => {
    void loadKnowledgeBases();
    void loadTasks();
  }, [loadKnowledgeBases, loadTasks]);

  // Poll while ingestion is running; refresh the table as tasks finish.
  useEffect(() => {
    const pending = new Set(tasks.filter((task) => task.status === "Pending").map((task) => task.task_id));
    const justFinished = tasks.filter(
      (task) => task.status !== "Pending" && previousPending.current.has(task.task_id),
    );
    previousPending.current = pending;

    if (justFinished.length > 0) {
      const latest = justFinished[0];
      toast.push(
        latest.status === "Completed"
          ? `"${latest.kb_name}" is ready`
          : `"${latest.kb_name}" failed: ${latest.status_text}`,
        latest.status === "Completed" ? "success" : "error",
      );
      void loadKnowledgeBases();
    }

    if (pending.size === 0) return;
    const timer = window.setInterval(() => void loadTasks(), 2000);
    return () => window.clearInterval(timer);
  }, [tasks, toast, loadKnowledgeBases, loadTasks]);

  const upload = async (file: File) => {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      toast.push("Only PDF files are accepted", "error");
      return;
    }
    setUploading(true);
    try {
      const result = await api.uploadKnowledgeBase(file);
      toast.push(`Uploaded "${result.knowledge_base}" — ingestion queued`, "success");
      await loadTasks();
    } catch (error) {
      toast.push(error instanceof Error ? error.message : "Upload failed", "error");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setBusy(true);
    try {
      await api.deleteKnowledgeBase(deleteTarget.name);
      toast.push(`Deleted "${deleteTarget.name}"`, "success");
      setDeleteTarget(null);
      await loadKnowledgeBases();
    } catch (error) {
      toast.push(error instanceof Error ? error.message : "Delete failed", "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-6 sm:px-6">
      <div className="mb-6">
        <h1 className="text-xl font-semibold tracking-tight">Knowledge bases</h1>
        <p className="mt-1 text-sm muted">
          Upload a PDF to build the parent/child chunks, embeddings and retrieval collections.
        </p>
      </div>

      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          const file = event.dataTransfer.files?.[0];
          if (file) void upload(file);
        }}
        className={
          dragging
            ? "mb-6 flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-[var(--brand)] bg-[var(--brand-soft)] px-6 py-10 text-center"
            : "mb-6 flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-[var(--border-strong)] bg-[var(--surface-muted)] px-6 py-10 text-center"
        }
      >
        <UploadCloud className="h-8 w-8 text-[var(--brand)]" />
        <p className="mt-3 text-sm font-medium">Drop a PDF here, or choose a file</p>
        <p className="mt-1 text-xs muted">Text is chunked at three granularities and embedded locally.</p>
        <button
          type="button"
          className="btn-outline mt-4"
          disabled={uploading}
          onClick={() => fileInputRef.current?.click()}
        >
          {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <UploadCloud className="h-4 w-4" />}
          {uploading ? "Uploading…" : "Choose PDF"}
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept="application/pdf,.pdf"
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void upload(file);
          }}
        />
      </div>

      <div className="surface mb-6 overflow-hidden rounded-2xl">
        <div className="border-b border-[var(--border)] px-5 py-3">
          <h2 className="text-sm font-semibold">Available knowledge bases</h2>
        </div>
        {loading ? (
          <p className="px-5 py-8 text-sm muted">Loading…</p>
        ) : knowledgeBases.length === 0 ? (
          <div className="flex flex-col items-center gap-2 px-5 py-10 text-center">
            <Database className="h-7 w-7 muted" />
            <p className="text-sm muted">No knowledge bases yet. Upload a PDF to get started.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-[11px] uppercase tracking-wide muted">
                <tr className="border-b border-[var(--border)]">
                  <th className="px-5 py-2.5 font-medium">Name</th>
                  <th className="px-5 py-2.5 font-medium">Uploaded</th>
                  <th className="px-5 py-2.5 font-medium">Size</th>
                  <th className="px-5 py-2.5" />
                </tr>
              </thead>
              <tbody>
                {knowledgeBases.map((kb) => (
                  <tr key={kb.name} className="border-b border-[var(--border)] last:border-0">
                    <td className="px-5 py-3 font-medium">{kb.name}</td>
                    <td className="px-5 py-3 muted">{formatDate(kb.timestamp)}</td>
                    <td className="px-5 py-3 muted">{formatBytes(kb.bytes)}</td>
                    <td className="px-5 py-3 text-right">
                      <button
                        type="button"
                        className="btn-ghost p-2 text-rose-600 hover:text-rose-700 dark:text-rose-400"
                        onClick={() => setDeleteTarget(kb)}
                        aria-label={`Delete ${kb.name}`}
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="surface overflow-hidden rounded-2xl">
        <div className="border-b border-[var(--border)] px-5 py-3">
          <h2 className="text-sm font-semibold">Recent ingestion tasks</h2>
        </div>
        {tasks.length === 0 ? (
          <p className="px-5 py-6 text-sm muted">No ingestion tasks yet.</p>
        ) : (
          <ul className="divide-y divide-[var(--border)]">
            {tasks.slice(0, 8).map((task) => (
              <li key={task.task_id} className="flex flex-wrap items-center gap-3 px-5 py-3 text-sm">
                <span className="font-medium">{task.kb_name}</span>
                <StatusBadge task={task} />
                <span className="ml-auto text-xs muted">{formatDate(task.timestamp)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <Modal
        open={Boolean(deleteTarget)}
        title="Delete knowledge base?"
        description={`"${deleteTarget?.name ?? ""}" and its vector collections will be removed permanently.`}
        onClose={() => setDeleteTarget(null)}
        footer={
          <>
            <button className="btn-outline" onClick={() => setDeleteTarget(null)}>
              Cancel
            </button>
            <button
              className="btn bg-rose-600 px-4 py-2.5 text-white hover:brightness-110"
              onClick={confirmDelete}
              disabled={busy}
            >
              Delete
            </button>
          </>
        }
      />
    </div>
  );
}