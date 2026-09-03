"""
dlp-server gRPC 클라이언트.

문서 §2.1의 계약을 그대로 호출한다: Inspect(InspectRequest) -> Verdict.
Relay는 이 결과(action/transformed_body/reason)를 받아 "그대로 실행"만 한다.
판정 기준을 재해석하거나 자체 판단을 얹지 않는다.
"""
import json
from dataclasses import dataclass

import grpc

from config import settings
from proto import dlp_pb2, dlp_pb2_grpc


@dataclass
class Verdict:
    action: str              # allow | block | transform
    transformed_body: bytes
    reason: dict


def _fail_closed_verdict(detail: str) -> Verdict:
    """dlp-server 무응답/오류 시 기본 정책은 block (§2.4)."""
    action = "allow" if not settings.fail_closed else "block"
    return Verdict(
        action=action,
        transformed_body=b"",
        reason={"fault": True, "detail": detail, "note": "DLP 판정이 아닌 장애 대응"},
    )


def inspect(
    *,
    session_id: str,
    direction: str,
    method: str,
    path: str,
    headers: dict,
    body: bytes,
) -> Verdict:
    """단일 Inspect 호출. 실패 시 fail-closed verdict를 반환한다 (예외를 던지지 않음)."""
    try:
        with grpc.insecure_channel(settings.dlp_server_addr) as channel:
            stub = dlp_pb2_grpc.DLPInspectorStub(channel)
            request = dlp_pb2.InspectRequest(
                session_id=session_id,
                direction=direction,
                method=method,
                path=path,
                headers=headers,
                body=body,
            )
            response = stub.Inspect(request, timeout=settings.grpc_deadline_seconds)

        try:
            reason = json.loads(response.reason) if response.reason else {}
        except json.JSONDecodeError:
            reason = {"raw": response.reason}

        return Verdict(
            action=response.action,
            transformed_body=response.transformed_body,
            reason=reason,
        )
    except grpc.RpcError as e:
        return _fail_closed_verdict(f"grpc error: {e.code()} {e.details()}")
    except Exception as e:  # noqa: BLE001 - relay는 무조건 유효한 verdict를 만들어야 함
        return _fail_closed_verdict(f"unexpected error: {e}")
