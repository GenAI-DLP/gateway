"""
Gemini API (Google AI Studio 무료 티어) 호출.
openai_client.chat_completion과 동일한 시그니처를 유지해서 main.py가
provider에 상관없이 그대로 쓸 수 있게 했다.

무료 티어는 요청/일 한도가 낮으니 데모 용도로만 쓸 것.
"""

import httpx

from config import settings
from gemini_format import extract_gemini_text, to_gemini_contents

# 기존 테스트(tests/test_gemini_client.py)가 이 이름으로 직접 임포트하므로 별칭 유지.
_to_gemini_contents = to_gemini_contents


class GeminiError(RuntimeError):
    pass


async def chat_completion(messages: list[dict]) -> str:
    if not settings.gemini_api_key:
        raise GeminiError(
            "GEMINI_API_KEY가 설정되지 않았습니다. relay/.env에 값을 넣어주세요. "
            "https://aistudio.google.com/apikey 에서 무료로 발급받을 수 있습니다."
        )

    contents, system_instruction = to_gemini_contents(messages)
    body: dict = {"contents": contents}
    if system_instruction:
        body["system_instruction"] = {"parts": [{"text": system_instruction}]}

    url = f"{settings.gemini_base_url}/models/{settings.gemini_model}:generateContent"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                url,
                headers={
                    "x-goog-api-key": settings.gemini_api_key,
                    "Content-Type": "application/json",
                },
                json=body,
            )
    except httpx.TimeoutException as e:
        raise GeminiError(
            "Gemini API 응답이 30초 안에 오지 않았습니다. 사내 네트워크/방화벽이 "
            "generativelanguage.googleapis.com 접속을 막고 있는지 확인해주세요."
        ) from e
    except httpx.RequestError as e:
        raise GeminiError(f"Gemini API 연결 실패: {e}") from e

    if resp.status_code != 200:
        raise GeminiError(f"Gemini 호출 실패 ({resp.status_code}): {resp.text[:300]}")

    data = resp.json()
    text = extract_gemini_text(data)
    if not text:
        # 안전 필터에 걸려 candidates가 비었거나 finishReason만 오는 경우 등
        raise GeminiError(f"Gemini 응답 파싱 실패: {data}")
    return text
