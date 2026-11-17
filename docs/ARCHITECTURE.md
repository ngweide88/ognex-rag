# Architecture

Ognex RAG is a single-process Flask application with a LangGraph query
pipeline, embedded Chroma retrieval, SQLite persistence and a React PWA
frontend.

## Components

### API layer — `ognex/backend.py`

An application factory (`create_app`) registers routes, JSON error handlers and
upload limits. Routes are thin: validate input, call a repository or the graph,
and return JSON or a streaming response. In development the frontend reaches the
API through the Vite `/api` proxy, so requests are same-origin.

### Orchestration — `ognex/langmodel/streamer_graph.py`

A LangGraph `StateGraph` with a typed `ChatState`. Nodes are state-to-state
functions decorated with `time_node`, which records per-stage latency into
`logs/node_timings.csv`.

Routing:

- `guardrail` classifies prompt-injection attempts. On `unsecure`, the graph
  exits with a fixed message.
- With **No RAG**, the graph goes straight to prompt construction.
- With RAG, it rewrites the query, retrieves contexts, formats them, extracts
  references, answers, emits citations and generates a conversation title.

Tokens are emitted through LangGraph's `get_stream_writer()` in `custom` stream
mode. The writer path is provider-independent: any `ChatClient` implementation
can feed the same graph.

### Model access — `ognex/langmodel/client.py`

`ChatClient` has two methods:

```python
stream(messages) -> Iterator[TokenChunk]   # TokenChunk(content, reasoning, usage)
invoke(messages) -> str
```

`OpenAICompatibleClient` normalises reasoning output across servers
(`delta.reasoning_content` or `delta.reasoning`) into `TokenChunk.reasoning` and
collects streaming token usage when the server provides it.

### Retrieval — `ognex/retriever/`

Ingestion writes three Chroma collections per knowledge base:

```
kb_<name>_large    child chunks ≈ 500 chars
kb_<name>_medium   child chunks ≈ 250 chars
kb_<name>_small    child chunks ≈ 150 chars
```

Every child points at a parent via `metadata.doc_id`. Parent text lives in
`data/pickle/<name>_docstore.pkl.gz`.

At query time:

1. **Embed once.**
2. **Collect candidates.** For each granularity, query every selected knowledge
   base and merge by cosine distance.
3. **Similarity ranking.** Deduplicate child hits by parent id.
4. **MMR ranking.** Request vectors, then run maximal marginal relevance with
   `λ = 0.9` to balance relevance and diversity.
5. **Fuse.** Six ranked lists (3 sizes × 2 strategies) are combined with
   Reciprocal Rank Fusion: `score(doc) = Σ 1 / (60 + rank)`.
6. **Expand.** Each surviving parent is padded with ±800/1800 characters of
   neighbouring text so the model sees coherent passages.
7. **Truncate.** The graph passes `TOP_K_CONTEXTS` parents to the prompt.

Parent expansion uses offsets recorded while concatenating the docstore, so the
lookup is linear and cannot match an earlier duplicate passage.

### Ingestion — `ognex/dataprep/`

```
PDF → page text + <reference> tags → normalized corpus
    → parent chunks (2.4k chars, short-chunk recombination)
    → child chunks (3 sizes)
    → embeddings → Chroma
    → metadata
```

Progress is written to the task table at each stage (`"40% child chunks"` …), so
the knowledge-base page can poll and show live status. Ingestion runs on a
thread pool; the API returns a task id immediately.

### Persistence — `ognex/database/`

SQLite with WAL mode. Tables are prefixed (`ognex_` by default):

| Table | Purpose |
|---|---|
| `ognex_chat_history` | `data` JSON array of messages, `name` title |
| `ognex_task` | ingestion task state and progress text |

Connections are short-lived and opened per operation, which keeps the ingestion
worker independent from request threads.

### Cache — `ognex/cache/`

Chat state is assembled incrementally: the user turn is appended, the graph
appends the assistant turn, and `/save_chat_history` drains the session into
SQLite. `/undo_chat` removes the latest assistant/user pair. Titles and optional
metadata live in the same session store. The store is bounded, TTL-evicted and
guarded by an `RLock`.

### Runtime model settings

The endpoint and model are selectable at runtime through `/settings` and
`/models`. The backend fetches the endpoint's `/v1/models` metadata, detects a
context window from fields such as `context_length` or `max_model_len`, and
persists the choice to `data/runtime_settings.json`. The raw metadata snapshot
is stored in `backend/endpoint_metadata.json`. Chat turns request streaming
usage (`stream_options.include_usage`) and emit a final `<meta>` block so the UI
can render context consumption against the detected window. The consumed
context (`context_used`, excluding reasoning tokens) and window are stored on
each assistant message, so the meter survives reloads.

### Single-tenant design

There are no accounts, roles or user identifiers. Chat history and ingestion
tasks are global to the installation, so the API needs no authentication
headers. To deploy this as a multi-user service, add an OIDC/JWT middleware in
front of Flask and scope the repository queries by user; the pipeline and UI do
not otherwise change.

## Streaming protocol

The chat endpoint returns `text/event-stream` but writes **raw text chunks**, not
SSE frames. Three lightweight markers carry structure:

| Marker | Meaning | Frontend behaviour |
|---|---|---|
| ` thinking` … `</think>` | reasoning tokens | collapsible panel |
| `<ref>` … `</ref>` | reference block | source list |
| `<meta>` … `</meta>` | usage, context window and model | context meter |

Parsing lives in `frontend/src/lib/richText.ts`. Keeping the transport raw makes
the reader trivial (`response.body.getReader()`), while the markers are
human-readable in logs.

## Failure handling

- **Model endpoint down:** the stream fails, the API logs it, and the client
  receives a user-facing error message in the answer stream.
- **Local embedding model unavailable:** the ONNX embedder falls back to the
  lexical hashing embedder, with a warning.
- **Ingestion failure:** the task is marked `Failed` with the exception type and
  message, visible on the knowledge-base page.
- **Unknown knowledge base:** `/chat` rejects the request before streaming.