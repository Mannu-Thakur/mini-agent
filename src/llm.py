import os
from pathlib import Path

from dotenv import load_dotenv, find_dotenv
from langchain_groq import ChatGroq

# Try explicit path first, fall back to auto-discovery
_env = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_env if _env.exists() else find_dotenv())



def get_llm():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not found in .env")

    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    return ChatGroq(
    api_key=api_key,
    model=model,
    temperature=0.2,
    max_tokens=2048,
    stop=["OBSERVATION:"],
)


def get_fallback_llm():
    """Smaller/faster model used when the primary model fails."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None
    model = os.getenv("GROQ_FALLBACK_MODEL", "llama-3.1-8b-instant")
    return ChatGroq(
    api_key=api_key,
    model=model,
    temperature=0.2,
    max_tokens=2048,
    stop=["OBSERVATION:"],
)