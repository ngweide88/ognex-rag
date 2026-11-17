import { useEffect, useState } from "react";
import { Brain, ChevronDown, Loader2 } from "lucide-react";
import { cn } from "../lib/utils";

interface Props {
  content: string;
  streaming: boolean;
}

export function ThinkingBlock({ content, streaming }: Props) {
  const [open, setOpen] = useState(true);

  // Collapse automatically once the answer starts streaming.
  useEffect(() => {
    if (!streaming && content) setOpen(false);
  }, [streaming, content]);

  if (!content) return null;

  return (
    <div className="mb-3 overflow-hidden rounded-xl border border-dashed border-[var(--border-strong)] bg-[var(--surface-muted)]">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center gap-2 px-3.5 py-2 text-left text-xs font-medium muted transition hover:text-[var(--ink)]"
      >
        {streaming ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin text-[var(--brand)]" />
        ) : (
          <Brain className="h-3.5 w-3.5 text-[var(--brand)]" />
        )}
        <span>{streaming ? "Reasoning…" : "Reasoning"}</span>
        <ChevronDown
          className={cn("ml-auto h-3.5 w-3.5 transition-transform", open && "rotate-180")}
        />
      </button>
      {open && (
        <div className="max-h-64 overflow-y-auto whitespace-pre-wrap px-3.5 pb-3 text-xs leading-relaxed muted">
          {content}
        </div>
      )}
    </div>
  );
}