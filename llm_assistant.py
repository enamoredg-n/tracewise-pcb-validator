"""
llm_assistant.py - optional LLM helper for PCB validation explanations.
"""

from __future__ import annotations

import json
import os
from urllib import error, parse, request


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


def get_openai_api_key() -> str:
    return (os.getenv("OPENAI_API_KEY") or "").strip()


def get_gemini_api_key() -> str:
    return (os.getenv("GEMINI_API_KEY") or "").strip()


def get_available_provider() -> str | None:
    if get_gemini_api_key():
        return "gemini"
    if get_openai_api_key():
        return "openai"
    return None


def ai_available() -> bool:
    return get_available_provider() is not None


def default_model_for_available_provider() -> str:
    provider = get_available_provider()
    if provider == "gemini":
        return "gemini-2.5-flash"
    return "gpt-5.4-mini"


def _build_prompt(
    candidate_name: str,
    summary: dict,
    failed_rows: list[dict],
    metrics: dict,
) -> str:
    payload = {
        "candidate_file": candidate_name,
        "summary": summary,
        "metrics": metrics,
        "failed_rows": failed_rows[:60],
    }
    payload_text = json.dumps(payload, indent=2)

    return (
        "You are a PCB design review copilot.\n"
        "Read the validation data and produce a concise engineer-facing response in markdown.\n"
        "Use exactly these sections with short bullet points:\n"
        "1. Overall Risk\n"
        "2. What Failed\n"
        "3. What To Fix First\n"
        "4. Suggested Fixes\n"
        "Rules:\n"
        "- Be concrete and practical.\n"
        "- Use the actual measured values when possible.\n"
        "- Prioritize safety/manufacturing issues before cosmetic ones.\n"
        "- Do not invent PCB facts that are not in the data.\n"
        "- If there are no failures, say the board passed and mention any residual warnings.\n\n"
        f"Validation data:\n{payload_text}"
    )


def generate_validation_guidance(
    *,
    candidate_name: str,
    summary: dict,
    failed_rows: list[dict],
    metrics: dict,
    model: str | None = None,
) -> str:
    provider = get_available_provider()
    if provider is None:
        raise RuntimeError("No AI API key found. Set GEMINI_API_KEY or OPENAI_API_KEY.")

    prompt = _build_prompt(candidate_name, summary, failed_rows, metrics)

    if provider == "gemini":
        return _generate_with_gemini(prompt, model or default_model_for_available_provider())

    return _generate_with_openai(prompt, model or default_model_for_available_provider())


def _generate_with_openai(prompt: str, model: str) -> str:
    api_key = get_openai_api_key()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    body = {
        "model": model,
        "input": prompt,
    }

    req = request.Request(
        OPENAI_RESPONSES_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=45) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API error: {exc.code} {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Could not reach OpenAI API: {exc.reason}") from exc

    output_text = payload.get("output_text")
    if output_text:
        return output_text.strip()

    try:
        return payload["output"][0]["content"][0]["text"].strip()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("OpenAI API returned an unexpected response shape.") from exc


def _generate_with_gemini(prompt: str, model: str) -> str:
    api_key = get_gemini_api_key()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set.")

    endpoint = f"{GEMINI_BASE_URL}/{parse.quote(model, safe='')}:" + "generateContent"
    body = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt,
                    }
                ]
            }
        ]
    }

    req = request.Request(
        endpoint,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=45) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini API error: {exc.code} {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Could not reach Gemini API: {exc.reason}") from exc

    try:
        return payload["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("Gemini API returned an unexpected response shape.") from exc
