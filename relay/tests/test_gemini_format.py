import json

from gemini_format import (
    build_gemini_request_body,
    extract_gemini_text,
    friendly_gemini_error,
    to_gemini_contents,
)


def test_to_gemini_contents_maps_assistant_to_model():
    contents, system_instruction = to_gemini_contents(
        [
            {"role": "system", "content": "너는 친절한 상담원이다."},
            {"role": "user", "content": "안녕"},
            {"role": "assistant", "content": "안녕하세요"},
        ]
    )
    assert system_instruction == "너는 친절한 상담원이다."
    assert contents == [
        {"role": "user", "parts": [{"text": "안녕"}]},
        {"role": "model", "parts": [{"text": "안녕하세요"}]},
    ]


def test_build_gemini_request_body_shape():
    body = build_gemini_request_body([{"role": "user", "content": "hi"}])
    data = json.loads(body.decode("utf-8"))
    assert data == {"contents": [{"role": "user", "parts": [{"text": "hi"}]}]}
    assert "system_instruction" not in data


def test_extract_gemini_text_happy_path():
    data = {
        "candidates": [
            {"content": {"parts": [{"text": "안녕"}, {"text": "하세요"}]}},
        ]
    }
    assert extract_gemini_text(data) == "안녕하세요"


def test_extract_gemini_text_missing_candidates_returns_empty():
    assert extract_gemini_text({}) == ""
    assert extract_gemini_text({"candidates": []}) == ""
    assert extract_gemini_text({"error": {"message": "blocked"}}) == ""


def test_friendly_gemini_error_429_has_no_raw_json():
    raw = json.dumps(
        {"error": {"code": 429, "message": "You exceeded your current quota."}}
    ).encode("utf-8")
    msg = friendly_gemini_error(429, raw)
    assert "429" not in msg  # 원본 코드/JSON을 그대로 노출하지 않음
    assert "무료 티어" in msg


def test_friendly_gemini_error_503():
    msg = friendly_gemini_error(503, b'{"error":{"message":"overloaded"}}')
    assert "과부하" in msg


def test_friendly_gemini_error_400_surfaces_message():
    raw = json.dumps({"error": {"message": "Invalid JSON payload"}}).encode("utf-8")
    assert "Invalid JSON payload" in friendly_gemini_error(400, raw)


def test_friendly_gemini_error_unknown_status_falls_back():
    msg = friendly_gemini_error(500, b"not json at all")
    assert "500" in msg
    assert "not json at all" in msg


def test_friendly_gemini_error_handles_malformed_json():
    # 깨진 JSON이어도 예외 없이 fallback 메시지를 만들어야 한다
    msg = friendly_gemini_error(429, b"{not valid json")
    assert "무료 티어" in msg  # 429는 바디 파싱 실패해도 고정 메시지
