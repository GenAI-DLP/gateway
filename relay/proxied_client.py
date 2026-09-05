"""
TRANSPORT_MODE=dlp_proxy 경로.

Relay는 여기서 dlp-server를 전혀 직접 호출하지 않는다. dlp-proxy가
Inspect(input) -> 실제 Gemini 호출 -> Inspect(output) 을 전부 처리한 뒤
최종 HTTP 응답만 돌려준다 — Relay는 그 결과를 그대로 UI에 보여줄 뿐이다.

dlp-proxy는 상세 판정 근거(reason)를 클라이언트에 안 돌려주고 자기 로그로만
남긴다(감사 목적 — 탐지 세부사항을 호출자에게 노출하지 않기 위함). 다만
"허용/변환/차단" 액션 자체는 X-Dlp-Input-Action / X-Dlp-Output-Action 커스텀
응답 헤더로 최소한만 흘려줘서, UI가 direct 모드와 동일한 배지를 보여줄 수
있게 한다 (상세 "판정 근거 보기"는 reason이 없으니 dlp_proxy 모드에서는
자연히 안 뜬다).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from config import settings
from dlp_proxy_transport import DlpProxyTransportError, request_via_dlp_proxy
from gemini_format import build_gemini_request_body, extract_gemini_text


@dataclass
class ProxiedChatResult:
    reply: str
    input_action: str | None = None
    output_action: str | None = None


class ProxiedChatError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        blocked: bool = False,
        input_action: str | None = None,
        output_action: str | None = None,
    ):
        super().__init__(message)
        self.blocked = blocked
        self.input_action = input_action
        self.output_action = output_action


async def chat_via_dlp_proxy(messages: list[dict], headers: dict[str, str]) -> ProxiedChatResult:
    if not settings.gemini_api_key:
        raise ProxiedChatError("GEMINI_API_KEY가 설정되지 않았습니다.")
    if not settings.dlp_proxy_ca_cert:
        raise ProxiedChatError(
            "DLP_PROXY_CA_CERT가 설정되지 않았습니다 (dlp-proxy-server의 certs/ca.pem 절대경로)."
        )

    body = build_gemini_request_body(messages)
    path = f"/v1beta/models/{settings.gemini_model}:generateContent?key={settings.gemini_api_key}"
    request_headers = {**headers, "Content-Type": "application/json"}

    try:
        resp = await request_via_dlp_proxy(
            method="POST",
            real_host=settings.gemini_upstream_host,
            path=path,
            headers=request_headers,
            body=body,
            proxy_host=settings.dlp_proxy_host,
            proxy_port=settings.dlp_proxy_port,
            ca_cert_path=settings.dlp_proxy_ca_cert,
        )
    except DlpProxyTransportError as e:
        raise ProxiedChatError(f"dlp-proxy 연결 실패: {e}") from e

    # dlp-proxy가 붙여주는 최소 시그널. 없으면(구버전 dlp-proxy 등) None으로 두고
    # UI는 "dlp-proxy 경유" 일반 표시로 자연히 폴백한다 (index.html 참고).
    input_action = resp.headers.get("x-dlp-input-action")
    output_action = resp.headers.get("x-dlp-output-action")

    if resp.status == 403:
        # dlp-proxy의 writeBlocked()가 "blocked by DLP policy: <reason>" 평문을 준다.
        reason = resp.body.decode("utf-8", errors="replace")
        raise ProxiedChatError(
            reason, blocked=True, input_action=input_action, output_action=output_action
        )

    if resp.status != 200:
        raise ProxiedChatError(
            f"업스트림 오류 ({resp.status}): {resp.body.decode('utf-8', errors='replace')[:300]}",
            input_action=input_action,
            output_action=output_action,
        )

    try:
        data = json.loads(resp.body)
    except json.JSONDecodeError as e:
        raise ProxiedChatError(f"응답 JSON 파싱 실패: {e}") from e

    text = extract_gemini_text(data)
    if not text:
        raise ProxiedChatError(
            f"응답에서 텍스트를 못 찾음: {data}",
            input_action=input_action,
            output_action=output_action,
        )

    return ProxiedChatResult(reply=text, input_action=input_action, output_action=output_action)
