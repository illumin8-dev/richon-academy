# 간편 로그인 준비 PR — 기본 OFF / 외부 인증 미연결

## 이번 범위와 선택

PG 계정 및 카카오/네이버 앱 신청 전, 회원 식별과 로그인 유지 기반만 준비합니다.
운영 홈페이지/Cloud Run/Neon/IAM/결제/주문 데이터는 변경하지 않습니다.
실제 제공자 토큰 검증, 가입 동의 화면, 계정 연결은 아직 구현하지 않았습니다.

| 선택 | 구조 / 장점 | 단점 / 운영·유지보수 부담 |
|---|---|---|
| A. JWT + refresh token | 서명 검증으로 API 호출 인증 / 다중 API에 편리 | 즉시 회수에는 추가 저장소·버전 검사 등이 필요 / refresh 회전·키 교체·재사용 탐지로 복잡도 증가 |
| B. 임의 세션 토큰 + PostgreSQL | 쿠키의 임의 토큰으로 서버 세션 확인 / 로그아웃·회원 정지·권한 변경 즉시 반영 | 인증 요청마다 짧은 DB 트랜잭션 / 인증 트래픽이 커지면 DB 비용·병목 관찰 필요 |

이번 단일 웹사이트의 준비안은 **B**입니다. 별도 Redis, JWT 서명키, 외부 인증 의존성을 추가하지 않습니다.
본격 공개 전에 세션 정책·도메인·접근 경계를 확정합니다. 토큰 발급/회수 로직을 auth_core에 모아 향후 변경 범위를 제한합니다.

## 구현한 것

- `richon.members`: 리치온 내부 UUID / 표시 이름 / 역할 / 상태 / 세션 회수 버전 / 필수 약관 버전·동의 시점.
- `richon.auth_identities`: **provider + app_id + subject**를 유일하게 보관. 전화번호·이메일·이름으로 검색하거나 자동 병합하지 않음.
- `richon.member_sessions`: 256비트 임의 토큰의 SHA-256만 보관. 원문 토큰·소셜 access/refresh token은 DB에 저장하지 않음.
- 신규 가입 기본 권한은 항상 member. 첫 가입자 자동 admin 처리 없음.
- 세션 재발급 시 이전 동일 회원 세션 회수, 현재 기기 로그아웃, 전체 기기 로그아웃.
- 서버 기준 절대/유휴 만료, 비활성 회원 차단, 역할 변경 시 재로그인 요구.
- Secure / HttpOnly / SameSite=Lax / Path=/ / Domain 없는 `__Host-` 쿠키.
- 변경 요청에는 정확한 Origin 허용목록 + 세션에 결합된 CSRF 토큰을 검사. SameSite만으로 허용하지 않음.
- 오류 응답과 로그에 세션·DB 주소·개인정보를 포함하지 않음. DB 장애는 503이고 로그아웃 성공으로 처리하지 않음.

**개발 기본값**: 절대 만료 12시간 / 유휴 만료 30분. 최종 고객 UX 정책은 미확정입니다.
만료된 세션 레코드의 주기적 정리·요청 제한·감사 이벤트는 공개 전 후속 범위입니다.

## 현재 제공 가능한 HTTP 표면

기본 `RICHON_AUTH_ENABLED=false`로 `/auth/*`를 등록하지 않습니다. enabled=true일 때는
`RICHON_AUTH_ALLOWED_ORIGINS`에 정확한 HTTPS origin 목록이 있어야 시작합니다. 빈 목록이나 와일드카드는 거부합니다.
자동 CORS 설정이나 기존 주문/점검 경로의 공개는 하지 않습니다.

| 경로 | 역할 |
|---|---|
| GET /auth/me | 서버가 확인한 현재 회원 UUID / 표시 이름 / 역할 |
| GET /auth/csrf | 로그인된 세션에 결합된 CSRF 토큰; 세션 원문은 반환하지 않음 |
| POST /auth/logout | 현재 세션 회수 후 쿠키 삭제 |
| POST /auth/logout-all | 현재 회원의 세션 버전 증가와 기존 세션 회수 후 쿠키 삭제 |

