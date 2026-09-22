# A안: 기존 도메인의 카카오·네이버 로그인 준비

## 승인과 범위

사용자가 `A로`를 선택했습니다. 공개 서비스 주소는 `https://richonacademy.com`으로 고정합니다.
카카오 앱 ID는 사용자가 제공한 **1585992**입니다. 비밀키가 아닙니다.
PR #9 병합 `6dac44608785c535f6170dcf0999183228da3c7c` 위에서 로그인만 분리해 구현합니다.
가격·메모 보관용 Draft PR #10은 이번 작업에 포함하거나 병합하지 않습니다.

## 주소

| 기능 | 주소 |
|---|---|
| 로그인 | https://richonacademy.com/auth/login |
| 카카오 복귀 | https://richonacademy.com/auth/kakao/callback |
| 네이버 복귀 | https://richonacademy.com/auth/naver/callback |
| 마이페이지 | https://richonacademy.com/portal/mypage |
| 관리자 | https://richonacademy.com/portal/admin |

위 주소는 이번 코드의 확정 연결 계약입니다. 아직 해당 도메인에 배포됐다는 뜻은 아닙니다.
카카오 등록 주소에는 마지막 `/`를 추가하지 않습니다.

## 제공하는 로그인 흐름

1. GET `/auth/login`: 설정된 제공자의 버튼. 카카오만 설정하면 카카오 버튼만 표시합니다.
2. POST `/auth/start`: 정확한 브라우저 Origin과 CSRF 검사. 브라우저 결합 5분짜리 state 생성.
3. GET 제공자별 callback: provider/app/state/browser/만료 확인. DB에서 state를 먼저 소비하고 커밋한 후 코드 교환.
4. 카카오 토큰 정보의 app_id/id/만료 검증 후 프로필 id 대조. 닉네임 동의 거부 시에도 로그인 가능.
5. 기존 회원은 새 세션 발급. 처음이면 10분짜리 임시 가입 ticket과 필수 동의 화면.
6. 동의 폼은 브라우저와 해당 ticket에 결합. 동의 후 일반 회원 생성. 세션 커밋 성공 후에만 쿠키 발급.
7. 기존 `/auth/me`, `/auth/csrf`, `/auth/logout`, `/auth/logout-all` 및 관리자 권한 검사를 재사용.

카카오 회원은 REST 키가 아닌 앱 ID+제공자 사용자 ID로 식별하므로 REST 키 교체로 중복 가입하지 않습니다.
네이버는 client ID와 제공자 응답의 resultcode/id로 식별합니다. 이름·전화번호·이메일 자동 병합은 없습니다.
기존 수동 수강 기록도 임의로 회원에게 연결하지 않습니다. 첫 가입자를 관리자로 만드는 기능은 없습니다.

Kakao S256 PKCE와 confidential client 인증을 사용합니다. 네이버는 공식 문서에 없는 PKCE 인자를 추정하지 않습니다.
토큰 교환/프로필 조회는 고정 HTTPS endpoint로만 전송하고 redirects를 따르지 않습니다.
네트워크 타임아웃과 64KB 응답 상한을 두고, 제공자 오류 원문을 클라이언트에 돌려주지 않습니다.
ID token을 무검증 디코딩해 신원으로 사용하지 않습니다. 카카오 OIDC 활성화는 필요하지 않습니다.
소셜 access/refresh token, 인가 코드와 시크릿은 DB나 HTML/localStorage에 저장하지 않습니다.
state/browser/ticket은 DB에 해시로만 저장합니다. 임시 가입 신원은 만료 시간이 있는 테이블에서만 처리합니다.

## A안 연결 구성과 기존 주문 서버 보존

- 기존 정적 홈페이지는 변경하지 않습니다. Cloudflare Worker에는 `/auth/*`, `/portal/*`만 연결하는 준비 코드를 둡니다.
- 기존 `richon-backend-test`를 공개하지 않습니다. 기존 main.py, 주문/health 경로, IAM, 배포 워크플로는 변경하지 않았습니다.
- `portal_entry.py`와 `Dockerfile.portal`은 별도 로그인·포털 서비스에 사용할 진입점/이미지입니다.
  이미지에도 orders.py/main.py/마이그레이션을 포함하지 않습니다. 실제 새 Cloud Run 생성·공개는 아직 실행하지 않았습니다.
- Worker/포털 사이에는 독립적인 256비트 이상의 임의 origin-gate secret을 사용합니다.
  이 값은 관리자 로그인 대체 수단이 아닙니다. 각 API에서 실제 회원/관리자 인증과 CSRF를 다시 검사합니다.
