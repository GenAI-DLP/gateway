import json

from gateway_format import build_gateway_body, parse_gateway_body


def test_build_gateway_body_shape():
    body = build_gateway_body([{"role": "user", "content": "안녕"}])
    data = json.loads(body.decode("utf-8"))
    assert data == {"messages": [{"role": "user", "content": "안녕"}]}


def test_round_trip():
    messages = [
        {"role": "user", "content": "계좌 확인해줘"},
        {"role": "assistant", "content": "네, 도와드리겠습니다."},
    ]
    body = build_gateway_body(messages)
    assert parse_gateway_body(body) == messages


def test_parse_empty_body_returns_empty_list():
    assert parse_gateway_body(b"") == []
