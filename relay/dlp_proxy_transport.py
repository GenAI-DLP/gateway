"""
dlp-proxy를 거쳐 진짜 업스트림(Gemini 등)으로 나가는 저수준 HTTP 클라이언트.

httpx의 proxy= 옵션은 표준 HTTP CONNECT 터널링을 가정하는데, dlp-proxy는
SNI를 직접 훔쳐보는 투명 MITM 프록시라 CONNECT 핸드셰이크를 구현하지 않는다
(curl에서 --connect-to로 우회했던 것과 동일한 이유). asyncio.open_connection의
host/server_hostname을 분리 지정하는 기능으로 같은 효과를 낸다:
  - TCP 연결은 dlp-proxy 주소로
  - TLS SNI/인증서 검증은 진짜 목적지 호스트명으로

dlp-proxy가 판정(allow/block/transform)까지 전부 처리한 뒤 돌려주는 최종
HTTP 응답을 그대로 반환한다 — 이 함수 자체는 DLP 판정에 대해 아무것도 모른다.
"""

from __future__ import annotations

import asyncio
import ssl
from dataclasses import dataclass


class DlpProxyTransportError(RuntimeError):
    pass


@dataclass
class ProxyResponse:
    status: int
    headers: dict[str, str]
    body: bytes


def _parse_http_response(raw: bytes) -> ProxyResponse:
    if b"\r\n\r\n" not in raw:
        raise DlpProxyTransportError(f"HTTP 응답 헤더 구분자를 못 찾음 (받은 바이트 {len(raw)})")

    header_blob, _, body = raw.partition(b"\r\n\r\n")
    lines = header_blob.split(b"\r\n")

    try:
        status = int(lines[0].decode("utf-8", errors="replace").split(" ")[1])
    except (IndexError, ValueError) as e:
        raise DlpProxyTransportError(f"상태줄 파싱 실패: {lines[0]!r}") from e

    headers: dict[str, str] = {}
    for line in lines[1:]:
        if b":" in line:
            k, v = line.split(b":", 1)
            headers[k.decode().strip().lower()] = v.decode().strip()

    return ProxyResponse(status=status, headers=headers, body=body)


async def request_via_dlp_proxy(
    *,
    method: str,
    real_host: str,
    path: str,
    headers: dict[str, str],
    body: bytes,
    proxy_host: str,
    proxy_port: int,
    ca_cert_path: str,
    timeout: float = 30.0,
) -> ProxyResponse:
    """dlp-proxy(proxy_host:proxy_port)로 TCP 연결하되, TLS SNI/Host는 real_host로 보낸다."""
    try:
        ssl_context = ssl.create_default_context(cafile=ca_cert_path)
    except (OSError, ssl.SSLError) as e:
        raise DlpProxyTransportError(f"CA 인증서 로드 실패({ca_cert_path}): {e}") from e

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(
                proxy_host, proxy_port, ssl=ssl_context, server_hostname=real_host
            ),
            timeout=timeout,
        )
    except (TimeoutError, OSError, ssl.SSLError) as e:
        raise DlpProxyTransportError(
            f"dlp-proxy({proxy_host}:{proxy_port}) 연결 실패 (SNI={real_host}): {e}"
        ) from e

    try:
        request_headers = {
            **headers,
            "Host": real_host,
            "Content-Length": str(len(body)),
            "Connection": "close",
        }
        header_lines = [f"{method} {path} HTTP/1.1"]
        header_lines += [f"{k}: {v}" for k, v in request_headers.items()]
        request = ("\r\n".join(header_lines) + "\r\n\r\n").encode("utf-8") + body

        writer.write(request)
        await writer.drain()

        chunks: list[bytes] = []
        try:
            while True:
                chunk = await asyncio.wait_for(reader.read(65536), timeout=timeout)
                if not chunk:
                    break
                chunks.append(chunk)
        except TimeoutError as e:
            raise DlpProxyTransportError(f"dlp-proxy 응답 읽기 타임아웃({timeout}s)") from e
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:  # noqa: BLE001 - 연결 정리 실패는 응답 자체엔 영향 없음
            pass

    raw = b"".join(chunks)
    if not raw:
        raise DlpProxyTransportError("dlp-proxy로부터 빈 응답")

    return _parse_http_response(raw)
