import { BookOpen } from "lucide-react";

export function References({ references }: { references: string[] }) {
  if (!references.length) return null;

  return (
    <div className="mt-4 rounded-xl border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-3">
      <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide muted">
        <BookOpen className="h-3.5 w-3.5" />
        Sources
      </div>
      <ul className="space-y-1.5">
        {references.map((reference) => {
          const [file, page] = reference.split(/,\s*page\s*/i);
          return (
            <li key={reference} className="flex flex-wrap items-baseline gap-x-2 text-xs">
              <span className="font-medium text-[var(--ink)]">{file}</span>
              {page && <span className="muted">page {page}</span>}
            </li>
          );
        })}
      </ul>
    </div>
  );
}