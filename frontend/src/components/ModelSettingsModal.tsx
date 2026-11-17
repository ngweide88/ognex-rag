import { useCallback, useEffect, useState } from "react";
import { Loader2, RefreshCw } from "lucide-react";
import { api } from "../lib/api";
import type { ModelInfo, RuntimeSettings } from "../types";
import { Modal } from "./Modal";

interface Props {
  open: boolean;
  current: RuntimeSettings | null;
  onClose: () => void;
  onSaved: (settings: RuntimeSettings) => void;
}

const CONTEXT_KEYS = [
  "context_length",
  "max_model_len",
  "max_context_length",
  "context_window",
  "max_context",
] as const;

function contextOf(modelId: string, models: ModelInfo[]): number | null {
  const model = models.find((item) => item.id === modelId);
  if (!model) return null;
  for (const key of CONTEXT_KEYS) {
    const value = model[key];
    if (typeof value === "number" && value > 1024) return value;
  }
  return null;
}

export function ModelSettingsModal({ open, current, onClose, onSaved }: Props) {
  const [apiBase, setApiBase] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const [contextWindow, setContextWindow] = useState("");
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const loadModels = useCallback(async (base: string, key: string) => {
    if (!base.trim()) {
      setError("Enter an endpoint URL first");
      return;
    }
    setLoading(true);
    setError(null);
    setStatus(null);
    try {
      const result = await api.models({
        api_base: base.trim(),
        ...(key.trim() ? { api_key: key.trim() } : {}),
      });
      if (!result.ok) {
        setModels([]);
        setError(result.error || "Endpoint unreachable");
        return;
      }
      setModels(result.models);
      setStatus(`${result.models.length} model${result.models.length === 1 ? "" : "s"} found`);
      if (result.models.length > 0) {
        const nextModel =
          result.models.find((item) => item.id === model)?.id ?? result.models[0].id;
        setModel(nextModel);
        const detected = contextOf(nextModel, result.models);
        if (detected) setContextWindow(String(detected));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load models");
    } finally {
      setLoading(false);
    }
  }, [model]);

  useEffect(() => {
    if (!open) return;
    const base = current?.api_base ?? "";
    const selected = current?.model ?? "";
    setApiBase(base);
    setApiKey("");
    setModel(selected);
    setContextWindow(current?.context_window ? String(current.context_window) : "");
    setModels([]);
    setError(null);
    setStatus(null);
    if (base) void loadModels(base, "");
    // Intentionally only on open: loadModels changes identity with the model.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const selectModel = (modelId: string) => {
    setModel(modelId);
    const detected = contextOf(modelId, models);
    if (detected) setContextWindow(String(detected));
  };

  const save = async () => {
    if (!model) {
      setError("Select a model");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const saved = await api.saveSettings({
        api_base: apiBase.trim(),
        ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}),
        model,
        context_window: contextWindow ? Number(contextWindow) : undefined,
      });
      onSaved(saved);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save settings");
    } finally {
      setSaving(false);
    }
  };

  const selected = models.find((item) => item.id === model);

  return (
    <Modal
      open={open}
      title="Endpoint and model"
      description="Choose any OpenAI-compatible endpoint. The context window is detected from its model metadata."
      onClose={onClose}
      footer={
        <>
          <button className="btn-outline" onClick={onClose}>
            Cancel
          </button>
          <button className="btn-primary" onClick={save} disabled={saving || loading || !model}>
            {saving && <Loader2 className="h-4 w-4 animate-spin" />}
            Save
          </button>
        </>
      }
    >
      <div className="space-y-4">
        <div>
          <label className="mb-1.5 block text-xs font-medium muted" htmlFor="api-base">
            Endpoint
          </label>
          <div className="flex gap-2">
            <input
              id="api-base"
              className="field"
              value={apiBase}
              onChange={(event) => setApiBase(event.target.value)}
              placeholder="http://127.0.0.1:5000"
              spellCheck={false}
            />
            <button
              type="button"
              className="btn-outline shrink-0"
              onClick={() => void loadModels(apiBase, apiKey)}
              disabled={loading}
              title="Load models from this endpoint"
            >
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              Load
            </button>
          </div>
        </div>

        <div>
          <label className="mb-1.5 block text-xs font-medium muted" htmlFor="api-key">
            API key
          </label>
          <input
            id="api-key"
            type="password"
            className="field"
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
            placeholder={current?.api_key_set ? "Saved — leave blank to keep" : "Optional"}
            autoComplete="off"
          />
        </div>

        <div>
          <label className="mb-1.5 block text-xs font-medium muted" htmlFor="model">
            Model
          </label>
          <select
            id="model"
            className="field"
            value={model}
            onChange={(event) => selectModel(event.target.value)}
            disabled={models.length === 0}
          >
            {models.length === 0 && <option value={model}>{model || "Load models first"}</option>}
            {models.map((item) => {
              const window = contextOf(item.id, models);
              return (
                <option key={item.id} value={item.id}>
                  {item.id}
                  {window ? ` · ${window.toLocaleString()} ctx` : ""}
                </option>
              );
            })}
          </select>
          {selected && (
            <p className="mt-1.5 text-[11px] muted">
              {selected.owned_by ? `Owner ${selected.owned_by} · ` : ""}
              metadata: {" "}
              {CONTEXT_KEYS.map((key) =>
                typeof selected[key] === "number" ? `${key}=${selected[key]}` : null,
              )
                .filter(Boolean)
                .join(", ") || "no context fields reported"}
            </p>
          )}
        </div>

        <div>
          <label className="mb-1.5 block text-xs font-medium muted" htmlFor="context-window">
            Context window (tokens)
          </label>
          <input
            id="context-window"
            type="number"
            min={1024}
            step={1024}
            className="field font-mono"
            value={contextWindow}
            onChange={(event) => setContextWindow(event.target.value)}
            placeholder="Detected from model metadata"
          />
        </div>

        {status && !error && <p className="text-xs text-emerald-600 dark:text-emerald-400">{status}</p>}
        {error && <p className="text-xs text-rose-600 dark:text-rose-400">{error}</p>}
      </div>
    </Modal>
  );
}