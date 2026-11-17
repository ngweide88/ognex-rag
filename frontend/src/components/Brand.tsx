import { cn } from "../lib/utils";

export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" fill="none" className={cn("h-8 w-8", className)} aria-hidden>
      <rect x="1" y="1" width="30" height="30" rx="9" fill="url(#ognex-gradient)" />
      <circle cx="16" cy="16" r="5.2" stroke="white" strokeWidth="2" />
      <circle cx="16" cy="7.4" r="2.1" fill="white" />
      <circle cx="16" cy="24.6" r="2.1" fill="white" />
      <circle cx="8" cy="12" r="1.8" fill="white" opacity="0.85" />
      <circle cx="24" cy="20" r="1.8" fill="white" opacity="0.85" />
      <defs>
        <linearGradient id="ognex-gradient" x1="0" y1="0" x2="32" y2="32">
          <stop stopColor="#6366f1" />
          <stop offset="1" stopColor="#8b5cf6" />
        </linearGradient>
      </defs>
    </svg>
  );
}

export function BrandName() {
  return (
    <div className="text-[15px] font-semibold tracking-tight">
      Ognex <span className="text-[var(--brand)]">RAG</span>
    </div>
  );
}