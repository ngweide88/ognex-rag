# API reference

Base URL: `http://127.0.0.1:5000`

The app is single-tenant with **no authentication and no accounts**, so no
headers are needed. Add an auth layer in front of Flask before deploying it as a
multi-user service.

---

## System

### `GET /health`

```json
{
  "status": "ok",
  "app": "Ognex RAG",
  "llm_model": "your-chat-model",
  "knowledge_bases": 1
}
```

---

## Endpoint and model

### `GET /settings`

```json
{
  "api_base": "http://127.0.0.1:5000/v1",
  "model": "your-model",
  "context_window": 1048576,
  "api_key_set": false,
  "metadata": { "ok": true, "models": [] }
}
```

### `PUT /settings`

```json
{
  "api_base": "http://127.0.0.1:5000",
  "model": "your-model",
  "context_window": 1048576,
  "api_key": "optional"
}
```

The endpoint is queried for `/v1/models`; an unknown model returns `400`. When
`context_window` is omitted it is detected from the model metadata.

### `GET /models`

Returns the model list and metadata from the currently configured endpoint.

### `POST /models`

```json
{ "api_base": "http://127.0.0.1:5000", "api_key": "optional" }
```

Preview an endpoint before saving it.

## Chat

### `POST /chat`

Returns a raw `text/event-stream` body containing:

- ` thinking…</think>` reasoning,
- plain answer tokens,
- a final `<ref>**References:** …</ref>` block (RAG only),
- a `<meta>{...}</meta>` block with token usage, `context_used` (prompt plus visible answer tokens, excluding reasoning), the model id and its context window.

Request:

```json
{
  "chat_session_id": "8e1c…",
  "knowledge_base_names": ["my_document"],
  "last_chat_message": "How long is temporary access granted for?"
}
```

- Use `["None (No RAG)"]` for ungrounded chat.
- To continue a stored conversation, pass
  `"chat_session_id": "updateChatHistory_<id>"`.
- Unknown knowledge-base names return `400`.

---

## Knowledge bases

### `GET /list_knowledge_base_names`

```json
{ "knowledge_base_names": ["None (No RAG)", "my_document"] }
```

### `GET /list_knowledge_base_with_metadata`

```json
{
  "knowledge_bases": [
    {
      "name": "my_document",
      "timestamp": 1730000000,
      "bytes": 8500,
      "chunk_sizes": [500, 250, 150]
    }
  ]
}
```

### `POST /add_new_knowledge_base`

`multipart/form-data` with a single `file` field (PDF only, ≤ `MAX_UPLOAD_MB`).

```json
{
  "success": true,
  "message": "Task created!",
  "task_id": "6f2…",
  "knowledge_base": "my_document"
}
```

Returns `409` if the knowledge base already exists.

### `GET /list_knowledge_base_tasks`

```json
{
  "tasks": [
    {
      "task_id": "6f2…",
      "kb_name": "my_document",
      "timestamp": 1730000000,
      "status": "Pending",
      "status_text": "40% child chunks"
    }
  ]
}
```

`status` is `Pending`, `Completed` or `Failed`.

### `DELETE /delete_knowledge_base`

```json
{ "knowledge_base_name": "my_document" }
```

Deletes pickles, the PDF, Chroma collections and metadata. Returns `404` if
nothing was found.

---

## Chat history

### `POST /save_chat_history`

Drains the session cache into SQLite. For a new session the response contains
the new id; use `updateChatHistory_<id>` for subsequent turns.

```json
{ "chat_session_id": "8e1c…" }
```

```json
{ "success": true, "id": 12 }
```

### `GET /list_chat_history`

```json
{
  "result": [
    { "category": "Past 24 hours", "chats": [{ "id": 12, "title": "Access rules" }] },
    { "category": "Past week", "chats": [] },
    { "category": "Past month", "chats": [] }
  ]
}
```

### `POST /undo_chat`

Removes the latest assistant reply and its user query.

```json
{ "chat_session_id": "updateChatHistory_12" }
```

```json
{ "success": true, "remaining": 2 }
```

### `POST /get_chat_history_by_id`

```json
{ "id": 12 }
```

```json
{
  "id": 12,
  "content": [
    { "sender": "user", "kb": ["my_document"], "content": "How long…" },
    { "sender": "bot", "content": "Temporary access is granted for 30 days…", "context_used": 121, "context_window": 1048576 }
  ]
}
```

### `POST /rename_chat_history_by_id`

```json
{ "id": 12, "name": "Access rules" }
```

### `DELETE /delete_chat_history_by_id`

```json
{ "id": 12 }
```

---

## Errors

Errors use a JSON body and a conventional status code:

```json
{ "error": "Chat history not found" }
```

| Status | Meaning |
|---|---|
| `400` | Validation failure |
| `404` | Resource not found |
| `409` | Knowledge base already exists |
| `413` | Upload exceeds the configured limit |