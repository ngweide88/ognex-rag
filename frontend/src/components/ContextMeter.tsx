interface Props {
  used: number | null;
  window: number;
}

function format(value: number): string {
  return value.toLocaleString();
}

export function ContextMeter({ used, window }: Props) {
  if (!window) return null;

  const rawPercent = used === null ? null : Math.min(100, (used / window) * 100);
  const percent = rawPercent === null ? null : Math.round(rawPercent);
  const label =
    rawPercent === null
      ? null
      : rawPercent < 1
        ? `${rawPercent.toFixed(2)}%`
        : `${percent}%`;
  const tone =
    percent === null
      ? "var(--brand)"
      : percent >= 90
        ? "#ef4444"
        : percent >= 70
          ? "#f59e0b"
          : "var(--brand)";

  return (
    <div className="mx-auto w-full max-w-3xl px-4 pt-2 sm:px-6">
      <div className="flex items-center justify-between gap-3 text-[10.5px] muted">
        <span>Context</span>
        <span className="truncate font-mono">
          {used === null
            ? `window ${format(window)}`
            : `${format(used)} / ${format(window)}${label ? ` (${label})` : ""}`}
        </span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-[var(--surface-muted)]">
        <div
          className="h-full rounded-full transition-[width] duration-300"
          style={{
            width: used !== null && used > 0 ? `max(${percent ?? 0}%, 2px)` : "0%",
            background: tone,
          }}
        />
      </div>
    </div>
  );
}