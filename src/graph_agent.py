"""LangGraph-based ReAct agent.

Replaces the hand-built while-loop with a StateGraph:
    think → (action | final_answer | clarify | unparsable)
    action → execute → think  (loop)
"""

from __future__ import annotations
import re, time
from typing import TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END

from src.prompts import build_react_prompt
from src.executor import ToolExecutor
from src.retry import retry_llm_call
from src import logger


class AgentState(TypedDict):
    messages: list
    trace: list
    step_count: int
    final_text: str
    status: str        # "action" | "done"


def build_agent_graph(llm, registry, state_mgr, *,
                      max_steps=6, fallback_llm=None):
    executor = ToolExecutor(registry)

    def _invoke(messages):
        try:
            return retry_llm_call(llm, messages)
        except Exception as exc:
            if fallback_llm:
                logger.log_info("graph_fallback", error=str(exc))
                return retry_llm_call(fallback_llm, messages, max_retries=1)
            raise

    def _parse(text):
        thought = None
        m = re.search(r"THINK:\s*(.+?)(?=\n\s*(?:ACTION|FINAL_ANSWER|CLARIFY):|\Z)", text, re.DOTALL)
        if m:
            thought = m.group(1).strip()
        actions = [
    (a.group(1).strip().lower(), a.group(2).strip())
    for a in re.finditer(
        r"ACTION:\s*(\w+)\s*:\s*(.+?)(?=\n(?:ACTION|FINAL_ANSWER|CLARIFY):|\Z)",
        text,
        re.DOTALL,
    )
]
        if actions:
            return thought, actions, None, None
        cm = re.search(r"CLARIFY:\s*([\s\S]+)", text)
        if cm:
            return thought, None, None, cm.group(1).strip()
        fm = re.search(r"FINAL_ANSWER:\s*([\s\S]+)", text)
        if fm:
            return thought, None, fm.group(1).strip(), None
        return thought, None, None, None

    # ── Nodes ──────────────────────────────────────────────────────────────

    def think_node(state: AgentState) -> dict:
        step = state["step_count"] + 1
        t0 = time.perf_counter()
        try:
            resp = _invoke(state["messages"])
            raw = resp.content.strip()
        except Exception as exc:
            logger.log_error("graph_llm", exc)
            return {
                "trace": state["trace"] + [{"step": step, "error": str(exc)}],
                "final_text": f"LLM error: {exc}",
                "status": "done", "step_count": step,
            }
        logger.log_llm_call(step, len(state["messages"]),
                            (time.perf_counter() - t0) * 1000)

        thought, actions, fa, clarify = _parse(raw)

        if fa is not None:
            return {
                "trace": state["trace"] + [{"step": step, "thought": thought, "final_answer": "(see response)"}],
                "final_text": fa, "status": "done", "step_count": step,
            }
        if clarify is not None:
            return {
                "trace": state["trace"] + [{"step": step, "thought": thought, "clarify": clarify}],
                "final_text": clarify, "status": "done", "step_count": step,
            }
        if actions:
            results = executor.execute_batch(actions)
            new_trace = list(state["trace"])
            obs_parts = []
            for (tname, targ), result in zip(actions, results):
                new_trace.append({
                    "step": step, "thought": thought,
                    "action": f"{tname}:{targ}", "observation": result,
                })
                obs_parts.append(f"[{tname}] {result}")
            combined_obs = "\n\n".join(obs_parts)
            new_msgs = list(state["messages"]) + [
                AIMessage(content=raw),
                HumanMessage(content=f"OBSERVATION:\n{combined_obs}"),
            ]
            return {
                "messages": new_msgs, "trace": new_trace,
                "status": "action", "step_count": step,
            }
        # Unparsable
        return {
            "trace": state["trace"] + [{"step": step, "thought": thought or "(unparsed)", "final_answer": "(see response)"}],
            "final_text": raw, "status": "done", "step_count": step,
        }

    # ── Routing ────────────────────────────────────────────────────────────

    def should_continue(state: AgentState) -> str:
        if state["status"] == "done":
            return "end"
        if state["step_count"] >= max_steps:
            return "end"
        return "continue"

    # ── Build graph ────────────────────────────────────────────────────────

    graph = StateGraph(AgentState)
    graph.add_node("think", think_node)
    graph.set_entry_point("think")
    graph.add_conditional_edges("think", should_continue, {
        "continue": "think",
        "end": END,
    })

    return graph.compile()
