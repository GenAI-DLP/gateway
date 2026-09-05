"""
OpenAI 스타일 messages([{role, content}]) <-> Gemini contents/system_instruction 변환.

gemini_client.py(직접 호출)와 proxied_client.py(dlp-proxy 경유) 양쪽이
동일한 변환 로직을 쓰도록 여기 하나로 모았다 — 중복 구현 방지.
"""

from __future__ import annotations

import json


def to_gemini_contents(messages: list[dict]) -> tuple[list[dict], str | None]:
    """system 메시지는 system_instruction으로 분리, assistant는 model로 매핑."""
    contents = []
    system_parts = []
    for m in messages:
        role = m.get("role")
        text = m.get("content", "")
        if role == "system":
            system_parts.append(text)
            continue
        contents.append(
            {
                "role": "model" if role == "assistant" else "user",
                "parts": [{"text": text}],
            }
        )
    system_instruction = "\n".join(system_parts) if system_parts else None
    return contents, system_instruction


def build_gemini_request_body(messages: list[dict]) -> bytes:
    """Gemini generateContent 엔드포인트가 그대로 받는 JSON 바이트."""
    contents, system_instruction = to_gemini_contents(messages)
    body: dict = {"contents": contents}
    if system_instruction:
        body["system_instruction"] = {"parts": [{"text": system_instruction}]}
    return json.dumps(body, ensure_ascii=False).encode("utf-8")


def extract_gemini_text(data: dict) -> str:
    """Gemini generateContent 응답 JSON에서 최종 텍스트만 뽑는다. 실패 시 빈 문자열."""
    try:
        candidate = data["candidates"][0]
        parts = candidate["content"]["parts"]
        return "".join(p.get("text", "") for p in parts)
    except (KeyError, IndexError, TypeError):
        return ""
