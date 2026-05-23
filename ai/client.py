import json
import logging
import os
import time
from typing import Any

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "llama-3.3-70b-versatile"
_TIMEOUT = 30
_MAX_RETRIES = 3


def _get_client():
    try:
        from groq import Groq
    except ImportError as e:
        raise RuntimeError("groq package not installed") from e
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY not set in environment")
    return Groq(api_key=api_key, timeout=_TIMEOUT)


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # drop opening fence line
        lines = lines[1:]
        # drop closing fence if present
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def complete_json(prompt: str, system: str, model: str | None = None) -> dict[str, Any]:
    """Call Groq and return parsed JSON. Retries on rate-limit / transient errors."""
    client = _get_client()
    model = model or os.environ.get("GROQ_MODEL", _DEFAULT_MODEL)

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]

    last_err: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.1,
            )
            raw = resp.choices[0].message.content or ""
            cleaned = _strip_fences(raw)
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                # One retry with an explicit JSON reminder appended
                if attempt < _MAX_RETRIES - 1:
                    messages = [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                        {"role": "assistant", "content": raw},
                        {"role": "user", "content": "Respond with raw JSON only. No markdown fences, no preamble."},
                    ]
                    continue
                logger.error("JSON parse failed after retries. Raw: %s", raw[:200])
                return {}
        except Exception as e:
            last_err = e
            # Check for rate-limit style errors
            err_str = str(e).lower()
            if any(k in err_str for k in ("rate", "429", "503", "502", "timeout")):
                wait = 2 ** attempt
                logger.warning("Groq transient error (attempt %d): %s — retrying in %ds", attempt + 1, e, wait)
                time.sleep(wait)
            else:
                logger.error("Groq non-retriable error: %s", e)
                return {}

    logger.error("Groq failed after %d attempts: %s", _MAX_RETRIES, last_err)
    return {}
