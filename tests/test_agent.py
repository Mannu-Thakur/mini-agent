"""Smoke tests for the Mini Agent.

Run:  python -m pytest tests/test_agent.py -v
  or: python tests/test_agent.py            (standalone)
"""

import sys, os, tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.memory import ChatMemory
from src.registry import ToolRegistry, build_default_registry
from src.state import ConversationState
from src.agent import MiniAgent
from src.tools import calculate, get_weather
from src.storage import SessionStore
from src.retry import _is_retryable


# ── Unit: ChatMemory ────────────────────────────────────────────────────────

def test_memory_windowing():
    mem = ChatMemory(max_messages=4)
    for i in range(10):
        mem.add_user_message(f"msg-{i}")
    msgs = mem.get_messages()
    assert len(msgs) == 4, f"Expected 4, got {len(msgs)}"
    assert msgs[0].content == "msg-6"
    assert msgs[-1].content == "msg-9"
    print("  memory windowing")


def test_memory_returns_copy():
    mem = ChatMemory()
    mem.add_user_message("hello")
    msgs = mem.get_messages()
    msgs.clear()
    assert len(mem.get_messages()) == 1, "Internal list was mutated!"
    print("  memory returns copy")


def test_memory_clear():
    mem = ChatMemory()
    mem.add_user_message("hello")
    mem.clear()
    assert len(mem.get_messages()) == 0
    print("  memory clear")


# ── Unit: ToolRegistry ─────────────────────────────────────────────────────

def test_registry_basic():
    reg = ToolRegistry()
    reg.register("echo", "Echoes input", "text", lambda x: x)
    assert "echo" in reg
    assert len(reg) == 1
    assert reg.names() == ["echo"]
    assert reg.get("echo")["function"]("hi") == "hi"
    print("  registry basic ops")


def test_registry_unknown_tool():
    reg = ToolRegistry()
    assert reg.get("nonexistent") is None
    print("  registry unknown tool returns None")


def test_default_registry():
    reg = build_default_registry()
    assert "weather" in reg and "calculator" in reg and "search" in reg
    assert len(reg) == 3
    print("  default registry has all tools")


# ── Unit: ConversationState ─────────────────────────────────────────────────

def test_state_update():
    state = ConversationState()
    trace = [
        {"step": 1, "action": "weather:Delhi", "observation": "42C"},
        {"step": 2, "final_answer": "It's hot"},
    ]
    state.update_from_trace(trace)
    assert state.last_tool == "weather"
    assert state.entities.get("location") == "Delhi"
    assert "Delhi" in state.get_context_summary()
    print("  conversation state update")


def test_state_clear():
    state = ConversationState()
    state.update_from_trace([{"step": 1, "action": "search:AI", "observation": "..."}])
    state.clear()
    assert state.current_topic is None and len(state.entities) == 0
    print("  conversation state clear")


# ── Unit: Calculator tool ───────────────────────────────────────────────────

def test_calculator():
    assert "600" in calculate("20 * 30")
    assert "division by zero" in calculate("1 / 0").lower()
    assert "Error" in calculate("import os")
    print("  calculator tool")


# ── Unit: Agent._parse ─────────────────────────────────────────────────────

def test_parse_action():
    t, a, fa, c = MiniAgent._parse("THINK: Need weather\nACTION: weather:Delhi")
    assert t == "Need weather" and a == ("weather", "Delhi")
    assert fa is None and c is None
    print("  parse ACTION")


def test_parse_final_answer():
    t, a, fa, c = MiniAgent._parse("THINK: I know this\nFINAL_ANSWER: Python is a programming language.")
    assert t == "I know this" and fa == "Python is a programming language."
    assert a is None
    print("  parse FINAL_ANSWER")


def test_parse_clarify():
    _, _, _, c = MiniAgent._parse("THINK: Ambiguous\nCLARIFY: Do you want weather or news about London?")
    assert c is not None and "London" in c
    print("  parse CLARIFY")


def test_parse_graceful_degradation():
    _, a, fa, c = MiniAgent._parse("Hello! I'm an AI assistant.")
    assert a is None and fa is None and c is None
    print("  parse graceful degradation")


def test_parse_multiline_final_answer():
    _, _, fa, _ = MiniAgent._parse("THINK: Summarizing\nFINAL_ANSWER: Here are the results:\n1. First\n2. Second")
    assert fa is not None and "First" in fa and "Second" in fa
    print("  parse multiline FINAL_ANSWER")


# ── Integration: Agent._execute_tool ────────────────────────────────────────

def test_execute_unknown_tool():
    reg = build_default_registry()
    agent = MiniAgent(llm=None, registry=reg)
    result = agent._execute_tool("foobar", "test")
    assert "unknown tool" in result.lower()
    print("  execute unknown tool returns error string")


def test_execute_calculator():
    reg = build_default_registry()
    agent = MiniAgent(llm=None, registry=reg)
    result = agent._execute_tool("calculator", "2 + 2")
    assert "4" in result
    print("  execute calculator via agent")


# ── Unit: SessionStore (Phase 5) ───────────────────────────────────────────

def test_storage_crud():
    db_path = os.path.join(tempfile.gettempdir(), "mini_agent_test.db")
    # Clean up any previous run
    if os.path.exists(db_path):
        os.remove(db_path)
    try:
        s = SessionStore(db_path=db_path)
        s.create_session("s1", "Hello chat")
        assert s.session_exists("s1")
        assert not s.session_exists("s2")

        s.save_message("s1", "human", "Hi")
        s.save_message("s1", "ai", "Hello!")
        msgs = s.load_messages("s1")
        assert len(msgs) == 2
        assert msgs[0]["role"] == "human" and msgs[0]["content"] == "Hi"

        sessions = s.list_sessions()
        assert len(sessions) == 1 and sessions[0]["title"] == "Hello chat"

        s.rename_session("s1", "Renamed")
        assert s.list_sessions()[0]["title"] == "Renamed"

        s.delete_session("s1")
        assert not s.session_exists("s1")
        assert len(s.load_messages("s1")) == 0
    finally:
        try:
            os.remove(db_path)
        except OSError:
            pass
    print("  storage CRUD operations")


# ── Unit: Retry helpers (Phase 8) ──────────────────────────────────────────

def test_is_retryable():
    assert _is_retryable(Exception("rate limit exceeded"))
    assert _is_retryable(Exception("Error code: 429"))
    assert _is_retryable(Exception("Connection timeout"))
    assert not _is_retryable(ValueError("bad input"))
    print("  retry _is_retryable")


def test_retry_respects_input_errors():
    """retry_tool_call should NOT retry ValueError/TypeError."""
    from src.retry import retry_tool_call
    calls = []
    def bad_tool(x):
        calls.append(1)
        raise ValueError("bad input")
    try:
        retry_tool_call(bad_tool, "x", max_retries=3)
    except ValueError:
        pass
    assert len(calls) == 1, "Should not have retried a ValueError"
    print("  retry does not retry input errors")


# ── Run all ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for fn in tests:
        try:
            fn()
            passed += 1
        except Exception as e:
            print(f"  FAIL {fn.__name__}: {e}")
            failed += 1
    print(f"\n{'='*40}")
    print(f"  {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)
