from gemini_client import _to_gemini_contents


def test_system_message_extracted_separately():
    messages = [
        {"role": "system", "content": "너는 친절한 상담원이다."},
        {"role": "user", "content": "안녕"},
    ]
    contents, system_instruction = _to_gemini_contents(messages)
    assert system_instruction == "너는 친절한 상담원이다."
    assert contents == [{"role": "user", "parts": [{"text": "안녕"}]}]


def test_assistant_role_mapped_to_model():
    messages = [
        {"role": "user", "content": "안녕"},
        {"role": "assistant", "content": "안녕하세요"},
    ]
    contents, system_instruction = _to_gemini_contents(messages)
    assert system_instruction is None
    assert contents == [
        {"role": "user", "parts": [{"text": "안녕"}]},
        {"role": "model", "parts": [{"text": "안녕하세요"}]},
    ]


def test_no_system_message_returns_none():
    contents, system_instruction = _to_gemini_contents(
        [{"role": "user", "content": "hi"}]
    )
    assert system_instruction is None
