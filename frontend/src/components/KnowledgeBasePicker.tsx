import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, Database } from "lucide-react";
import { cn } from "../lib/utils";
import { NO_RAG } from "../lib/constants";

interface Props {
  options: string[];
  selected: string[];
  onChange: (next: string[]) => void;
  disabled?: boolean;
}

export function KnowledgeBasePicker({ options, selected, onChange, disabled }: Props) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open]);

  const toggle = (name: string) => {
    const isSelected = selected.includes(name);

    if (name === NO_RAG) {
      onChange(isSelected ? [] : [NO_RAG]);
      return;
    }

    const withoutSentinel = selected.filter((item) => item !== NO_RAG);
    if (isSelected) {
      onChange(withoutSentinel.filter((item) => item !== name));
    } else {
      onChange([...withoutSentinel, name]);
    }
  };

  const label = (() => {
    if (selected.length === 0) return "Select sources";
    if (selected.length === 1) return selected[0];
    return `${selected.length} sources`;
  })();

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        className="btn-outline max-w-[280px]"
        onClick={() => setOpen((value) => !value)}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <Database className="h-4 w-4 text-[var(--brand)]" />
        <span className="truncate">{label}</span>
        <ChevronDown className={cn("h-4 w-4 transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <div className="surface absolute right-0 z-30 mt-2 w-72 animate-fade-up rounded-xl p-1.5">
          <p className="px-2.5 pb-1.5 pt-2 text-[11px] font-medium uppercase tracking-wide muted">
            Knowledge bases
          </p>
          <div className="max-h-72 overflow-y-auto">
            {options.map((option) => {
              const checked = selected.includes(option);
              return (
                <button
                  key={option}
                  type="button"
                  onClick={() => toggle(option)}
                  className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm transition hover:bg-[var(--surface-muted)]"
                >
                  <span
                    className={cn(
                      "flex h-4 w-4 shrink-0 items-center justify-center rounded border transition",
                      checked
                        ? "border-[var(--brand)] bg-[var(--brand)] text-white"
                        : "border-[var(--border-strong)]",
                    )}
                  >
                    {checked && <Check className="h-3 w-3" />}
                  </span>
                  <span className="truncate">{option}</span>
                </button>
              );
            })}
            {options.length === 0 && <p className="px-2.5 py-3 text-sm muted">No knowledge bases yet.</p>}
          </div>
        </div>
      )}
    </div>
  );
}