- 브라우저의 실제 Origin은 그대로 검사합니다. Worker가 신뢰 Origin으로 위조하거나 인증 헤더를 전달하지 않습니다.
- Worker는 외부 OAuth redirects를 따라가지 않고 브라우저로 반환합니다. 쿠키는 host-only/Secure/HttpOnly를 유지합니다.
- Worker/서버 모두 기본 OFF입니다. edge/wrangler.toml에는 활성 Routes를 넣지 않았습니다.

## 키와 환경변수

사용자는 다음 Secret 저장과 런타임 읽기 권한 부여를 완료했다고 알렸습니다.
이번 PR에서는 실제 Secret 내용/버전/IAM을 읽거나 검증하지 않았습니다.

| 변수 | 연결할 값 |
|---|---|
| KAKAO_APP_ID | 1585992 |
| KAKAO_CLIENT_ID | richon-kakao-rest-api-key의 확인된 특정 버전 |
| KAKAO_CLIENT_SECRET | richon-kakao-client-secret의 확인된 특정 버전 |
| NAVER_CLIENT_ID / NAVER_CLIENT_SECRET | 네이버 준비 전에는 모두 생략 |
| RICHON_OAUTH_ORIGIN | https://richonacademy.com |
| RICHON_AUTH_ALLOWED_ORIGINS | https://richonacademy.com |
| RICHON_EDGE_SECRET | Worker와 별도 포털 서버의 일치하는 비밀값. Git/채팅 저장 금지 |
| RICHON_TERMS_VERSION / RICHON_PRIVACY_VERSION | 실제 검토·승인한 문서 버전 |
| RICHON_TERMS_URL / RICHON_PRIVACY_URL | 실제 가입용으로 승인한 HTTPS 문서 주소 |

AUTH/OAUTH/PORTAL과 EDGE 기능은 별도 플래그입니다. 실제 값은 공개 전 검토 후 설정합니다.
현재 홈페이지의 약관/개인정보 문서를 읽거나 법적 적합성을 확인한 것으로 간주하지 않습니다.
미승인 문서 버전을 임의로 운영 동의 기록에 쓰지 않습니다.

## DB

007_oauth_handoff.sql은 기존 Draft와 같은 내용이며, 실제 적용기는 선행 001/002 이력을 확인합니다.
006 가격·메모 변경과 독립적입니다. 동일 체크섬으로 적용돼 있으면 다시 만들지 않습니다.
앱 시작 또는 HTTP 요청에서 DDL을 실행하지 않습니다. 실제 Neon 적용은 별도 승인 대상입니다.
회원 생성/세션 생성은 기존 각각의 트랜잭션입니다. 세션 생성 실패 시 회원만 남을 수 있으나 성공 쿠키는 반환하지 않습니다.
재로그인으로 이어갈 수 있으며, 실패한 state/ticket은 인증에 재사용하지 않습니다.

## 검증과 공개 전 남은 것

- test_oauth.py: 제공자 HTTP 모의 응답, 앱/사용자 ID·만료·닉네임·CSRF·중복 쿠키·크기 제한.
- test_oauth_postgres.py: 폐기 가능한 localhost richon_ci만 사용. state/ticket 동시성, 첫 가입·재로그인·로그아웃, 커밋 실패.
- test_portal_entry.py: origin gate, 회원/관리자 검사 유지, private 경로 없음, 잘못된 구성·큰 요청 차단.
- edge/worker.test.mjs: 모의 transport로 경로·쿠키·redirect·헤더 처리. 실제 Cloudflare 배포 시험은 아님.
- 별도 CI에서 포털 Docker 이미지 빌드/기동/민감 경로 제외를 검사. 기존 CI와 합쳐 최종 결과는 PR에 기록.

아직 실제 GCP/Cloudflare/Neon/제공자 로그인 테스트나 공개 설정은 하지 않았습니다.
공개 전에는 별도 포털 서비스 생성 승인, 최소권한 DB/Secret 연결, 실제 Worker Routes,
플랫폼 callback 쿼리 로그 보관 방지, rate limit, 문서 동의·운영자 지정, 실제 모바일/브라우저 종단간 검증이 필요합니다.
rate limiting/플랫폼 로그 정책은 이 소스만으로 완료되지 않습니다. edge/README.md를 따릅니다.

## 공식 근거 (2026-09-23 확인)

- https://developers.kakao.com/docs/ko/kakaologin/rest-api
- https://developers.naver.com/docs/login/api/api.md
- https://developers.naver.com/docs/login/profile/profile.md
- https://developers.cloudflare.com/workers/configuration/routing/routes/
- https://developers.cloudflare.com/workers/runtime-apis/request/
- https://docs.cloud.google.com/run/docs/authenticating/overview
