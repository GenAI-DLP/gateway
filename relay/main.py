"""
Gateway 릴레이 — Demo 1 (사내 Gateway 경로).

역할 (DLP_Server_아키텍처.md 최신 논의 반영):
  1. 사내 신원(X-Corp-User-Id, X-Corp-Role) 헤더 주입
  2. 대화를 gateway 포맷으로 빌드
  3. dlp-server에 Inspect(input) gRPC 호출 → 판정대로 실행
  4. (allow/transform 인 경우) LLM 호출 (OpenAI 또는 Gemini, LLM_PROVIDER로 선택) — 프로덕션에서 Go 프록시가 하는
     "판정대로 외부 LLM에 직접 중계" 역할을 Demo 1에서는 Relay가 맡는다
  5. 응답에 Inspect(output) gRPC 호출 → 판정대로 최종 응답 결정
  6. UI에 반환

판정 로직 자체(PII 탐지/정책/변환)는 전혀 갖고 있지 않다 — dlp-server의 몫이다.
"""

import uuid

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import grpc_client
from gateway_format import build_gateway_body, parse_gateway_body
from llm_client import LLMError, chat_completion

app = FastAPI(title="DLP Demo 1 — Gateway Relay")


class ChatRequest(BaseModel):
    session_id: str | None = None
    user_id: str
    role: str
    message: str
    history: list[dict] = []  # [{"role": "user"|"assistant", "content": "..."}]


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    blocked: bool
    input_action: str
    input_reason: dict
    output_action: str | None = None
    output_reason: dict | None = None


def _corp_headers(user_id: str, role: str) -> dict:
    """
    실제 환경에서는 사내 SSO 세션에서 추출해 주입한다 (문서 §2.3).
    이 데모에는 SSO가 없으므로 UI에서 받은 값을 그대로 헤더로 옮긴다 —
    "헤더 주입"이라는 Relay의 역할 자체는 동일하게 재현한다.
    """
    return {"X-Corp-User-Id": user_id, "X-Corp-Role": role}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())
    headers = _corp_headers(req.user_id, req.role)

    messages = req.history + [{"role": "user", "content": req.message}]
    input_body = build_gateway_body(messages)

    verdict_in = grpc_client.inspect(
        session_id=session_id,
        direction="input",
        method="POST",
        path="/chat/completions",
        headers=headers,
        body=input_body,
    )

    if verdict_in.action == "block":
        return ChatResponse(
            session_id=session_id,
            reply="이 요청은 정책에 따라 차단되었습니다.",
            blocked=True,
            input_action=verdict_in.action,
            input_reason=verdict_in.reason,
        )

    if verdict_in.action == "transform":
        outgoing_messages = parse_gateway_body(verdict_in.transformed_body)
    else:
        outgoing_messages = messages

    try:
        reply_text = await chat_completion(outgoing_messages)
    except LLMError as e:
        return JSONResponse(status_code=502, content={"detail": str(e)})

    output_body = build_gateway_body([{"role": "assistant", "content": reply_text}])
    verdict_out = grpc_client.inspect(
        session_id=session_id,
        direction="output",
        method="POST",
        path="/chat/completions",
        headers=headers,
        body=output_body,
    )

    if verdict_out.action == "block":
        return ChatResponse(
            session_id=session_id,
            reply="응답이 정책 위반으로 차단되었습니다.",
            blocked=True,
            input_action=verdict_in.action,
            input_reason=verdict_in.reason,
            output_action=verdict_out.action,
            output_reason=verdict_out.reason,
        )

    if verdict_out.action == "transform":
        final_messages = parse_gateway_body(verdict_out.transformed_body)
        final_reply = final_messages[-1]["content"] if final_messages else reply_text
    else:
        final_reply = reply_text

    return ChatResponse(
        session_id=session_id,
        reply=final_reply,
        blocked=False,
        input_action=verdict_in.action,
        input_reason=verdict_in.reason,
        output_action=verdict_out.action,
        output_reason=verdict_out.reason,
    )


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index():
    return FileResponse("static/index.html")
