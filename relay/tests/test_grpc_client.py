import grpc_client


def test_inspect_fails_closed_when_dlp_server_unreachable():
    # 존재하지 않는 포트로 호출 -> grpc.RpcError -> fail-closed verdict
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
