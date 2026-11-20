"""
src/llm.py
──────────
THE only LLM entry-point for the entire project.

    from src.llm import llm

    result = llm(prompt, schema)   # → dict

Providers
─────────
  gemini        – Google Gemini via google-generativeai SDK
  openai_compat – Any OpenAI-compatible endpoint (Groq, OpenRouter,
                  local vLLM, …) via the openai SDK

Configuration
─────────────
config.yaml → llm.provider, llm.model, llm.openai_compat.*

Disk cache
──────────
Every call is cached under  cache/<sha256(provider+model+prompt)>.json.
Identical calls are free after the first.

Rule enforced here
──────────────────
Prompts must NEVER ask the LLM to output timestamps.
Callers reference clips only by clip_id; real times are looked up in code.
"""

import hashlib
import json
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

_ROOT    = Path(__file__).parent.parent
_CFG     = yaml.safe_load((_ROOT / "config.yaml").read_text())
_CACHE   = _ROOT / "cache"
_CACHE.mkdir(exist_ok=True)

_PROVIDER = _CFG["llm"]["provider"]          # gemini | openai_compat
_MODEL    = _CFG["llm"]["model"]


def has_api_key() -> bool:
    """Check if an API key is set for the configured provider."""
    load_dotenv()
    cfg = _get_config()
    provider = cfg.get("llm", {}).get("provider", "openai_compat")
    if provider == "openai_compat":
        return bool(
            os.environ.get("OPENROUTER_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("NVIDIA_API_KEY")
        )
    elif provider == "gemini":
        return bool(os.environ.get("GEMINI_API_KEY"))
    return False


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _key(prompt: str) -> str:
    raw = f"{_PROVIDER}{_MODEL}{prompt}".encode()
    return hashlib.sha256(raw).hexdigest()

def _load(key: str):
    p = _CACHE / f"{key}.json"
    return json.loads(p.read_text()) if p.exists() else None

def _save(key: str, data: dict):
    (_CACHE / f"{key}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False))


# ── Gemini provider ───────────────────────────────────────────────────────────

def _call_gemini(prompt: str, schema: dict) -> dict:
    """
    Call Google Gemini using the new google-genai SDK.
    Reads GEMINI_API_KEY from environment.

    Uses generate_content with response_mime_type=application/json so the
    model returns structured JSON without the caller having to parse markdown.
    """
    from google import genai          # lazy import – new unified SDK
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    resp   = client.models.generate_content(
        model=_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
        ),
    )
    return json.loads(resp.text)


def _clean_json_str(raw: str) -> str:
    """Strip markdown code fence if the LLM wraps JSON inside ```json ... ```."""
    s = raw.strip()
    if s.startswith("```"):
        lines = s.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    return s


# ── OpenAI-compatible provider (OpenRouter, Groq, local, …) ──────────────────

def _call_openai_compat(prompt: str, schema: dict, temperature: float = 0.0) -> dict:
    """
    Call any OpenAI-compatible endpoint (OpenRouter, Groq, etc.) using the openai SDK.
    """
    from openai import OpenAI

    cfg = _get_config()
    oc = cfg["llm"].get("openai_compat", {})
    mdl = oc.get("model", cfg["llm"]["model"])

    api_key = (
        os.environ.get("OPENROUTER_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("NVIDIA_API_KEY")
    )
    if not api_key:
        raise ValueError(
            "Missing API key! Please set OPENROUTER_API_KEY or NVIDIA_API_KEY in your environment/secrets."
        )

    # Determine endpoint base_url
    if os.environ.get("OPENAI_BASE_URL"):
        url = os.environ.get("OPENAI_BASE_URL")
    elif os.environ.get("NVIDIA_API_KEY") and not os.environ.get("OPENROUTER_API_KEY"):
        url = "https://integrate.api.nvidia.com/v1"
    else:
        url = oc.get("base_url", "https://openrouter.ai/api/v1")

    client = OpenAI(
        base_url=url,
        api_key=api_key,
        default_headers={
            "HTTP-Referer": "https://github.com/kukufm-promo-finder",
            "X-Title": "Microdrama Promo Finder",
        },
    )

    enhanced_prompt = (
        f"{prompt}\n\n"
        f"IMPORTANT: Respond ONLY with a valid JSON object strictly matching this schema:\n"
        f"{json.dumps(schema, indent=2)}\n"
        f"Do not include any conversational text or markdown explanation outside the JSON."
    )

    try:
        resp = client.chat.completions.create(
            model=mdl,
            messages=[{"role": "user", "content": enhanced_prompt}],
            temperature=temperature,
            max_tokens=1500,
            response_format={"type": "json_object"},
        )
    except Exception:
        resp = client.chat.completions.create(
            model=mdl,
            messages=[{"role": "user", "content": enhanced_prompt}],
            temperature=temperature,
            max_tokens=1500,
        )

    content = resp.choices[0].message.content or "{}"
    cleaned = _clean_json_str(content)
    return json.loads(cleaned)


def _get_config():
    return yaml.safe_load((_ROOT / "config.yaml").read_text())


# ── Public API ────────────────────────────────────────────────────────────────

def llm(prompt: str, schema: dict, temperature: float = 0.0) -> dict:
    """
    Call the configured LLM and return a dict conforming to `schema`.
    Results are cached on disk; identical calls are free after the first.
    """
    cfg = _get_config()
    provider = cfg["llm"]["provider"]
    model = cfg["llm"].get("openai_compat", {}).get("model", cfg["llm"]["model"]) if provider == "openai_compat" else cfg["llm"]["model"]

    key_raw = f"{provider}{model}{temperature}{prompt}".encode()
    key = hashlib.sha256(key_raw).hexdigest()

    cached = _load(key)
    if cached is not None:
        print(f"  [llm] cache hit  ({key[:12]}…)")
        return cached

    print(f"  [llm] calling {provider}/{model}  ({key[:12]}…)")
    if provider == "gemini":
        result = _call_gemini(prompt, schema)
    elif provider == "openai_compat":
        result = _call_openai_compat(prompt, schema, temperature=temperature)
    else:
        raise ValueError(f"Unknown provider: {provider!r}. Use 'gemini' or 'openai_compat'.")

    _save(key, result)
    return result


# ── Smoke-test  (python -m src.llm) ──────────────────────────────────────────

if __name__ == "__main__":
    _schema = {
        "type": "object",
        "properties": {
            "answer": {"type": "string"},
            "confidence": {"type": "number"},
        },
        "required": ["answer", "confidence"],
        "additionalProperties": False,
    }
    _prompt = (
        "You are a helpful assistant.  "
        "Reply ONLY with a JSON object matching the schema you have been given.\n\n"
        "Question: What is 2 + 2?"
    )
    print("Running smoke-test LLM call …\n")
    out = llm(_prompt, _schema)
    print("Result:", json.dumps(out, indent=2))
