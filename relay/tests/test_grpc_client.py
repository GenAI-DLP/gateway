import dataclasses

import grpc_client
from config import settings


def test_inspect_fails_closed_when_dlp_server_unreachable(monkeypatch):
    # 로컬에 dlp-server가 실제로 떠 있어도(개발 중 흔함) 이 테스트가 항상
    # "미응답" 상황을 재현하도록, 확실히 막힌 주소로 강제 오버라이드한다.
    # 기본 설정(settings.dlp_server_addr)에 의존하면 dlp-server 기동 여부에
    # 따라 테스트 결과가 뒤집히는 flaky 테스트가 된다.
    # Settings는 frozen dataclass라 속성을 직접 못 바꾸므로, grpc_client가
    # 참조하는 모듈 레벨 settings 자체를 교체된 사본으로 갈아끼운다.
    unreachable = dataclasses.replace(settings, dlp_server_addr="localhost:1")
    monkeypatch.setattr(grpc_client, "settings", unreachable)

    verdict = grpc_client.inspect(
        session_id="test-session",
        direction="input",
        method="POST",
        path="/chat/completions",
        headers={},
        body=b'{"messages":[]}',
    )
    assert verdict.action in ("block", "allow")  # FAIL_CLOSED 설정에 따라 달라짐
    assert verdict.reason.get("fault") is True
