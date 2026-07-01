"""MiniAgent — ReAct agent with graph backend, streaming, logging, retry.

run()        → LangGraph (blocking, supports parallel tools)
run_stream() → manual loop (token-level SSE streaming)
"""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.prompts import build_react_prompt
from src.state import ConversationState
from src.executor import ToolExecutor
from src import logger
from src.retry import retry_llm_call, retry_llm_stream, retry_tool_call

if TYPE_CHECKING:
    from src.memory import ChatMemory
    from src.registry import ToolRegistry


class MiniAgent:
    """ReAct agent — graph backend for run(), manual loop for streaming."""

    def __init__(self, llm, registry: "ToolRegistry", *,
                 max_steps: int = 6, fallback_llm=None, use_graph: bool = True):
        self.llm = llm
        self.fallback_llm = fallback_llm
        self.registry = registry
        self.max_steps = max_steps
        self.state = ConversationState()
        self.executor = ToolExecutor(registry)
        self.use_graph = use_graph
        self._graph = None

    # ── Public API ─────────────────────────────────────────────────────────

    def run(self, query: str, memory: "ChatMemory") -> dict:
        if self.use_graph:
            return self._run_graph(query, memory)
        return self._run_manual(query, memory)

    # ── Graph-based run (Phase 10) ─────────────────────────────────────────

    def _run_graph(self, query: str, memory: "ChatMemory") -> dict:
        if self._graph is None:
            from src.graph_agent import build_agent_graph
            self._graph = build_agent_graph(
                self.llm, self.registry, self.state,
                max_steps=self.max_steps, fallback_llm=self.fallback_llm,
            )

        system_prompt = build_react_prompt(
            self.registry, self.state.get_context_summary()
        )
        messages = [SystemMessage(content=system_prompt)] + memory.get_messages()

        initial_state = {
            "messages": messages, "trace": [],
            "step_count": 0, "final_text": "", "status": "",
        }

        try:
            result = self._graph.invoke(initial_state)
        except Exception as exc:
            logger.log_error("graph_invoke", exc)
            return {"text": f"Agent error: {exc}", "trace": []}

        trace = result.get("trace", [])
        text = result.get("final_text", "")

        if not text:
            # Max steps exhausted
            last_obs = ""
            for step in reversed(trace):
                if step.get("observation"):
                    last_obs = step["observation"]
                    break
            text = ("I reached my reasoning step limit, but here's what "
                    "I found:\n\n" + last_obs) if last_obs else \
                   "I wasn't able to complete the task. Could you rephrase?"

        self.state.update_from_trace(trace)
        return {"text": text, "trace": trace}

    # ── Manual run (backward compat + fallback) ────────────────────────────

    def _run_manual(self, query: str, memory: "ChatMemory") -> dict:
        system_prompt = build_react_prompt(
            self.registry, self.state.get_context_summary()
        )
        messages: list = [SystemMessage(content=system_prompt)] + memory.get_messages()
        trace: list[dict] = []

        for step_num in range(1, self.max_steps + 1):
            t0 = time.perf_counter()
            try:
                response = self._invoke_with_fallback(messages)
                raw = response.content.strip()
            except Exception as exc:
                logger.log_error("llm_call", exc)
                trace.append({"step": step_num, "error": str(exc)})
                return {"text": f"LLM error: {exc}", "trace": trace}
            logger.log_llm_call(step_num, len(messages),
                                (time.perf_counter() - t0) * 1000)

            thought, action, final_answer, clarify = self._parse(raw)

            if final_answer is not None:
                trace.append({"step": step_num, "thought": thought,
                              "final_answer": "(see response)"})
                self.state.update_from_trace(trace)
                return {"text": final_answer, "trace": trace}

            if clarify is not None:
                trace.append({"step": step_num, "thought": thought,
                              "clarify": clarify})
                return {"text": clarify, "trace": trace}

            if action is not None:
                tool_name, tool_arg = action
                tool_output = self.executor.execute_single(tool_name, tool_arg)
                trace.append({
                    "step": step_num, "thought": thought,
                    "action": f"{tool_name}:{tool_arg}",
                    "observation": tool_output,
                })
                messages.append(AIMessage(content=raw))
                messages.append(
                    HumanMessage(content=f"OBSERVATION:\n{tool_output}")
                )
                continue

            trace.append({"step": step_num,
                          "thought": thought or "(unparsed)",
                          "final_answer": "(see response)"})
            self.state.update_from_trace(trace)
            return {"text": raw, "trace": trace}

        self.state.update_from_trace(trace)
        return self._compile_max_steps_result(trace)

    # ── Streaming (always manual loop for token-level SSE) ─────────────────

    def run_stream(self, query: str, memory: "ChatMemory"):
        system_prompt = build_react_prompt(
            self.registry, self.state.get_context_summary()
        )
        messages: list = [SystemMessage(content=system_prompt)] + memory.get_messages()
        trace: list[dict] = []

        for step_num in range(1, self.max_steps + 1):
            t0 = time.perf_counter()
            try:
                stream = self._stream_with_fallback(messages)
                raw = ""
                for chunk in stream:
                    token = chunk.content
                    if token:
                        raw += token
                        yield {"type": "token", "content": token, "step": step_num}
            except Exception as exc:
                logger.log_error("llm_stream", exc)
                trace.append({"step": step_num, "error": str(exc)})
                yield {"type": "error", "content": str(exc)}
                yield {"type": "done", "trace": trace, "text": f"LLM error: {exc}"}
                return

            raw = raw.strip()
            logger.log_llm_call(step_num, len(messages),
                                (time.perf_counter() - t0) * 1000)

            thought, action, final_answer, clarify = self._parse(raw)

            if final_answer is not None:
                trace.append({"step": step_num, "thought": thought,
                              "final_answer": "(see response)"})
                self.state.update_from_trace(trace)
                yield {"type": "done", "trace": trace, "text": final_answer}
                return

            if clarify is not None:
                trace.append({"step": step_num, "thought": thought,
                              "clarify": clarify})
                yield {"type": "done", "trace": trace, "text": clarify}
                return

            if action is not None:
                tool_name, tool_arg = action
                yield {"type": "action", "tool": tool_name,
                       "input": tool_arg, "step": step_num}
                tool_output = self.executor.execute_single(tool_name, tool_arg)
                trace.append({
                    "step": step_num, "thought": thought,
                    "action": f"{tool_name}:{tool_arg}",
                    "observation": tool_output,
                })
                yield {"type": "observation", "content": tool_output,
                       "step": step_num}
                messages.append(AIMessage(content=raw))
                messages.append(
                    HumanMessage(content=f"OBSERVATION:\n{tool_output}")
                )
                continue

            trace.append({"step": step_num,
                          "thought": thought or "(unparsed)",
                          "final_answer": "(see response)"})
            self.state.update_from_trace(trace)
            yield {"type": "done", "trace": trace, "text": raw}
            return

        self.state.update_from_trace(trace)
        result = self._compile_max_steps_result(trace)
        yield {"type": "done", "trace": trace, "text": result["text"]}

    # ── LLM with fallback ──────────────────────────────────────────────────

    def _invoke_with_fallback(self, messages):
        try:
            return retry_llm_call(self.llm, messages)
        except Exception as exc:
            if self.fallback_llm:
                logger.log_info("fallback_activated", primary_error=str(exc))
                return retry_llm_call(self.fallback_llm, messages, max_retries=1)
            raise

    def _stream_with_fallback(self, messages):
        try:
            return retry_llm_stream(self.llm, messages)
        except Exception as exc:
            if self.fallback_llm:
                logger.log_info("fallback_stream", primary_error=str(exc))
                return retry_llm_stream(self.fallback_llm, messages, max_retries=1)
            raise

    # ── Parsing ────────────────────────────────────────────────────────────

    @staticmethod
    def _parse(text: str):
        thought = None
        m = re.search(
            r"THINK:\s*(.+?)(?=\n\s*(?:ACTION|FINAL_ANSWER|CLARIFY):|\Z)",
            text, re.DOTALL,
        )
        if m:
            thought = m.group(1).strip()

        action_m = re.search(r"ACTION:\s*(\w+)\s*:\s*(.+)", text)
        if action_m:
            return (thought,
                    (action_m.group(1).strip().lower(), action_m.group(2).strip()),
                    None, None)

        clarify_m = re.search(r"CLARIFY:\s*([\s\S]+)", text)
        if clarify_m:
            return thought, None, None, clarify_m.group(1).strip()

        fa_m = re.search(r"FINAL_ANSWER:\s*([\s\S]+)", text)
        if fa_m:
            return thought, None, fa_m.group(1).strip(), None

        return thought, None, None, None

    @staticmethod
    def _compile_max_steps_result(trace):
        last_obs = ""
        for step in reversed(trace):
            if step.get("observation"):
                last_obs = step["observation"]
                break
        text = ("I reached my reasoning step limit, but here's what "
                "I found:\n\n" + last_obs) if last_obs else \
               "I wasn't able to complete the task. Could you rephrase?"
        return {"text": text, "trace": trace}
