import json
import time
from collections import OrderedDict
from dotenv import load_dotenv

load_dotenv()

from flask import (Flask, request, jsonify, send_from_directory,
                   Response, stream_with_context)

from src.llm import get_llm, get_fallback_llm
from src.memory import ChatMemory
from src.agent import MiniAgent
from src.registry import build_default_registry
from src.storage import SessionStore
from src import logger

app = Flask(__name__, static_folder="ui", static_url_path="")

llm = get_llm()
fallback_llm = get_fallback_llm()
registry = build_default_registry()
store = SessionStore()

MAX_SESSIONS_MEMORY = 100
MAX_MESSAGE_LENGTH = 2000

# In-memory LRU cache for active sessions
_cache: OrderedDict[str, dict] = OrderedDict()


def _get_session(session_id: str) -> dict:
    """Get or create a session (memory + agent), backed by SQLite."""
    if session_id in _cache:
        _cache.move_to_end(session_id)
        return _cache[session_id]

    while len(_cache) >= MAX_SESSIONS_MEMORY:
        _cache.popitem(last=False)

    memory = ChatMemory()
    # Rehydrate from DB if the session already exists
    if store.session_exists(session_id):
        for msg in store.load_messages(session_id):
            if msg["role"] == "human":
                memory.add_user_message(msg["content"])
            elif msg["role"] == "ai":
                memory.add_ai_message(msg["content"])

    agent = MiniAgent(llm, registry, fallback_llm=fallback_llm)
    _cache[session_id] = {"memory": memory, "agent": agent}
    return _cache[session_id]


# ── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("ui", "index.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    session_id = data.get("session_id", "default")
    user_input = data.get("message", "").strip()

    if not user_input:
        return jsonify({"error": "Empty message"}), 400
    if len(user_input) > MAX_MESSAGE_LENGTH:
        return jsonify({"error": f"Message too long (max {MAX_MESSAGE_LENGTH} chars)"}), 400

    if not store.session_exists(session_id):
        title = user_input[:36] + ("\u2026" if len(user_input) > 36 else "")
        store.create_session(session_id, title)

    session = _get_session(session_id)
    memory, agent = session["memory"], session["agent"]

    memory.add_user_message(user_input)
    store.save_message(session_id, "human", user_input)

    t0 = time.perf_counter()
    try:
        result = agent.run(user_input, memory)
    except Exception as exc:
        logger.log_error("agent_run", exc)
        return jsonify({"error": f"Agent error: {exc}"}), 500

    duration_ms = (time.perf_counter() - t0) * 1000
    memory.add_ai_message(result["text"])
    store.save_message(session_id, "ai", result["text"])
    logger.log_turn(session_id, user_input, result["text"],
                    result.get("trace", []), duration_ms)

    return jsonify({"text": result["text"], "trace": result.get("trace", [])})


@app.route("/api/chat/stream", methods=["POST"])
def chat_stream():
    """SSE endpoint — streams ReAct tokens/events in real-time."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    session_id = data.get("session_id", "default")
    user_input = data.get("message", "").strip()

    if not user_input:
        return jsonify({"error": "Empty message"}), 400
    if len(user_input) > MAX_MESSAGE_LENGTH:
        return jsonify({"error": f"Message too long (max {MAX_MESSAGE_LENGTH} chars)"}), 400

    if not store.session_exists(session_id):
        title = user_input[:36] + ("\u2026" if len(user_input) > 36 else "")
        store.create_session(session_id, title)

    session = _get_session(session_id)
    memory, agent = session["memory"], session["agent"]

    memory.add_user_message(user_input)
    store.save_message(session_id, "human", user_input)

    def generate():
        t0 = time.perf_counter()
        final_text = ""
        try:
            for event in agent.run_stream(user_input, memory):
                if event["type"] == "done":
                    final_text = event.get("text", "")
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as exc:
            logger.log_error("agent_stream", exc)
            yield f"data: {json.dumps({'type': 'error', 'content': str(exc)})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'trace': [], 'text': f'Error: {exc}'})}\n\n"
            final_text = f"Error: {exc}"

        if final_text:
            memory.add_ai_message(final_text)
            store.save_message(session_id, "ai", final_text)
            duration_ms = (time.perf_counter() - t0) * 1000
            logger.log_turn(session_id, user_input, final_text, [], duration_ms)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Session management API ─────────────────────────────────────────────────

@app.route("/api/sessions", methods=["GET"])
def list_sessions():
    return jsonify({"sessions": store.list_sessions()})


@app.route("/api/sessions/<session_id>/messages", methods=["GET"])
def get_session_messages(session_id):
    if not store.session_exists(session_id):
        return jsonify({"error": "Session not found"}), 404
    return jsonify({"messages": store.load_messages(session_id)})


@app.route("/api/sessions/<session_id>", methods=["DELETE"])
def delete_session(session_id):
    store.delete_session(session_id)
    _cache.pop(session_id, None)
    return jsonify({"status": "deleted"})


@app.route("/api/sessions/rename", methods=["POST"])
def rename_session():
    data = request.get_json(silent=True) or {}
    sid = data.get("session_id")
    title = data.get("title", "").strip()
    if not sid or not title:
        return jsonify({"error": "session_id and title required"}), 400
    store.rename_session(sid, title)
    return jsonify({"status": "renamed"})


@app.route("/api/reset", methods=["POST"])
def reset():
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id", "default")
    store.delete_session(session_id)
    _cache.pop(session_id, None)
    return jsonify({"status": "reset"})


if __name__ == "__main__":
    logger.log_info("server_start", port=5000)
    app.run(debug=True, port=5000)
