import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  Database,
  MessageSquare,
  Moon,
  MoreHorizontal,
  Pencil,
  Plus,
  Search,
  Sun,
  Trash2,
  X,
} from "lucide-react";
import { api } from "../lib/api";
import type { HistoryChat, HistoryGroup } from "../types";
import { useTheme } from "../hooks/useTheme";
import { useToast } from "./Toast";
import { BrandMark, BrandName } from "./Brand";
import { Modal } from "./Modal";
import { cn } from "../lib/utils";

interface Props {
  onNavigate?: () => void;
}

export function Sidebar({ onNavigate }: Props) {
  const navigate = useNavigate();
  const location = useLocation();
  const { theme, toggle } = useTheme();
  const toast = useToast();

  const [groups, setGroups] = useState<HistoryGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [openMenu, setOpenMenu] = useState<number | null>(null);
  const [renameTarget, setRenameTarget] = useState<HistoryChat | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<HistoryChat | null>(null);
  const [busy, setBusy] = useState(false);

  const activeId = (location.state as { historyId?: number } | null)?.historyId ?? null;

  const loadHistory = useCallback(async () => {
    try {
      const data = await api.history();
      setGroups(data.result);
    } catch (error) {
      toast.push(error instanceof Error ? error.message : "Could not load chat history", "error");
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    void loadHistory();
    const refresh = () => void loadHistory();
    window.addEventListener("ognex:history-updated", refresh);
    return () => window.removeEventListener("ognex:history-updated", refresh);
  }, [loadHistory]);

  useEffect(() => {
    if (!openMenu) return;
    const close = () => setOpenMenu(null);
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, [openMenu]);

  const filteredGroups = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return groups
      .map((group) => ({
        ...group,
        chats: needle
          ? group.chats.filter((chat) => chat.title.toLowerCase().includes(needle))
          : group.chats,
      }))
      .filter((group) => group.chats.length > 0);
  }, [groups, query]);

  const openChat = (chat: HistoryChat) => {
    navigate("/", { state: { historyId: chat.id, title: chat.title } });
    onNavigate?.();
  };

  const startNewChat = () => {
    navigate("/", { state: { newChat: Date.now() } });
    onNavigate?.();
  };

  const submitRename = async () => {
    if (!renameTarget || !renameValue.trim()) return;
    setBusy(true);
    try {
      await api.renameHistory(renameTarget.id, renameValue.trim());
      setRenameTarget(null);
      await loadHistory();
      window.dispatchEvent(new Event("ognex:history-updated"));
      toast.push("Chat renamed", "success");
    } catch (error) {
      toast.push(error instanceof Error ? error.message : "Rename failed", "error");
    } finally {
      setBusy(false);
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setBusy(true);
    try {
      await api.deleteHistory(deleteTarget.id);
      setDeleteTarget(null);
      if (activeId === deleteTarget.id) startNewChat();
      await loadHistory();
      window.dispatchEvent(new Event("ognex:history-updated"));
      toast.push("Chat deleted", "success");
    } catch (error) {
      toast.push(error instanceof Error ? error.message : "Delete failed", "error");
    } finally {
      setBusy(false);
    }
  };

  const go = (path: string) => {
    navigate(path);
    onNavigate?.();
  };

  return (
    <div className="flex h-full flex-col border-r border-[var(--border)] bg-[var(--surface)]">
      <div className="flex items-center gap-2.5 px-4 pb-3 pt-5">
        <BrandMark />
        <BrandName />
        <button className="btn-ghost ml-auto p-2 lg:hidden" onClick={onNavigate} aria-label="Close menu">
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="px-3">
        <button className="btn-primary w-full" onClick={startNewChat}>
          <Plus className="h-4 w-4" />
          New chat
        </button>
      </div>

      <div className="px-3 pt-3">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 muted" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search chats"
            className="field py-2 pl-8 text-[13px]"
          />
        </div>
      </div>

      <div className="mt-4 flex-1 overflow-y-auto px-2 pb-4">
        {loading && <p className="px-2 py-4 text-xs muted">Loading…</p>}
        {!loading && filteredGroups.length === 0 && (
          <p className="px-2 py-4 text-xs muted">
            {query ? "No matching chats." : "Your conversations will appear here."}
          </p>
        )}

        {filteredGroups.map((group) => (
          <div key={group.category} className="mb-3">
            <p className="px-2 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-wider muted">
              {group.category}
            </p>
            {group.chats.map((chat) => (
              <div
                key={chat.id}
                className={cn(
                  "group relative flex items-center rounded-lg transition",
                  activeId === chat.id
                    ? "bg-[var(--brand-soft)] text-[var(--brand-ink)]"
                    : "hover:bg-[var(--surface-muted)]",
                )}
              >
                <button
                  type="button"
                  onClick={() => openChat(chat)}
                  className="flex min-w-0 flex-1 items-center gap-2 px-2 py-2 text-left text-[13px]"
                >
                  <MessageSquare className="h-3.5 w-3.5 shrink-0 opacity-60" />
                  <span className="truncate">{chat.title}</span>
                </button>
                <button
                  type="button"
                  className="mr-1 rounded-md p-1.5 opacity-0 transition group-hover:opacity-100 hover:bg-black/5 dark:hover:bg-white/10"
                  onClick={(event) => {
                    event.stopPropagation();
                    setOpenMenu((current) => (current === chat.id ? null : chat.id));
                  }}
                  aria-label="Chat options"
                >
                  <MoreHorizontal className="h-4 w-4" />
                </button>

                {openMenu === chat.id && (
                  <div className="surface absolute right-1 top-9 z-20 w-36 rounded-lg p-1 text-[13px]">
                    <button
                      type="button"
                      className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 hover:bg-[var(--surface-muted)]"
                      onClick={() => {
                        setRenameTarget(chat);
                        setRenameValue(chat.title);
                        setOpenMenu(null);
                      }}
                    >
                      <Pencil className="h-3.5 w-3.5" /> Rename
                    </button>
                    <button
                      type="button"
                      className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-rose-600 hover:bg-rose-500/10 dark:text-rose-400"
                      onClick={() => {
                        setDeleteTarget(chat);
                        setOpenMenu(null);
                      }}
                    >
                      <Trash2 className="h-3.5 w-3.5" /> Delete
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        ))}
      </div>

      <div className="flex items-center gap-1 border-t border-[var(--border)] p-3">
        <button className="btn-ghost flex-1 justify-start" onClick={() => go("/knowledge-bases")}>
          <Database className="h-4 w-4" /> Knowledge bases
        </button>
        <button className="btn-ghost p-2" onClick={toggle} aria-label="Toggle theme">
          {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </button>
      </div>

      <Modal
        open={Boolean(renameTarget)}
        title="Rename chat"
        onClose={() => setRenameTarget(null)}
        footer={
          <>
            <button className="btn-outline" onClick={() => setRenameTarget(null)}>
              Cancel
            </button>
            <button className="btn-primary" onClick={submitRename} disabled={busy || !renameValue.trim()}>
              Save
            </button>
          </>
        }
      >
        <input
          className="field"
          value={renameValue}
          onChange={(event) => setRenameValue(event.target.value)}
          onKeyDown={(event) => event.key === "Enter" && submitRename()}
          autoFocus
        />
      </Modal>

      <Modal
        open={Boolean(deleteTarget)}
        title="Delete chat?"
        description={`"${deleteTarget?.title ?? ""}" will be removed permanently.`}
        onClose={() => setDeleteTarget(null)}
        footer={
          <>
            <button className="btn-outline" onClick={() => setDeleteTarget(null)}>
              Cancel
            </button>
            <button
              className="btn px-4 py-2.5 text-white bg-rose-600 hover:brightness-110"
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