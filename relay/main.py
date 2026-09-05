"""
Gateway 릴레이 — Demo 1 (사내 Gateway 경로).

두 가지 전송 모드를 지원한다 (.env의 TRANSPORT_MODE):

  "direct" (기존 방식) — Relay가 dlp-server와 LLM을 직접 호출:
    1. 사내 신원(X-Corp-User-Id, X-Corp-User-Role) 헤더 주입
    2. gateway 포맷으로 dlp-server에 Inspect(input) gRPC 호출 → 판정대로 실행
    3. (allow/transform) LLM 직접 호출
    4. 응답에 Inspect(output) gRPC 호출 → 판정대로 최종 응답 결정

  "dlp_proxy" (신규) — Relay는 헤더 주입 + 트래픽 발생만, 판정·중계는 dlp-proxy가 전부:
    1. 헤더 주입 + Gemini 네이티브 포맷으로 요청 조립
    2. TCP는 dlp-proxy로, TLS SNI는 진짜 Gemini 호스트로 보내는 커스텀 전송
       (dlp_proxy_transport.py) — curl --connect-to와 동일한 원리
    3. dlp-proxy가 Inspect(input) → 실제 Gemini 호출 → Inspect(output)을 전부 처리
    4. 최종 HTTP 응답만 그대로 받아 UI에 전달

  두 모드 다 판정 로직 자체(PII 탐지/정책/변환)는 전혀 갖고 있지 않다 — dlp-server의 몫이다.
  dlp_proxy 모드는 판정 근거(reason)가 dlp-proxy 내부 로그로만 남고 Relay에는
  안 돌아오므로, direct 모드에 있던 입력/응답별 action·reason 배지는 만들지 않는다.
"""

import uuid

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import grpc_client
from config import settings
from gateway_format import build_gateway_body, parse_gateway_body
from llm_client import LLMError, chat_completion
from proxied_client import ProxiedChatError, chat_via_dlp_proxy

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
    transport_mode: str
    # direct 모드에서만 채워짐 — dlp_proxy 모드는 판정 근거를 Relay가 못 받음
    input_action: str | None = None
    input_reason: dict | None = None
    output_action: str | None = None
    output_reason: dict | None = None


def _corp_headers(user_id: str, role: str) -> dict:
    """
    실제 환경에서는 사내 SSO 세션에서 추출해 주입한다 (문서 §2.3).
    이 데모에는 SSO가 없으므로 UI에서 받은 값을 그대로 헤더로 옮긴다 —
    "헤더 주입"이라는 Relay의 역할 자체는 두 모드 모두 동일하게 재현한다.
    """
    return {"X-Corp-User-Id": user_id, "X-Corp-User-Role": role}


@app.get("/health")
def health():
    return {"status": "ok", "transport_mode": settings.transport_mode}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())
    headers = _corp_headers(req.user_id, req.role)
    messages = req.history + [{"role": "user", "content": req.message}]

    if settings.transport_mode == "dlp_proxy":
        return await _chat_via_dlp_proxy(session_id, headers, messages)
    return await _chat_direct(session_id, headers, messages)


async def _chat_via_dlp_proxy(session_id: str, headers: dict, messages: list[dict]) -> ChatResponse:
    try:
        result = await chat_via_dlp_proxy(messages, headers)
    except ProxiedChatError as e:
        if e.blocked:
            return ChatResponse(
                session_id=session_id,
                reply=str(e),
                blocked=True,
                transport_mode="dlp_proxy",
                input_action=e.input_action,
                output_action=e.output_action,
            )
        return JSONResponse(status_code=502, content={"detail": str(e)})

    return ChatResponse(
        session_id=session_id,
        reply=result.reply,
        blocked=False,
        transport_mode="dlp_proxy",
        input_action=result.input_action,
        output_action=result.output_action,
    )


async def _chat_direct(session_id: str, headers: dict, messages: list[dict]) -> ChatResponse:
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
            transport_mode="direct",
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
            transport_mode="direct",
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
        transport_mode="direct",
        input_action=verdict_in.action,
        input_reason=verdict_in.reason,
        output_action=verdict_out.action,
        output_reason=verdict_out.reason,
    )


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index():
    return FileResponse("static/index.html")
