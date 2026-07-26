# backend/services/chatbot.py
# Step 3 — Engineering Chatbot (restricted to uploaded drawing JSON)
# Step 4 — Drawing Search (semantic keyword search within the JSON)

from __future__ import annotations
import json
from services.ai_service import call_ai

# ---------------------------------------------------------------------------
# Step 3 — Chatbot
# ---------------------------------------------------------------------------

def chat_with_drawing(
    question: str,
    eng_json: dict,
    history: list[dict] | None = None,
) -> str:
    """
    Answer a user question strictly using the structured engineering JSON.

    Args:
        question:  The user's question about the drawing.
        eng_json:  Structured engineering JSON from extract_engineering_json().
        history:   Prior conversation turns [{role, content}, ...].

    Returns:
        Answer string. If the question is unrelated to engineering, returns
        a polite refusal.
    """
    eng_str = json.dumps(eng_json, indent=2)

    system = f"""You are an expert Mechanical CAD Drawing Assistant.

You MUST ONLY answer questions about the engineering drawing provided below.

If the user asks anything unrelated to this drawing (weather, coding, general knowledge, etc.),
respond EXACTLY with:
"I can only answer questions about the uploaded engineering drawing. Please ask something related to this drawing."

Never use outside knowledge. Never make up values. If a field is not present in the drawing JSON,
say "Not present in the uploaded drawing."

=== DRAWING JSON (YOUR ONLY KNOWLEDGE SOURCE) ===
{eng_str}
=== END OF DRAWING JSON ==="""

    prompt = f"""User question: {question}

Answer based ONLY on the drawing JSON above:"""

    return call_ai(prompt, system_override=system, history=history)


# ---------------------------------------------------------------------------
# Step 4 — Drawing Search
# ---------------------------------------------------------------------------

def search_drawing(query: str, eng_json: dict) -> dict:
    """
    Perform semantic search within the engineering JSON.

    Strategy
    --------
    1. Local pass: scan all string values in the JSON for the query substring.
    2. GPT pass: ask GPT to find semantically related entries.

    Returns:
        {
            "query": str,
            "local_matches": [...],   # exact / substring matches
            "ai_matches": str         # GPT semantic match summary
        }
    """
    # ── Local substring search ────────────────────────────────────────────────
    local_matches = _local_search(eng_json, query.lower())

    # ── GPT semantic search ───────────────────────────────────────────────────
    eng_str = json.dumps(eng_json, indent=2)

    prompt = f"""Search the engineering drawing JSON below for anything related to: "{query}"

Return a bullet list of every matching value, field name, or entry you find.
Include ONLY information present in the JSON.
If nothing matches, say "No matching entries found for '{query}'."

Drawing JSON:
{eng_str}

Search results for "{query}":"""

    ai_result = call_ai(prompt)

    return {
        "query":         query,
        "local_matches": local_matches,
        "ai_summary":    ai_result,
    }


def _local_search(obj, query: str, path: str = "", results: list | None = None) -> list[dict]:
    """Recursively walk the engineering JSON and collect all substring matches."""
    if results is None:
        results = []

    if isinstance(obj, dict):
        for k, v in obj.items():
            _local_search(v, query, f"{path}.{k}" if path else k, results)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            _local_search(item, query, f"{path}[{i}]", results)
    elif isinstance(obj, str):
        if query in obj.lower():
            results.append({"field": path, "value": obj})

    return results
