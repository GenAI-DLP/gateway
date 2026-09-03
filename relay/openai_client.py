"""
OpenAI 호출. dlp-server의 input verdict를 반영한 messages를 그대로 전달할 뿐,
여기서 내용을 검사하거나 바꾸지 않는다.
"""
import httpx

from config import settings


class OpenAIError(RuntimeError):
    pass


async def chat_completion(messages: list[dict]) -> str:
    if not settings.openai_api_key:
        raise OpenAIError(
            "OPENAI_API_KEY가 설정되지 않았습니다. relay/.env에 값을 넣어주세요."
        )

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{settings.openai_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={"model": settings.openai_model, "messages": messages},
        )

    if resp.status_code != 200:
        raise OpenAIError(f"OpenAI 호출 실패 ({resp.status_code}): {resp.text[:300]}")

    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise OpenAIError(f"OpenAI 응답 파싱 실패: {e}") from e
