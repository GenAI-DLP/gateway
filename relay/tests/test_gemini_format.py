import json

from gemini_format import build_gemini_request_body, extract_gemini_text, to_gemini_contents


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
