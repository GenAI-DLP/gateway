"""
Relay 설정.

Gateway 릴레이는 로직이 거의 없는 얇은 컴포넌트다 (DLP_Server_아키텍처.md 참고).
여기 있는 값들은 전부 "누구에게 어떻게 연결할지"에 대한 설정이지,
판정/탐지/변환 로직이 아니다 — 그건 dlp-server의 몫이다.
"""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    # dlp-server gRPC 주소. 프로덕션에서는 Go 프록시가 이 역할을 하지만,
    # Demo 1(사내 Gateway 경로)에서는 Relay가 직접 gRPC로 dlp-server를 호출한다.
    dlp_server_addr: str = os.getenv("DLP_SERVER_ADDR", "localhost:50051")

    # 프록시 호출 deadline은 문서 §2.4 기준 3초. Relay도 동일 기준을 따른다.
    grpc_deadline_seconds: float = float(os.getenv("GRPC_DEADLINE_SECONDS", "3.0"))

    # dlp-server 장애(타임아웃/연결 실패) 시 정책 — 문서 §2.4 fail-closed가 기본.
    fail_closed: bool = os.getenv("FAIL_CLOSED", "true").lower() != "false"

    # openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    # openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    # openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        # "openai" | "gemini" — 실제 LLM 호출 대상 선택
    llm_provider: str = os.getenv("LLM_PROVIDER", "gemini")

    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    # Gemini — Google AI Studio 무료 티어. https://aistudio.google.com/apikey
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    gemini_base_url: str = os.getenv(
        "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"
    )

    # 데모 포트
    port: int = int(os.getenv("PORT", "8080"))


settings = Settings()
