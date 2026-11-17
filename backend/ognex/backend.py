"""Flask application factory and HTTP API.

Routes cover chat streaming, knowledge-base management and chat history.
"""

from __future__ import annotations

import glob
import logging
import os

from flask import Flask, Response, jsonify, request, stream_with_context
from werkzeug.exceptions import HTTPException

from ognex import runtime_settings
from ognex.cache.chat_history import (
    clear_history_cache,
    insert_history_into_cache,
    list_history_cache,
)
from ognex.cache.session_cache import get_and_clear_item_from_cache
from ognex.config import settings
from ognex.constants import (
    BE_ASSISTANT,
    BE_USER,
    FE_ASSISTANT,
    FE_USER,
    NO_RAG_KNOWLEDGE_BASE,
)
from ognex.database.chat_history import (
    delete_chat_history,
    get_chat_history,
    insert_chat_history,
    list_chat_history_within_last_month,
    rename_chat_history,
    replace_chat_history,
    update_chat_history,
)
from ognex.database.main import init_db
from ognex.database.tasks import list_tasks
from ognex.embeddings import get_embeddings
from ognex.exception import OgnexError
from ognex.helper import (
    load_from_pickle,
    log_query,
    sanitise_knowledge_base_name,
)
from ognex.langmodel.client import reset_chat_client
from ognex.langmodel.interface import initialise_streamer_from_config
from ognex.retriever.vectorstore import delete_knowledge_base_collections
from ognex.tasks.runner import submit_knowledge_base_task

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

METADATA_SUFFIX = "_metadata.pkl.gz"


def available_knowledge_bases() -> list[str]:
    if not settings.pickle_dir.exists():
        return []
    names = [
        filename[: -len(METADATA_SUFFIX)]
        for filename in os.listdir(settings.pickle_dir)
        if filename.endswith(METADATA_SUFFIX)
    ]
    return [NO_RAG_KNOWLEDGE_BASE] + sorted(names)


def _flatten_history(fe_chats: list[dict]) -> list[dict]:
    role_mapping = {FE_USER: BE_USER, FE_ASSISTANT: BE_ASSISTANT}
    history: list[dict] = []

    for chat in fe_chats:
        content = chat.get("content", "")
        if isinstance(content, list):
            content = "\n".join(
                part.get("text", "") for part in content if part.get("type") == "text"
            )
        elif not isinstance(content, str):
            content = str(content)

        role = role_mapping.get(chat.get("sender"))
        if role:
            history.append({"role": role, "content": content})
    return history


def _json_body() -> dict:
    return request.get_json(silent=True) or {}


def _trim_last_turn(messages: list[dict]) -> bool:
    removed = False
    if messages and messages[-1].get("sender") == FE_ASSISTANT:
        messages.pop()
        removed = True
    if messages and messages[-1].get("sender") == FE_USER:
        messages.pop()
        removed = True
    return removed


