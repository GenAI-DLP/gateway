"""
request_via_dlp_proxy()가 실제로 "TCP는 프록시로, TLS SNI는 다른 진짜 호스트명으로"
분리해서 붙는지 검증한다. 진짜 dlp-proxy 대신, 같은 방식으로 동작하는 로컬 TLS
서버(다른 CN으로 서명된 인증서)를 띄워서 확인한다 — curl --connect-to 검증과
동일한 아이디어를 pytest 안에서 자동화한 것.
"""

import asyncio
import datetime
import ssl

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from dlp_proxy_transport import DlpProxyTransportError, request_via_dlp_proxy

FAKE_UPSTREAM_HOST = "fake-upstream.example.com"


@pytest.fixture(scope="module")
def fake_upstream_cert(tmp_path_factory):
    """FAKE_UPSTREAM_HOST를 CN/SAN으로 하는 자체 서명 인증서 생성."""
    tmp_dir = tmp_path_factory.mktemp("certs")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, FAKE_UPSTREAM_HOST)])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(FAKE_UPSTREAM_HOST)]), critical=False
        )
        .sign(key, hashes.SHA256())
    )
    cert_path = tmp_dir / "cert.pem"
    key_path = tmp_dir / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return cert_path, key_path


async def _run_fake_proxy(cert_path, key_path, response_bytes: bytes):
    """요청 하나 받으면 response_bytes를 그대로 돌려주고 닫는 TLS 서버. (host, port) 리턴."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(str(cert_path), str(key_path))

    async def handle(reader, writer):
        await reader.read(65536)
        writer.write(response_bytes)
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0, ssl=ctx)
    port = server.sockets[0].getsockname()[1]
    asyncio.ensure_future(server.serve_forever())
    return "127.0.0.1", port, server


@pytest.mark.asyncio
async def test_request_via_dlp_proxy_success(fake_upstream_cert):
    cert_path, key_path = fake_upstream_cert
    body = b'{"ok": true}'
    response = (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: application/json\r\n"
        b"Content-Length: " + str(len(body)).encode() + b"\r\n"
        b"Connection: close\r\n\r\n" + body
    )
    host, port, server = await _run_fake_proxy(cert_path, key_path, response)
    try:
        resp = await request_via_dlp_proxy(
            method="POST",
            real_host=FAKE_UPSTREAM_HOST,
            path="/v1/test",
            headers={"Content-Type": "application/json"},
            body=b"{}",
            proxy_host=host,
            proxy_port=port,
            ca_cert_path=str(cert_path),
            timeout=5.0,
        )
    finally:
        server.close()

    assert resp.status == 200
    assert resp.body == body
    assert resp.headers["content-type"] == "application/json"


@pytest.mark.asyncio
async def test_request_via_dlp_proxy_blocked_response(fake_upstream_cert):
    cert_path, key_path = fake_upstream_cert
    body = b'blocked by DLP policy: {"matched": ["RRN"]}'
    response = (
        b"HTTP/1.1 403 Forbidden\r\n"
        b"Content-Type: text/plain\r\n"
        b"Content-Length: " + str(len(body)).encode() + b"\r\n"
        b"Connection: close\r\n\r\n" + body
    )
    host, port, server = await _run_fake_proxy(cert_path, key_path, response)
    try:
        resp = await request_via_dlp_proxy(
            method="POST",
            real_host=FAKE_UPSTREAM_HOST,
            path="/v1/test",
            headers={},
            body=b"{}",
            proxy_host=host,
            proxy_port=port,
            ca_cert_path=str(cert_path),
            timeout=5.0,
        )
    finally:
        server.close()

    assert resp.status == 403
    assert b"RRN" in resp.body


@pytest.mark.asyncio
async def test_request_via_dlp_proxy_connection_refused_raises(fake_upstream_cert):
    cert_path, _ = fake_upstream_cert
    with pytest.raises(DlpProxyTransportError):
        await request_via_dlp_proxy(
            method="POST",
            real_host=FAKE_UPSTREAM_HOST,
            path="/",
            headers={},
            body=b"{}",
            proxy_host="127.0.0.1",
            proxy_port=1,  # 특권 포트, 항상 거부됨
            ca_cert_path=str(cert_path),
            timeout=2.0,
        )


@pytest.mark.asyncio
async def test_request_via_dlp_proxy_bad_ca_path_raises_friendly_error():
    with pytest.raises(DlpProxyTransportError, match="CA 인증서 로드 실패"):
        await request_via_dlp_proxy(
            method="POST",
            real_host=FAKE_UPSTREAM_HOST,
            path="/",
            headers={},
            body=b"{}",
            proxy_host="127.0.0.1",
            proxy_port=9999,
            ca_cert_path="/nonexistent/ca.pem",
            timeout=2.0,
        )
