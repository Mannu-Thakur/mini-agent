import ast
import operator
import os
import re
from urllib.parse import quote

import requests


# ── Weather ──────────────────────────────────────────────────────────────────

def get_weather(city: str) -> str:
    city = city.strip()
    if not city:
        return "Error: city name is empty."

    url = f"https://wttr.in/{quote(city)}?format=j1"
    try:
        response = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        data = response.json()
        current = data["current_condition"][0]
        area = data.get("nearest_area", [{}])[0]

        area_name = area.get("areaName", [{}])[0].get("value", city)
        region = area.get("region", [{}])[0].get("value", "")
        country = area.get("country", [{}])[0].get("value", "")
        location = ", ".join([p for p in [area_name, region, country] if p])

        return (
            f"Location: {location}\n"
            f"Condition: {current.get('weatherDesc', [{}])[0].get('value', 'N/A')}\n"
            f"Temperature: {current.get('temp_C', 'N/A')}°C\n"
            f"Feels like: {current.get('FeelsLikeC', 'N/A')}°C\n"
            f"Humidity: {current.get('humidity', 'N/A')}%\n"
            f"Wind speed: {current.get('windspeedKmph', 'N/A')} km/h"
        )
    except requests.RequestException as exc:
        return f"Error fetching weather for '{city}': {exc}"
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        return f"Unexpected weather data format for '{city}': {exc}"


# ── Calculator ────────────────────────────────────────────────────────────────

_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_OPS:
        return _SAFE_OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_OPS:
        return _SAFE_OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError(f"Unsupported expression: {ast.dump(node)}")


def calculate(expression: str) -> str:
    expression = expression.strip()
    if not expression:
        return "Error: expression is empty."

    # Allow only digits, operators, spaces, dots, parentheses
    if not re.fullmatch(r"[\d\s\+\-\*\/\%\.\(\)\^]+", expression):
        return f"Error: unsafe expression '{expression}'"

    expression = expression.replace("^", "**")
    try:
        tree = ast.parse(expression, mode="eval")
        result = _safe_eval(tree.body)
        if isinstance(result, float) and result.is_integer():
            result = int(result)
        return f"{expression} = {result}"
    except ZeroDivisionError:
        return "Error: division by zero"
    except Exception as exc:
        return f"Error evaluating '{expression}': {exc}"


# ── Tavily Search ─────────────────────────────────────────────────────────────

TAVILY_ENDPOINT = "https://api.tavily.com/search"

NEWS_HINTS = (
    "latest", "news", "today", "current", "now", "recent", "launch",
    "launched", "announced", "announcement", "breaking", "event",
    "update", "updates", "released", "release"
)

FINANCE_HINTS = (
    "stock", "share", "shares", "market", "price", "crypto", "bitcoin",
    "nifty", "sensex", "earnings", "revenue", "profit", "ipo"
)


def _detect_topic(query: str) -> tuple[str, str, str | None]:
    q = query.lower()

    if any(word in q for word in FINANCE_HINTS):
        return "finance", "advanced", "week"

    if any(word in q for word in NEWS_HINTS):
        return "news", "advanced", "week"

    return "general", "basic", None


def _format_tavily_results(payload: dict) -> str:
    answer = (payload.get("answer") or "").strip()
    results = payload.get("results") or []

    parts = []

    if answer:
        parts.append(f"Answer: {answer}")

    if results:
        parts.append("Top results:")
        for idx, item in enumerate(results[:5], start=1):
            title = (item.get("title") or "Untitled").strip()
            url = (item.get("url") or "").strip()
            content = (item.get("content") or "").strip()
            score = item.get("score", None)

            if len(content) > 280:
                content = content[:277].rstrip() + "..."

            score_text = f" (score: {score:.2f})" if isinstance(score, (int, float)) else ""
            line = f"{idx}. {title}{score_text}\n   {url}"
            if content:
                line += f"\n   {content}"
            parts.append(line)

    if parts:
        return "\n\n".join(parts)

    return "No clear result found. Try rephrasing the query."


def search(query: str) -> str:
    query = query.strip()
    if not query:
        return "Error: search query is empty."

    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        return "Error: TAVILY_API_KEY is not set in your environment."

    topic, search_depth, time_range = _detect_topic(query)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    body = {
        "query": query,
        "topic": topic,
        "search_depth": search_depth,
        "max_results": 5,
        "include_answer": "basic",
        "include_raw_content": False,
        "include_images": False,
        "include_image_descriptions": False,
        "include_favicon": False,
        "include_usage": False,
        "safe_search": False,
    }

    if time_range:
        body["time_range"] = time_range

    try:
        response = requests.post(TAVILY_ENDPOINT, json=body, headers=headers, timeout=20)
        response.raise_for_status()
        data = response.json()
        return _format_tavily_results(data)

    except requests.HTTPError as exc:
        details = ""
        try:
            details = response.text  # type: ignore[name-defined]
        except Exception:
            pass
        return f"Error during Tavily search for '{query}': {exc}\n{details}".strip()

    except requests.RequestException as exc:
        return f"Error during Tavily search for '{query}': {exc}"
    except (ValueError, TypeError, KeyError) as exc:
        return f"Unexpected Tavily response for '{query}': {exc}"