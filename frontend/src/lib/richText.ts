import type { ChatTurnMeta } from "../types";

export interface RichAnswer {
  thinking: string;
  answer: string;
  references: string[];
  thinkingOpen: boolean;
}

const OPEN_THINK = "<think";
const CLOSE_THINK = "</think>";
const META_RE = /<meta>([\s\S]*?)<\/meta>/g;

/**
 * The backend streams reasoning between  thinking…</think> and a reference
 * block wrapped in <ref>…</ref>, followed by a <meta> JSON block carrying token
 * usage and the model's context window.
 */
export function parseAnswer(raw: string): RichAnswer {
  let thinking = "";
  let rest = raw;
  let thinkingOpen = false;

  const openIndex = raw.indexOf(OPEN_THINK);
  if (openIndex !== -1) {
    const closeIndex = raw.indexOf(CLOSE_THINK, openIndex + OPEN_THINK.length);
    if (closeIndex === -1) {
      thinking = raw.slice(openIndex + OPEN_THINK.length);
      rest = raw.slice(0, openIndex);
      thinkingOpen = true;
    } else {
      thinking = raw.slice(openIndex + OPEN_THINK.length, closeIndex);
      rest = raw.slice(0, openIndex) + raw.slice(closeIndex + CLOSE_THINK.length);
    }
  }

  const references: string[] = [];
  rest = rest.replace(/<ref>([\s\S]*?)<\/ref>/g, (_match, block: string) => {
    references.push(...parseReferenceBlock(block));
    return "";
  });
  rest = rest.replace(META_RE, "");
  // Hide a partially streamed metadata block until the closing tag arrives.
  rest = rest.replace(/<meta>[\s\S]*$/g, "");

  return {
    thinking: thinking.trim(),
    answer: rest.trim(),
    references,
    thinkingOpen,
  };
}

export function parseReferenceBlock(block: string): string[] {
  return block
    .split("\n")
    .map((line) => line.replace(/\*\*References:\*\*/i, "").trim())
    .filter(Boolean)
    .map((line) => line.replace(/^\d+\.\s*/, "").trim());
}

export function extractMeta(raw: string): { text: string; meta: ChatTurnMeta | null } {
  let meta: ChatTurnMeta | null = null;
  const text = raw.replace(META_RE, (_match, body: string) => {
    try {
      const parsed = JSON.parse(body) as ChatTurnMeta;
      if (parsed && typeof parsed === "object") meta = parsed;
    } catch {
      /* ignore malformed metadata */
    }
    return "";
  });
  return { text: text.trim(), meta };
}