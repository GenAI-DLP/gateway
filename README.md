# Demo 1 — 사내 Gateway 경로

`DLP_Server_아키텍처.md`에서 정의한 Demo 1(사내 포털 경로)의 프론트 + Gateway 릴레이 구현.
dlp-server 자체(탐지/정책/변환/로깅)는 이미 존재한다는 전제로, 그 앞단만 새로 만들었다.

## 무엇을 만들었나 / 안 만들었나

만든 것:
- `relay/static/index.html` — 사내 포털 챗 UI (빌드 불필요, 단일 파일)
- `relay/main.py` 외 — Gateway 릴레이 (FastAPI). 로직은 최소로 유지했다:
  - `X-Corp-User-Id` / `X-Corp-Role` 헤더 주입 (실제 SSO가 없으므로 데모에서는 UI 입력값을 그대로 사용 — 헤더 주입이라는 Relay의 역할 자체만 재현)
  - 대화를 gateway 포맷(`{"messages":[...]}`)으로 빌드
  - `Inspect(input)` gRPC 호출 → 판정대로 실행 (block이면 즉시 중단, transform이면 변환된 본문 사용)
  - OpenAI 호출 — 프로덕션에서 Go 프록시가 맡는 "판정대로 외부 LLM에 직접 중계" 역할을 이 데모에서는 Relay가 맡는다 (MITM이 필요 없는 직접 통합 경로이므로)
  - `Inspect(output)` gRPC 호출 → 판정대로 최종 응답 결정
- `relay/proto/dlp.proto` — 아키텍처 문서 §2.1/§5 계약을 그대로 옮긴 proto 정의 + 생성된 gRPC 스텁

**안 만든 것 (의도적으로):** PII 탐지, 정책 평가, 토큰화/마스킹, 감사 로그 저장 — 전부 dlp-server의 몫이며 Relay는 그 판정 결과(`action`/`transformed_body`/`reason`)를 그대로 실행만 한다.

## 아키텍처 상 위치

```
사내 포털(챗 UI) → Relay(/chat) ──gRPC Inspect(input)──▶ dlp-server
                       │                                      │
                       │◀──────────── Verdict ────────────────┘
                       │
                       ├─ block 이면 여기서 종료
                       ├─ allow/transform 이면 OpenAI 호출
                       │
                       └──gRPC Inspect(output)──▶ dlp-server ──▶ Verdict ──▶ 최종 응답
```

Relay는 문서 §1.2의 "Go 프록시" 행이 하는 일(헤더 주입은 프록시가 아니라 dlp-server 몫이지만, "판정 요청 후 Hold, 판정대로 외부 LLM에 직접 중계"하는 패턴) 을 MITM 없이 애플리케이션 레벨에서 재현한 것이다. 별도 Demo(외부 API 직접 호출 경로)에서는 이 자리를 Go MITM 프록시가 대신한다.

## 실행 방법

```bash
cd relay
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# .env에서 DLP_SERVER_ADDR(이미 떠 있는 dlp-server 주소)와 OPENAI_API_KEY를 채운다

uvicorn main:app --reload --port 8080
```

브라우저에서 `http://localhost:8080` 접속. 사번/역할을 입력하고 메시지를 보내면:
1. Relay가 `X-Corp-User-Id`/`X-Corp-Role` 헤더를 붙여 dlp-server에 `Inspect(input)`을 호출한다.
2. 차단이면 즉시 안내 메시지, 아니면 (변환된) 대화를 OpenAI에 보낸다.
3. OpenAI 응답도 다시 `Inspect(output)`을 거쳐 최종 표시된다.
4. 각 턴 아래 "입력 · 허용/변환/차단", "응답 · 허용/변환/차단" 배지와 판정 근거(JSON)가 표시된다 — 실제 서비스라면 관리자 대시보드에서만 보일 정보를 데모 편의상 화면에 노출한 것이다.

## dlp-server 쪽에서 맞춰야 할 것

- gRPC 리스닝 주소가 `.env`의 `DLP_SERVER_ADDR`와 일치해야 한다.
- `Inspect` 요청의 `body`는 gateway 포맷(`{"messages":[{"role":"user"|"assistant","content":"..."}]}`)의 JSON 바이트로 온다 — `adapters/gateway.py`가 파싱하는 그 포맷이다.
- `direction`은 `"input"` 또는 `"output"`으로 온다.
- 헤더 맵에 `X-Corp-User-Id`, `X-Corp-Role`이 들어온다 (§2.3의 role 해석 입력).
- `transform`일 때 `transformed_body`는 같은 gateway 포맷 JSON이어야 Relay가 되돌려 파싱할 수 있다.
- `reason`은 JSON 문자열이어야 UI가 파싱해 배지 아래 상세 정보로 보여준다 (아니어도 동작은 하지만 `{"raw": "..."}`로만 표시됨).

## 장애 정책

`Inspect` 호출이 타임아웃(기본 3초, `GRPC_DEADLINE_SECONDS`)되거나 실패하면 fail-closed로 `block` 판정을 반환한다 (`.env`의 `FAIL_CLOSED=false`로 시연 안정용 allow 전환 가능) — 문서 §2.4와 동일한 정책을 Relay 레벨에도 적용했다.

## 확인한 것 / 확인 못 한 것

로컬에서 `Inspect`를 흉내 내는 임시 gRPC 서버로 allow·transform·OpenAI 왕복까지 전체 플로우가 정상 동작하는 것을 확인했다 (이 테스트용 서버는 코드에 포함하지 않았다 — 실제 dlp-server가 이미 있다고 해서). block 경로와 fail-closed 경로는 코드 리뷰로 확인했으며, 실제 dlp-server와 붙여서 reason 스키마가 기대와 다르게 오는 경우는 없는지는 실환경에서 한 번 더 확인이 필요하다.
