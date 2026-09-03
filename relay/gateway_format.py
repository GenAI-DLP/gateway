"""
사내 Gateway 포맷 <-> 파이썬 객체 변환.

adapters/gateway.py (dlp-server 측)가 파싱하는 그 포맷을 그대로 만든다.
Relay는 이 포맷을 "만들기만" 한다 — 안의 내용을 검사/변형하지 않는다.
"""

import json


def build_gateway_body(messages: list[dict]) -> bytes:
    """messages: [{"role": "user"|"assistant"|"system", "content": "..."}]"""
    return json.dumps({"messages": messages}, ensure_ascii=False).encode("utf-8")


def parse_gateway_body(body: bytes) -> list[dict]:
    """gRPC에서 돌아온 body(원본 또는 transformed)를 messages 리스트로 되돌린다."""
    if not body:
        return []
    data = json.loads(body.decode("utf-8"))
    return data.get("messages", [])
