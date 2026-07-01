from langchain_core.messages import HumanMessage, AIMessage, SystemMessage


class ChatMemory:
    """Sliding-window conversation memory.

    Stores the last *max_messages* messages and always returns a
    defensive copy so callers can never corrupt internal state.
    """

    def __init__(self, max_messages: int = 50):
        self._messages: list = []
        self.max_messages = max_messages

    # ── Mutators ────────────────────────────────────────────────────────────

    def add_user_message(self, message: str):
        self._messages.append(HumanMessage(content=message))
        self._trim()

    def add_ai_message(self, message: str):
        self._messages.append(AIMessage(content=message))
        self._trim()

    def add_system_message(self, message: str):
        self._messages.append(SystemMessage(content=message))
        self._trim()

    # ── Accessors ───────────────────────────────────────────────────────────

    def get_messages(self) -> list:
        """Return a *copy* of the message list (safe for callers to mutate)."""
        return list(self._messages)

    def clear(self):
        self._messages.clear()

    # ── Internal ────────────────────────────────────────────────────────────

    def _trim(self):
        """Keep only the most recent *max_messages* entries."""
        if len(self._messages) > self.max_messages:
            self._messages = self._messages[-self.max_messages:]