`require_member` / `require_admin`은 이후 고객 관리 경로에 적용할 의존성입니다.
현재 주문 API는 기존 Cloud Run IAM 보호를 그대로 사용합니다. 이 PR이 주문에 회원 소유권을 붙이지는 않습니다.

**/auth/login /signup /mock-login /link /merge 경로는 없습니다.**
테스트는 Python에서 임시 DB의 내부 함수를 직접 사용하며, 외부에서 회원번호만 보내 로그인하는 우회 경로를 만들지 않습니다.

## 외부 인증 연결 시 반드시 지킬 계약

`VerifiedIdentity`는 내부 어댑터의 데이터 형식일 뿐, 생성 자체가 인증을 수행하지 않습니다.
`register_verified_identity()` / `issue_session()`을 사용자 입력이나 IAM 통과만으로 호출하면 안 됩니다.

실제 카카오·네이버 앱 준비 후 다음 흐름을 구현합니다:

1. 브라우저에 묶인 일회용 state / 만료 / 재사용 차단, 지원되는 PKCE, 허용된 callback·return URL.
2. 서버에서 인가 코드 교환 및 제공자 응답 검증. OIDC를 선택하면 서명/issuer/audience/nonce/만료를 검증.
3. 제공자가 검증한 app-scoped subject로 기존 회원 확인. 처음 가입할 때 실제 필수 약관 동의 완료 후만 회원 생성.
4. 성공한 신규 세션이 DB에 커밋된 뒤에만 set_session_cookie 호출. 소셜 토큰이나 JWT를 브라우저 저장소에 보관하지 않음.
5. 전용 도메인/프록시 선택과 CSRF·CORS·Cloud Run IAM 분리 검증. run.app에 프론트를 곧바로 붙이지 않음.

공개 JWT, 미검증 id_token decode, 전화번호 문자열 비교를 인증 대신 사용하는 흐름은 포함하지 않습니다.

## 카카오·네이버 계정 연결 제안 — 이번에 실행하지 않음

이름·인증된 번호 일치는 계정 연결의 후보 판단에 사용할 수 있지만, 현재 번호 점유가 과거 계정 소유를 보장하지는 않습니다.
기존 계정에 재로그인 → 다른 제공자에도 로그인 → 연결 확인을 거치는 방식을 제안합니다.
이미 서로 다른 두 회원에 주문·결제가 있으면 단순 연결이 아니라 별도 회원 통합 작업이며 승인·충돌 정책이 필요합니다.
휴대폰 인증 공급자 / 후보 안내의 정보 노출 방지 / 양쪽 계정 재인증 / 연결 감사 이력은 후속 설계입니다.
이 PR에는 이름·전화번호 자동 병합이나 기존 비회원 주문 자동 귀속 코드가 없습니다.

## DB 적용과 배포 상태

`migrations/002_auth_foundation.sql` + `auth_migrate.py`는 **검토용**입니다.
준비된 001 마이그레이션의 체크섬과 이력을 확인하고 동일 트랜잭션션에서만 002를 적용합니다.
적용 기록의 체크섬이 다르거나 테이블이 충돌하면 실패합니다. 앱 시작·HTTP 요청에서 DDL을 실행하지 않습니다.

이번에는 CI의 폐기 가능한 PostgreSQL에만 적용합니다. 실제 Neon에는 적용하지 않습니다.
런타임 이미지에는 auth_core.py / auth_http.py만 추가하며, 새 DDL·실행기는 업로드 허용목록에서 제외합니다.
실제 적용 시 schema owner와 최소권한 runtime DB 역할 분리도 먼저 확인합니다.

## 검증

- 순수/HTTP 모의 테스트: `python -m pytest tests/test_auth.py`.
- 실제 SQL 테스트: 기존 CI의 `RICHON_EMPTY_TEST_DB=YES` + loopback `/richon_ci` 전용 DSN만 허용.
- 기존 001 시험 fixture를 재사용하여 빈 richon 스키마만 생성·제거. 실제 애플리케이션 DATABASE_URL이 설정된 환경은 거부.
- 제공자 연동·실제 브라우저 쿠키·Neon TLS·공개 서비스 보안 검증을 대신하지 않습니다.

## 참고

- https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- https://developers.kakao.com/docs/ko/kakaologin/rest-api
- https://developers.naver.com/docs/login/devguide/devguide.md
