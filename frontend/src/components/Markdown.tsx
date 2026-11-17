import { useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, Copy } from "lucide-react";
import { copyText } from "../lib/utils";

function CodeBlock({ language, value }: { language: string; value: string }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    if (await copyText(value)) {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    }
  };

  return (
    <div className="my-4 overflow-hidden rounded-xl border border-[var(--border)]">
      <div className="flex items-center justify-between border-b border-[var(--border)] bg-[var(--surface-muted)] px-3 py-1.5 text-[11px] font-medium uppercase tracking-wide muted">
        <span>{language || "text"}</span>
        <button type="button" onClick={copy} className="inline-flex items-center gap-1 hover:text-[var(--ink)]">
          {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="overflow-x-auto bg-[#0d1117] p-4 text-[13px] leading-relaxed text-[#e6edf3]">
        <code>{value}</code>
      </pre>
    </div>
  );
}

function textOf(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (node && typeof node === "object" && "props" in node) {
    return textOf((node as { props: { children?: ReactNode } }).props.children);
  }
  return "";
}

export function Markdown({ children, streaming = false }: { children: string; streaming?: boolean }) {
  return (
    <div className={streaming ? "prose prose-chat max-w-none stream-caret" : "prose prose-chat max-w-none"}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ className, children: codeChildren, ...props }) {
            const language = className?.replace("language-", "") ?? "";
            const value = textOf(codeChildren).replace(/\n$/, "");
            const isBlock = Boolean(className) || value.includes("\n");
            if (!isBlock) {
              return (
                <code className={className} {...props}>
                  {codeChildren}
                </code>
              );
            }
            return <CodeBlock language={language} value={value} />;
          },
          pre({ children: preChildren }) {
            return <>{preChildren}</>;
          },
          a({ href, children: linkChildren }) {
            return (
              <a href={href} target="_blank" rel="noreferrer">
                {linkChildren}
              </a>
            );
          },
          table({ children: tableChildren }) {
            return (
              <div className="my-4 overflow-x-auto rounded-xl border border-[var(--border)]">
                <table className="m-0 w-full">{tableChildren}</table>
              </div>
            );
          },
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}