def create_app() -> Flask:
    settings.ensure_directories()
    init_db()
    try:
        runtime_settings.ensure_initialized()
    except Exception:
        logger.exception("Could not initialise runtime model settings")

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = settings.max_upload_mb * 1024 * 1024

    @app.errorhandler(OgnexError)
    def handle_ognex_error(error: OgnexError):
        return jsonify({"error": str(error)}), error.status_code

    @app.errorhandler(413)
    def handle_too_large(_error):
        return jsonify({"error": f"Upload exceeds {settings.max_upload_mb} MB"}), 413

    @app.errorhandler(Exception)
    def handle_unexpected(error: Exception):
        if isinstance(error, HTTPException):
            return jsonify({"error": error.description}), error.code or 500
        logger.exception("Unhandled error")
        return jsonify({"error": "Internal server error"}), 500

    # ------------------------------------------------------------- system
    @app.get("/health")
    def health():
        runtime = runtime_settings.load()
        return jsonify(
            {
                "status": "ok",
                "app": settings.app_name,
                "llm_model": runtime.model,
                "context_window": runtime.context_window,
                "knowledge_bases": len(available_knowledge_bases()) - 1,
            }
        )

    # ------------------------------------------------------- model settings
    @app.get("/settings")
    def get_settings():
        runtime = runtime_settings.load()
        payload = runtime_settings.public(runtime)
        payload["metadata"] = runtime_settings.load_metadata()
        return jsonify(payload)

    @app.put("/settings")
    def update_settings():
        body = _json_body()
        current = runtime_settings.load()
        base = str(body.get("api_base") or current.api_base).strip()
        api_key = body.get("api_key")
        if api_key in (None, ""):
            api_key = current.api_key
        model = str(body.get("model") or current.model).strip()
        if not model:
            return jsonify({"error": "A model is required"}), 400

        result = runtime_settings.fetch_models(base, api_key)
        if not result["ok"]:
            return jsonify({"error": result["error"] or "Endpoint unreachable"}), 400
        if model not in {item["id"] for item in result["models"]}:
            return jsonify({"error": f"Model not found on this endpoint: {model}"}), 400

        detected = runtime_settings.context_for(model, result["models"])
        requested = body.get("context_window")
        try:
            context_window = int(requested) if requested else (detected or current.context_window)
        except (TypeError, ValueError):
            return jsonify({"error": "context_window must be an integer"}), 400
        if context_window < 1024:
            return jsonify({"error": "context_window is too small"}), 400

        updated = runtime_settings.RuntimeSettings(
            api_base=result["api_base"],
            api_key=api_key or "",
            model=model,
            context_window=context_window,
        )
        runtime_settings.save(updated)
        reset_chat_client()
        return jsonify(runtime_settings.public(updated))

    @app.get("/models")
    def list_models():
        return jsonify(runtime_settings.fetch_models())

    @app.post("/models")
    def preview_models():
        body = _json_body()
        current = runtime_settings.load()
        base = str(body.get("api_base") or current.api_base).strip()
        api_key = body.get("api_key")
        if api_key in (None, ""):
            api_key = current.api_key if base.rstrip("/") == current.api_base.rstrip("/") else ""
        return jsonify(runtime_settings.fetch_models(base, api_key))

    # --------------------------------------------------------------- chat
    @app.route("/chat", methods=["POST", "OPTIONS"])
    def chat():
        body = _json_body()
        chat_session_id = body.get("chat_session_id") or ""
        kb_names = body.get("knowledge_base_names") or [NO_RAG_KNOWLEDGE_BASE]
        prompt = (body.get("last_chat_message") or "").strip()

        if not chat_session_id:
            return jsonify({"error": "chat_session_id is required"}), 400
        if not prompt:
            return jsonify({"error": "last_chat_message is required"}), 400

        if isinstance(kb_names, str):
            kb_names = [kb_names]
        valid = set(available_knowledge_bases())
        unknown = [name for name in kb_names if name not in valid]
        if unknown:
            return jsonify({"error": f"Unknown knowledge base(s): {unknown}"}), 400

        insert_history_into_cache(
            chat_session_id,
            {"sender": FE_USER, "kb": kb_names, "content": prompt},
        )
        fe_chats = list_history_cache(chat_session_id, False)

        if chat_session_id.startswith("updateChatHistory"):
            try:
                chat_id = int(chat_session_id.split("_", 1)[1])
            except (IndexError, ValueError):
                return jsonify({"error": "Malformed chat_session_id"}), 400
            record = get_chat_history(chat_id)
            if record is None:
                return jsonify({"error": "Chat history not found"}), 404
            fe_chats = record["content"] + fe_chats

        full_history = _flatten_history(fe_chats)
        log_query(kb_names, prompt)

        embedding = get_embeddings()
        streamer = initialise_streamer_from_config()

        def generate():
            try:
                yield from streamer.stream_response(
                    full_history,
                    prompt,
                    embedding,
                    kb_names,
                    chat_session_id,
                )
            except Exception:
                logger.exception("Chat stream failed")
                yield "\n\n⚠️ The response could not be completed. Please retry."

        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ---------------------------------------------------- knowledge bases
    @app.route("/list_knowledge_base_names", methods=["GET", "OPTIONS"])
    def list_knowledge_base_names():
        return jsonify({"knowledge_base_names": available_knowledge_bases()})

    @app.route("/list_knowledge_base_with_metadata", methods=["GET", "OPTIONS"])
    def list_knowledge_base_with_metadata():
        knowledge_bases = []
        for name in available_knowledge_bases():
            if name == NO_RAG_KNOWLEDGE_BASE:
                continue
            metadata = load_from_pickle(os.path.join(settings.pickle_dir, f"{name}{METADATA_SUFFIX}"))
            metadata["name"] = name
            knowledge_bases.append(metadata)
        return jsonify({"knowledge_bases": knowledge_bases})

    @app.route("/add_new_knowledge_base", methods=["POST", "OPTIONS"])
    def add_new_knowledge_base():
        if "file" not in request.files:
            return jsonify({"success": False, "message": "No file part"}), 400

        upload = request.files["file"]
        if not upload.filename:
            return jsonify({"success": False, "message": "No selected file"}), 400

        extension = os.path.splitext(upload.filename)[1].lower()
        if extension != ".pdf":
            return jsonify({"success": False, "message": "Only PDF files are allowed"}), 400

        try:
            knowledge_base_name = sanitise_knowledge_base_name(upload.filename)
        except ValueError as exc:
            return jsonify({"success": False, "message": str(exc)}), 400

        metadata_path = os.path.join(
            settings.pickle_dir, f"{knowledge_base_name}{METADATA_SUFFIX}"
        )
        if os.path.exists(metadata_path):
            return (
                jsonify({"success": False, "message": f"'{knowledge_base_name}' already exists"}),
                409,
            )

        # Clear artefacts from a previously failed ingestion of the same name
        # (metadata is only written when ingestion succeeds).
        for stale in glob.glob(
            os.path.join(str(settings.pickle_dir), f"{knowledge_base_name}*")
        ):
            os.remove(stale)

        filepath = os.path.join(settings.pdf_upload_dir, f"{knowledge_base_name}.pdf")
        upload.save(filepath)

        task_id = submit_knowledge_base_task(knowledge_base_name, filepath)
        return jsonify(
            {"success": True, "message": "Task created!", "task_id": task_id, "knowledge_base": knowledge_base_name}
        )

    @app.route("/list_knowledge_base_tasks", methods=["GET", "OPTIONS"])
    def list_knowledge_base_tasks():
        return jsonify({"tasks": list_tasks()})

    @app.route("/delete_knowledge_base", methods=["DELETE", "OPTIONS"])
    def delete_knowledge_base():
        raw_name = str(_json_body().get("knowledge_base_name") or "")
        try:
            knowledge_base_name = sanitise_knowledge_base_name(raw_name)
        except ValueError:
            return jsonify({"success": False, "message": "Invalid knowledge base name"}), 400

        removed_files = 0
        for filepath in glob.glob(
            os.path.join(str(settings.pickle_dir), f"{knowledge_base_name}*")
        ):
            os.remove(filepath)
            removed_files += 1

        pdf_path = os.path.join(settings.pdf_upload_dir, f"{knowledge_base_name}.pdf")
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
            removed_files += 1

        delete_knowledge_base_collections(knowledge_base_name)

        if removed_files == 0:
            return jsonify({"success": False, "message": "Knowledge base not found"}), 404
        return jsonify({"success": True})

    # -------------------------------------------------------- chat history
    @app.route("/undo_chat", methods=["POST", "OPTIONS"])
    def undo_chat():
        chat_session_id = _json_body().get("chat_session_id") or ""
        if not chat_session_id:
            return jsonify({"success": False, "message": "chat_session_id is required"}), 400

        if chat_session_id.startswith("updateChatHistory"):
            try:
                chat_id = int(chat_session_id.split("_", 1)[1])
            except (IndexError, ValueError):
                return jsonify({"success": False, "message": "Malformed chat_session_id"}), 400
            record = get_chat_history(chat_id)
            if record is None:
                return jsonify({"success": False, "message": "Chat history not found"}), 404
            messages = record["content"]
            removed = _trim_last_turn(messages)
            if removed:
                replace_chat_history(chat_id, messages)
            clear_history_cache(chat_session_id)
            return jsonify({"success": True, "remaining": len(messages)})

        messages = list_history_cache(chat_session_id, True)
        removed = _trim_last_turn(messages)
        for message in messages:
            insert_history_into_cache(chat_session_id, message)
        get_and_clear_item_from_cache(chat_session_id, "title")
        return jsonify({"success": True, "remaining": len(messages)})

    @app.route("/save_chat_history", methods=["POST", "OPTIONS"])
    def save_chat_history():
        chat_session_id = _json_body().get("chat_session_id") or ""
        if not chat_session_id:
            return jsonify({"success": False, "message": "chat_session_id is required"}), 400

        chat_messages = list_history_cache(chat_session_id, True)
        title = get_and_clear_item_from_cache(chat_session_id, "title")
        get_and_clear_item_from_cache(chat_session_id, "reference")

        if not chat_messages:
            return jsonify({"success": True, "empty": True})

        if chat_session_id.startswith("updateChatHistory"):
            try:
                chat_id = int(chat_session_id.split("_", 1)[1])
            except (IndexError, ValueError):
                return jsonify({"success": False, "message": "Malformed chat_session_id"}), 400
            updated = update_chat_history(chat_id, chat_messages, title)
            if not updated:
                return jsonify({"success": False, "message": "Chat history not found"}), 404
            return jsonify({"success": True, "id": chat_id})

        new_id = insert_chat_history(chat_messages, title)
        return jsonify({"success": True, "id": new_id})

    @app.route("/list_chat_history", methods=["GET", "OPTIONS"])
    def list_chat_history():
        return jsonify({"result": list_chat_history_within_last_month()})

    @app.route("/get_chat_history_by_id", methods=["POST", "OPTIONS"])
    def get_chat_history_by_id():
        chat_id = _json_body().get("id")
        record = get_chat_history(chat_id) if chat_id is not None else None
        if record is None:
            return jsonify({"error": "Chat history not found"}), 404
        return jsonify(record)

    @app.route("/delete_chat_history_by_id", methods=["DELETE", "OPTIONS"])
    def delete_chat_history_by_id():
        chat_id = _json_body().get("id")
        if chat_id is None or not delete_chat_history(chat_id):
            return jsonify({"success": False, "message": "Chat history not found"}), 404
        return jsonify({"success": True})

    @app.route("/rename_chat_history_by_id", methods=["POST", "OPTIONS"])
    def rename_chat_history_by_id():
        body = _json_body()
        chat_id, name = body.get("id"), (body.get("name") or "").strip()
        if chat_id is None or not name:
            return jsonify({"success": False, "message": "id and name are required"}), 400
        if not rename_chat_history(name[:120], chat_id):
            return jsonify({"success": False, "message": "Chat history not found"}), 404
        return jsonify({"success": True})

    return app


if __name__ == "__main__":
    create_app().run(host=settings.host, port=settings.port, debug=settings.debug, threaded=True)