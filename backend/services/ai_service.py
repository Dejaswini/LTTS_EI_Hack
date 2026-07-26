# backend/services/ai_service.py
# Azure FoundAI Responses API client for LTTS Hackathon endpoint.
#
# API format (Responses API — different from Chat Completions):
#   POST {LTTS_API_URL}
#   Headers: api-key / Ocp-Apim-Subscription-Key
#   Body:
#     {
#       "model": "gpt-5.3-codex",
#       "instructions": "<system prompt>",
#       "input": [ {"role":"user","content":"..."}, ... ]
#     }
#   Response:
#     { "output_text": "...", "output": [...] }
#
# Required in backend/.env:
#   LTTS_API_KEY   — subscription key from DevOps credentials
#   LTTS_API_URL   — https://apim-foundry-prod-ltts.azure-api.net/codex/responses
#   MODEL_NAME     — gpt-5.3-codex

from __future__ import annotations
import os
import requests
from dotenv import load_dotenv

# Load .env from backend directory
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

# ---------------------------------------------------------------------------
# System prompt — hard-locked to engineering drawing context
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are an expert Mechanical CAD Drawing Assistant.

Your ONLY responsibility is understanding and analyzing engineering drawings.

Use ONLY the OCR content or structured JSON supplied to you in this conversation.

Do NOT invent, assume, or hallucinate any missing values.

Do NOT answer questions unrelated to the uploaded drawing.

If information does not exist in the drawing, reply exactly:
"Not present in the uploaded drawing."

Always return structured, precise engineering information.

Never generate explanations or knowledge outside the supplied drawing content."""


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _get_config() -> tuple[str, str, str]:
    """Return (api_key, api_url, model_name) from environment."""
    api_key   = os.getenv("LTTS_API_KEY",  "")
    api_url   = os.getenv("LTTS_API_URL",  "")
    model     = os.getenv("MODEL_NAME",    "gpt-5.3-codex")
    return api_key, api_url, model


def get_deployment() -> str:
    """Return configured model name (used by status endpoint)."""
    return os.getenv("MODEL_NAME", "gpt-5.3-codex")


def is_configured() -> bool:
    """Return True if all required env vars are set with real values."""
    key, url, _ = _get_config()
    return (
        bool(key) and key != "your_actual_api_key_here"
        and bool(url) and "apim" in url
    )


# ---------------------------------------------------------------------------
# Core call function — Responses API format
# ---------------------------------------------------------------------------

def call_ai(
    user_message: str,
    system_override: str | None = None,
    history: list[dict] | None = None,
    json_mode: bool = False,
) -> str:
    """
    Send a message to the Azure FoundAI Responses API.

    Responses API body format:
        {
          "model": "gpt-5.3-codex",
          "instructions": "<system prompt>",
          "input": [
            {"role": "user",      "content": "..."},
            {"role": "assistant", "content": "..."},   <- history
            {"role": "user",      "content": "current message"}
          ]
        }

    Args:
        user_message:    The user turn content.
        system_override: Optional system prompt (defaults to SYSTEM_PROMPT).
        history:         Prior conversation turns [{role, content}, ...].
        json_mode:       If True, appends JSON-only instruction to system prompt.

    Returns:
        Response text string.

    Raises:
        EnvironmentError: API key / URL not configured.
        RuntimeError:     HTTP or parse error.
    """
    api_key, api_url, model = _get_config()

    # ── Validate config ───────────────────────────────────────────────────────
    if not api_key or api_key == "your_actual_api_key_here":
        raise EnvironmentError(
            "LTTS_API_KEY is not set. Open backend/.env and paste your API key."
        )
    if not api_url:
        raise EnvironmentError(
            "LTTS_API_URL is not set. Open backend/.env and set the Responses API URL."
        )

    # ── Build system instruction ──────────────────────────────────────────────
    system = system_override or SYSTEM_PROMPT
    if json_mode:
        system += (
            "\n\nCRITICAL: Return ONLY valid JSON. "
            "No markdown fences. No explanation text outside the JSON."
        )

    # ── Build input array (Responses API uses 'input', not 'messages') ────────
    input_turns: list[dict] = []
    if history:
        input_turns.extend(history)
    input_turns.append({"role": "user", "content": user_message})

    # ── Build request body ────────────────────────────────────────────────────
    body = {
        "model":        model,
        "instructions": system,   # system prompt goes here in Responses API
        "input":        input_turns,
    }

    headers = {
        "Content-Type":              "application/json",
        "api-key":                   api_key,
        "Ocp-Apim-Subscription-Key": api_key,
    }

    # ── Call the API ──────────────────────────────────────────────────────────
    try:
        resp = requests.post(api_url, headers=headers, json=body, timeout=120)
    except requests.exceptions.Timeout:
        raise RuntimeError("Request timed out after 120 s.")
    except requests.exceptions.ConnectionError as e:
        raise RuntimeError(f"Cannot reach API: {e}")

    if resp.status_code != 200:
        raise RuntimeError(
            f"API returned HTTP {resp.status_code}: {resp.text[:600]}"
        )

    # ── Parse response ────────────────────────────────────────────────────────
    # Responses API returns { "output_text": "...", "output": [...] }
    # Chat Completions returns { "choices": [{"message": {"content": "..."}}] }
    # We handle both formats as a safety fallback.
    try:
        data = resp.json()

        # Responses API — primary format
        if "output_text" in data:
            return data["output_text"].strip()

        # Responses API — nested format
        if "output" in data:
            for item in data["output"]:
                if isinstance(item, dict):
                    # item.content[0].text
                    content = item.get("content", [])
                    if isinstance(content, list) and content:
                        text = content[0].get("text", "")
                        if text:
                            return text.strip()
                    # item.text directly
                    if "text" in item:
                        return item["text"].strip()

        # Chat Completions fallback
        if "choices" in data:
            return data["choices"][0]["message"]["content"].strip()

        # Last resort — return raw JSON so we can debug
        raise ValueError(f"Unrecognised response format. Keys: {list(data.keys())}")

    except (KeyError, IndexError, ValueError) as e:
        raise RuntimeError(f"Failed to parse API response: {e}\nRaw: {resp.text[:400]}")
