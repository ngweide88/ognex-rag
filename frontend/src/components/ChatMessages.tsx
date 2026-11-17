import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { BrandMark } from "./Brand";
import { Markdown } from "./Markdown";
import { References } from "./References";
import { ThinkingBlock } from "./ThinkingBlock";
import { parseAnswer } from "../lib/richText";
import { copyText, formatTime } from "../lib/utils";
import type { ChatMessage } from "../types";

export function UserBubble({ message }: { message: ChatMessage }) {
  return (
    <div className="flex animate-fade-up justify-end">
      <div className="max-w-[85%] sm:max-w-[75%]">
        <div className="rounded-2xl rounded-br-md bg-[var(--user-bubble)] px-4 py-2.5 text-[14px] leading-relaxed text-[var(--ink)]">
          <p className="whitespace-pre-wrap">{message.content}</p>
        </div>
        <p className="mt-1 pr-1 text-right text-[10px] muted">{formatTime(message.createdAt)}</p>
      </div>
    </div>
  );
}

function TypingDots() {
  return (
    <div className="flex items-center gap-1 py-1.5">
      <span className="dot h-1.5 w-1.5 rounded-full bg-[var(--ink-muted)]" />
      <span className="dot h-1.5 w-1.5 rounded-full bg-[var(--ink-muted)]" />
      <span className="dot h-1.5 w-1.5 rounded-full bg-[var(--ink-muted)]" />
    </div>
  );
}

export function AssistantBubble({ message }: { message: ChatMessage }) {
  const [copied, setCopied] = useState(false);
  const parsed = parseAnswer(message.content || "");
  const streaming = Boolean(message.streaming);
  const showDots = streaming && !parsed.thinking && !parsed.answer;

  const copy = async () => {
    if (await copyText(parsed.answer)) {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    }
  };

  return (
    <div className="flex animate-fade-up gap-3">
      <BrandMark className="mt-0.5 h-8 w-8 shrink-0" />
      <div className="min-w-0 flex-1">
        <ThinkingBlock content={parsed.thinking} streaming={streaming && parsed.thinkingOpen} />

        {parsed.answer ? (
          <Markdown streaming={streaming} >{parsed.answer}</Markdown>
        ) : (
          showDots && <TypingDots />
        )}

        {!streaming && <References references={parsed.references} />}

        {!streaming && parsed.answer && (
          <div className="mt-3 flex items-center gap-1">
            <button
              type="button"
              onClick={copy}
              className="btn-ghost p-1.5"
              aria-label="Copy answer"
              title="Copy answer"
            >
              {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}