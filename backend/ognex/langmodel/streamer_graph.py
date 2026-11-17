"""LangGraph RAG pipeline.

Graph shape (one linear path, with two conditional exits):

    guardrail ─┬─ unsecure ──────────────► exit_unsafe
               ├─ no-RAG ────────────────► construct_prompt
               └─ RAG ─► sentence_structure_editor ─► retrieve_context
                        ─► rag_context_list_to_string ─► process_reference
                        ─► construct_prompt ─► generate_response
                        ─► yield_reference ─► generate_title ─► END

Every node lives once in ``GraphStreamer``; only the chat client is injected,
so a new provider means implementing ``ChatClient`` and nothing else.

Token streaming uses LangGraph's custom stream writer, which works for any
client (OpenAI SDK, custom HTTP client) and avoids backend-specific
stream modes.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Iterator

from langgraph.config import get_stream_writer
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from ognex import runtime_settings
from ognex.cache.chat_history import insert_history_into_cache
from ognex.cache.session_cache import insert_item_into_cache
from ognex.config import settings
from ognex.constants import (
    FE_ASSISTANT,
    get_guardrail_prompt,
    get_no_rag_system_prompt,
    get_rag_system_prompt,
    get_sentence_structure_editor_prompt,
    get_title_prompt,
)
from ognex.helper import merge_pages
from ognex.langmodel.client import ChatClient
from ognex.langmodel.helper import time_node
from ognex.retriever.base import initialise_retriever_from_config

UNSAFE_MESSAGE = (
    "⚠️ Your query appears to contain unsafe instructions. Please rephrase."
)

ANSWER_MAX_TOKENS = 1_000_000
AUX_MAX_TOKENS = 16_364


class ChatState(TypedDict, total=False):
    sys_prompt: str
    chat_hist: list[dict]
    user_qn: str
    updated_user_qn: str
    rag_ctx: list[str]
    rag_str: str
    ref_text: str
    response: str
    chat_session_id: str
    embedding: object
    kb_name: list[str]
    guard: str
    Messages: list[dict[str, str]]


def _message_text(message: dict) -> str:
    """Flatten a chat message whose content may be a string or multimodal list."""
    content = message.get("content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return " ".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ).strip()
    return str(content).strip()


class GraphStreamer:
    def __init__(
        self,
        chat_client: ChatClient,
        model_name: str | None = None,
        context_window: int | None = None,
    ) -> None:
        self.chat_client = chat_client
        runtime = runtime_settings.load()
        self.model_name = model_name or runtime.model
        self.max_context = context_window or runtime.context_window

    # ------------------------------------------------------------------ nodes
    @time_node
    def guardrail(self, state: ChatState) -> dict:
        query = state["user_qn"].split("ctx:")[0]
        response = self.chat_client.invoke(get_guardrail_prompt(query), max_tokens=AUX_MAX_TOKENS)
        guard = "unsecure" if "unsecure" in response.lower() else "secure"
        user_qn = state["user_qn"].replace("ctx:", "context: ")
        return {**state, "guard": guard, "user_qn": user_qn}

    @time_node
    def sentence_structure_editor(self, state: ChatState) -> dict:
        previous_qn = ""
        user_messages = [
            msg for msg in state.get("chat_hist", []) if msg.get("role") == "user"
        ]
        if len(user_messages) >= 2:
            previous_qn = _message_text(user_messages[-2])

        current_qn = state.get("user_qn", "").strip()
        response = self.chat_client.invoke(
            get_sentence_structure_editor_prompt(previous_qn, current_qn), max_tokens=AUX_MAX_TOKENS
        ).strip()

        rewrite = re.search(r"<rewrite>(.*?)</rewrite>", response, re.DOTALL)
        refers = re.search(r"<refers>(yes|no)</refers>", response, re.IGNORECASE)

        updated = rewrite.group(1).strip() if rewrite else current_qn
        needs_rewrite = bool(refers and refers.group(1).lower() == "yes")
        return {**state, "updated_user_qn": updated if needs_rewrite else ""}

    @time_node
    def retrieve_context(self, state: ChatState) -> dict:
        retriever = initialise_retriever_from_config(state["kb_name"], state["embedding"])
        query = state.get("updated_user_qn") or state.get("user_qn") or ""
        contexts = retriever.get_context(query)
        return {**state, "rag_ctx": contexts[: settings.top_k_contexts]}

    @staticmethod
    def rag_context_list_to_string(state: ChatState) -> dict:
        rag_str = "".join(
            f"Context {index + 1}: {context}\n\n"
            for index, context in enumerate(state.get("rag_ctx") or [])
        )
        return {**state, "rag_str": rag_str}

    @staticmethod
    def clean_rag_context(text: str) -> str:
        text = re.sub(
            r"<\s*(?:ref|reference)[^>]*?>.*?</\s*(?:ref|reference)\s*>",
            "",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        text = re.sub(
            r"S(?:ingapore)?\s+Statutes?\s+Online\nCurrent.*?PDF created date on:\s*\d{2} [A-Za-z]{3}(?:,\s*\d{4})?",
            "",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        text = re.sub(r"\[\s*(?:\d+(?:/\d{4})?(?:\s*;\s*\d+(?:/\d{4})?)*|[a-z]+/\w+)\s*\]", "", text)
        text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"(\d)([a-zA-Z])", r"\1 \2", text)
        return text.strip()

    def construct_prompt(self, state: ChatState) -> dict:
        is_no_rag = state.get("kb_name") == ["None (No RAG)"]
        user_qn = state.get("updated_user_qn") or state.get("user_qn")
        if not user_qn:
            raise ValueError("Both user_qn and updated_user_qn are missing from state")

        sys_prompt = (
            get_no_rag_system_prompt(self.model_name)
            if is_no_rag
            else state.get("sys_prompt") or get_rag_system_prompt(self.model_name)
        )

        messages = [{"role": "system", "content": sys_prompt}]

        rag_context = ""
        if not is_no_rag and state.get("rag_str"):
            rag_context = self.clean_rag_context(state["rag_str"])

        # Keep history inside the context budget, newest messages first. The
        # system prompt and retrieved context are reserved up front; the rest
        # of the window is filled with the most recent turns that still fit.
        budget = int((self.max_context - 4325 - 2500) * 2.5) - 500
        trimmed: list[dict] = []
        used = 0
        for message in reversed(state.get("chat_hist") or []):
            content = message.get("content", "")
            length = len(content) if isinstance(content, str) else len(str(content))
            if used + length > budget:
                continue
            trimmed.append(message)
            used += length
        trimmed.reverse()

        # The latest user turn is re-appended with retrieved context below.
        if trimmed:
            trimmed.pop()

        messages.extend(trimmed)

        final_user = f"Document context\n {rag_context}User query\n {user_qn}" if rag_context else f"User query\n {user_qn}"

        messages.append({"role": "user", "content": final_user})

        return {**state, "Messages": messages}

    @time_node
    def generate_response(self, state: ChatState) -> dict:
        writer = get_stream_writer()
        full_response = ""
        usage: dict[str, int] | None = None

        for chunk in self.chat_client.stream(state["Messages"], max_tokens=ANSWER_MAX_TOKENS):
            if chunk.usage:
                usage = chunk.usage
            writer(
                {
                    "role": "assistant",
                    "content": chunk.content,
                    "reasoning_content": chunk.reasoning,
                }
            )
            full_response += chunk.content

        if "</think>" in full_response:
            full_response = full_response.split("</think>", 1)[1]

        context_used: int | None = None
        if usage:
            reasoning = int(usage.get("reasoning_tokens") or 0)
            total = usage.get("total_tokens")
            if isinstance(total, int):
                context_used = max(0, total - reasoning)
            else:
                prompt_tokens = int(usage.get("prompt_tokens") or 0)
                completion_tokens = int(usage.get("completion_tokens") or 0)
                context_used = max(0, prompt_tokens + completion_tokens - reasoning)

        if state.get("chat_session_id"):
            content = full_response
            if state.get("ref_text"):
                content += state["ref_text"]
            cached = {"sender": FE_ASSISTANT, "content": content}
            if context_used is not None:
                cached["context_used"] = context_used
                cached["context_window"] = self.max_context
            insert_history_into_cache(state["chat_session_id"], cached)

        writer(
            {
                "meta": {
                    "usage": usage or {},
                    "context_used": context_used,
                    "context_window": self.max_context,
                    "model": self.model_name,
                }
            }
        )

        return {**state, "response": full_response}

    @time_node
    def generate_title(self, state: ChatState) -> dict:
        questions = [
            _message_text(message)
            for message in state.get("chat_hist", [])
            if message.get("role") == "user"
        ]

        # A chat gets one generated title, from its first user query only.
        if len(questions) > 1:
            return state
        if not questions and state.get("user_qn"):
            questions = [state["user_qn"]]

        aggregated = "".join(
            f"{index + 1}: {question}\n"
            for index, question in enumerate(questions)
            if question
        )
        output = self.chat_client.invoke(get_title_prompt(aggregated), max_tokens=AUX_MAX_TOKENS).strip()
        match = re.search(r"<title>(.*?)</title>", output, re.IGNORECASE | re.DOTALL)
        title = (match.group(1) if match else output).strip()
        # Models sometimes omit the closing tag; strip any residual markup.
        title = re.sub(r"</?title[^>]*>", "", title, flags=re.IGNORECASE).strip(" \n\"'")

        # Models occasionally return a generic label; fall back to the first
        # question so the sidebar stays useful.
        if title.lower().strip(" .") in {"", "new chat", "chat", "title", "untitled"}:
            title = questions[0].rstrip(" ?.")[:60] if questions else "New Chat"

        insert_item_into_cache(state["chat_session_id"], "title", title)
        return state

    @time_node
    def process_reference(self, state: ChatState) -> dict:
        references: list[str] = []
        for context in state.get("rag_ctx") or []:
            references.extend(
                ref.strip()
                for ref in re.findall(
                    r"<reference>(.*?)</reference>", context, re.IGNORECASE | re.DOTALL
                )
                if ref.strip()
            )

        unique_references = list(dict.fromkeys(references))

        pdf_pages: dict[str, list[int]] = defaultdict(list)
        other_refs: list[str] = []
        for reference in unique_references:
            match = re.match(r"(.+\.pdf),\s*page\s+(\d+)", reference, re.IGNORECASE)
            if match:
                pdf_pages[match.group(1).strip()].append(int(match.group(2)))
            else:
                other_refs.append(reference)

        aggregated: list[str] = []
        for pdf, pages in pdf_pages.items():
            for start, end in merge_pages(pages):
                aggregated.append(
                    f"{pdf}, page {start}" if start == end else f"{pdf}, page {start} to {end}"
                )
        aggregated.extend(other_refs)

        if not aggregated:
            return {**state, "ref_text": ""}

        ref_text = "\n<ref>**References:**"
        for index, reference in enumerate(aggregated):
            ref_text += f"\n{index + 1}. {reference}"
        ref_text += "</ref>"
        return {**state, "ref_text": ref_text}

    @time_node
    def yield_reference(self, state: ChatState) -> dict:
        if state.get("ref_text"):
            writer = get_stream_writer()
            writer({"role": "assistant", "content": state["ref_text"], "reasoning_content": ""})
        return state

    @staticmethod
    def _unsafe(state: ChatState) -> dict:
        writer = get_stream_writer()
        writer({"role": "assistant", "content": UNSAFE_MESSAGE, "reasoning_content": ""})
        return state

    # ----------------------------------------------------------------- graph
    def _build_graph(self):
        graph = StateGraph(ChatState)
        graph.add_node("guardrail", self.guardrail)
        graph.add_node("sentence_structure_editor", self.sentence_structure_editor)
        graph.add_node("retrieve_context", self.retrieve_context)
        graph.add_node("rag_context_list_to_string", self.rag_context_list_to_string)
        graph.add_node("process_reference", self.process_reference)
        graph.add_node("construct_prompt", self.construct_prompt)
        graph.add_node("generate_response", self.generate_response)
        graph.add_node("yield_reference", self.yield_reference)
        graph.add_node("generate_title", self.generate_title)
        graph.add_node("exit_unsafe", self._unsafe)

        graph.set_entry_point("guardrail")

        def route(state: ChatState) -> str:
            if state.get("guard") == "unsecure":
                return "exit_unsafe"
            if state.get("kb_name") == ["None (No RAG)"]:
                return "construct_prompt"
            return "sentence_structure_editor"

        graph.add_conditional_edges("guardrail", route)
        graph.add_edge("sentence_structure_editor", "retrieve_context")
        graph.add_edge("retrieve_context", "rag_context_list_to_string")
        graph.add_edge("rag_context_list_to_string", "process_reference")
        graph.add_edge("process_reference", "construct_prompt")
        graph.add_edge("construct_prompt", "generate_response")
        graph.add_edge("generate_response", "yield_reference")
        graph.add_edge("yield_reference", "generate_title")
        graph.add_edge("generate_title", END)
        graph.add_edge("exit_unsafe", END)
        return graph.compile()

    # ---------------------------------------------------------------- public
    def stream_response(
        self,
        history: list[dict],
        user_query: str,
        embedding,
        kb_name: list[str],
        chat_session_id: str | None = None,
    ) -> Iterator[str]:
        inputs: ChatState = {
            "sys_prompt": get_rag_system_prompt(self.model_name),
            "chat_hist": history,
            "user_qn": user_query,
            "rag_ctx": [],
            "chat_session_id": chat_session_id or "",
            "embedding": embedding,
            "kb_name": kb_name,
        }

        compiled = self._build_graph()
        thinking_opened = False
        thinking_closed = False
        meta: dict | None = None

        for event in compiled.stream(inputs, stream_mode="custom"):
            if event.get("meta"):
                meta = event["meta"]
                continue
            reasoning = event.get("reasoning_content", "")
            content = event.get("content", "")

            if reasoning and not thinking_opened:
                thinking_opened = True
                yield "<think"
            if reasoning:
                yield reasoning
            if thinking_opened and not reasoning and content and not thinking_closed:
                yield "</think>"
                thinking_closed = True
            if content:
                yield content

        if meta:
            yield f"\n<meta>{json.dumps(meta)}</meta>"


class EndpointStreamer(GraphStreamer):
    """Streams from the configured OpenAI-compatible endpoint."""

    def __init__(
        self,
        chat_client: ChatClient | None = None,
        model_name: str | None = None,
        context_window: int | None = None,
    ) -> None:
        runtime = runtime_settings.load()
        super().__init__(
            chat_client or _default_client(),
            model_name=model_name or runtime.model,
            context_window=context_window or runtime.context_window,
        )


def _default_client() -> ChatClient:
    from ognex.langmodel.client import get_chat_client

    return get_chat_client()