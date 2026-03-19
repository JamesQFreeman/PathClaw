#!/opt/pathclaw-venv/bin/python
from __future__ import annotations

import json
import mimetypes
import os
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

DEFAULT_MODEL = "gemini-3-flash-preview"


def require_api_key() -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY is not set")
    return api_key


def resolve_mllm_model(explicit: str | None = None) -> str:
    return explicit or os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL


def image_part(path: str) -> types.Part:
    raw = Path(path).read_bytes()
    mime = mimetypes.guess_type(path)[0] or "image/png"
    return types.Part.from_bytes(data=raw, mime_type=mime)


def call_mllm(messages: list[dict[str, Any]], model: str, temperature: float = 0.2) -> str:
    api_key = require_api_key()
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents=messages_to_contents(messages),
            config=types.GenerateContentConfig(temperature=temperature),
        )
    except Exception as err:
        raise SystemExit(f"Gemini SDK error: {err}") from err

    if getattr(response, "text", None):
        return response.text

    parts: list[str] = []
    for part in getattr(response, "parts", []) or []:
        if getattr(part, "text", None):
            parts.append(part.text)
    if parts:
        return "\n".join(parts)
    raise SystemExit(f"Gemini response missing text content: {response}")


def messages_to_contents(messages: list[dict[str, Any]]) -> list[types.Content]:
    contents: list[types.Content] = []
    for message in messages:
        role = "model" if message.get("role") == "assistant" else "user"
        raw_content = message.get("content")
        parts: list[types.Part] = []
        if isinstance(raw_content, str):
            parts.append(types.Part.from_text(text=raw_content))
        elif isinstance(raw_content, list):
            for item in raw_content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text" and isinstance(item.get("text"), str):
                    parts.append(types.Part.from_text(text=item["text"]))
                elif item.get("type") == "image_path" and isinstance(item.get("path"), str):
                    parts.append(image_part(item["path"]))
        if parts:
            contents.append(types.Content(role=role, parts=parts))
    return contents


def parse_json_response(text: str) -> dict[str, Any]:
    candidate = text.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        candidate = "\n".join(lines).strip()
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise SystemExit(f"Expected JSON object from Gemini, got: {text[:800]}")
    return json.loads(candidate[start : end + 1])
