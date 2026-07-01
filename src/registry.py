"""Tool registry — single source of truth for every tool the agent can use.

WHY:  The old code required editing agent.py (dispatch) AND prompts.py
      (tool names) every time a new tool was added.  Two modification
      points = Open/Closed Principle violation.

WHAT THIS SOLVES:
      Register a tool ONCE → the router prompt auto-generates, and the
      agent dispatches dynamically.  Zero changes to agent or prompt code.

HOW LANGCHAIN DOES IT:
      LangChain's BaseTool / @tool decorator stores name, description, and
      callable in one object.  We do the same with a plain dict + class.
"""

from __future__ import annotations

from src.tools import calculate, get_weather, search


class ToolRegistry:
    """Dynamic collection of tools with metadata."""

    def __init__(self):
        self._tools: dict[str, dict] = {}

    def register(
        self,
        name: str,
        description: str,
        input_hint: str,
        function: callable,
    ) -> "ToolRegistry":
        """Register a tool.  Returns *self* for chaining."""
        self._tools[name] = {
            "name": name,
            "description": description,
            "input": input_hint,
            "function": function,
        }
        return self

    # ── Lookup ──────────────────────────────────────────────────────────────

    def get(self, name: str) -> dict | None:
        return self._tools.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    # ── Metadata for prompt generation ──────────────────────────────────────

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def descriptions(self) -> list[dict]:
        """Return metadata dicts (name, description, input) for all tools."""
        return [
            {"name": t["name"], "description": t["description"], "input": t["input"]}
            for t in self._tools.values()
        ]


# ── Factory ─────────────────────────────────────────────────────────────────

def build_default_registry() -> ToolRegistry:
    """Create the standard tool set."""
    return (
        ToolRegistry()
        .register(
            name="weather",
            description="Get the current weather for a city or location.",
            input_hint="city name (e.g. Delhi, Mumbai, London)",
            function=get_weather,
        )
        .register(
            name="calculator",
            description="Evaluate a mathematical expression safely.",
            input_hint="math expression (e.g. 23 * 17, 100 / 4)",
            function=calculate,
        )
        .register(
            name="search",
            description="Search the web for factual information, people, definitions, or news.",
            input_hint="search query (e.g. Python programming language)",
            function=search,
        )
    )


# ── Backward-compatible module-level helpers ────────────────────────────────

_default: ToolRegistry | None = None


def _get_default() -> ToolRegistry:
    global _default
    if _default is None:
        _default = build_default_registry()
    return _default


def get_tool(name: str) -> dict | None:
    return _get_default().get(name)


def list_tools() -> list[dict]:
    return _get_default().descriptions()
