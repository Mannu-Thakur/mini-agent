"""Conversation state tracker.

WHY:  The ReAct loop receives conversation history, but the LLM can still
      lose track of entities over long conversations.  An explicit state
      summary (current topic, known entities, last tool) is injected into
      the system prompt so the LLM reliably resolves pronouns like "there",
      "it", and "that one".

WHAT PROBLEM IT SOLVES:
      "Weather in Delhi" → "How hot is it there?" — without state, the
      router/LLM forgets "there" = Delhi.

WHAT LIMITATION EXISTED:
      The old router received ONLY the raw query with zero context.

HOW LANGCHAIN SOLVES IT:
      LangChain offers ConversationSummaryMemory and ConversationEntityMemory.
      We build a lightweight version: a dict of extracted entities updated
      after every ReAct turn.
"""


class ConversationState:
    """Tracks current topic, named entities, and last tool usage."""

    def __init__(self):
        self.current_topic: str | None = None
        self.entities: dict[str, str] = {}
        self.last_tool: str | None = None
        self.last_tool_args: str | None = None

    # ── Update from a completed ReAct trace ─────────────────────────────────

    def update_from_trace(self, trace: list[dict]):
        """Extract entities and topic from the list of ReAct steps."""
        for step in trace:
            action = step.get("action")
            if not action or ":" not in action:
                continue

            tool_name, tool_arg = action.split(":", 1)
            self.last_tool = tool_name
            self.last_tool_args = tool_arg
            self.current_topic = tool_name

            # Domain-specific entity extraction
            if tool_name == "weather":
                self.entities["location"] = tool_arg
            elif tool_name == "search":
                self.entities["search_topic"] = tool_arg

    # ── Build a concise context summary for the system prompt ───────────────

    def get_context_summary(self) -> str:
        parts = []
        if self.current_topic:
            parts.append(f"Current topic: {self.current_topic}")
        if self.entities:
            items = ", ".join(f"{k}={v}" for k, v in self.entities.items())
            parts.append(f"Known entities: {items}")
        if self.last_tool:
            parts.append(f"Last tool used: {self.last_tool}({self.last_tool_args})")
        return "\n".join(parts)

    def clear(self):
        self.current_topic = None
        self.entities.clear()
        self.last_tool = None
        self.last_tool_args = None
