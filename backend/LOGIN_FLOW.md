# 로그인 폼 / 공식 버튼 / 이전 페이지 복귀

## 승인 범위

- 공식 카카오 PNG를 변경 없이 자체 제공합니다. 이미지 파일은 아래 출처 원본과 SHA-256이 같습니다.
- 폼 페이지의 Referrer-Policy 충돌을 수정합니다. 서버의 Origin 검사와 폼 토큰 검사는 완화하지 않습니다.
- 로그인 또는 신규 가입 완료 후 요청한 사이트 내부 페이지로 복귀합니다. 직접 로그인 URL 진입 시 기본은 `/`입니다.
- 운영 DB 적용 / 실서비스 배포 / 일반 고객 로그인 버튼 노출 / 네이버 키 설정은 이번 PR이 자동 실행하지 않습니다.

## 공식 리소스

- 가이드: https://developers.kakao.com/docs/ko/kakaologin/design-guide
- 다운로드: https://developers.kakao.com/tool/download/Kakao%20Login.zip
- 원본 파일: `Kakao Login/PNG @2x/kakao_login_kr_xlarge.png`
- 크기: 896 × 92 / 1547 bytes.
- SHA-256: `ed361544b384131f777d6085638182abc8483a6b95fe2fead12acb3b9425b04e`.
- 저장: `backend/portal_static/kakao-login.png`.
- 제공: `/auth/assets/kakao-login.png`의 GET만 허용. 앱의 edge gate 및 Cloudflare Access 대상입니다.
- 다운로드는 일회성 개발 단계에서 수행했습니다. 배포·페이지 열기 때 외부 CDN에서 다운로드하지 않습니다.
- 색상/문구/말풍선을 재제작하지 않고, 이미지 전체 비율만 유지해 표시합니다.

## 출처 검사

`no-referrer`가 설정된 네이티브 HTML 폼은 `Origin: null`을 보낼 수 있습니다. 로그인·가입의 성공한 GET HTML 문서에만 `same-origin`을 사용합니다. 앱의 EdgeBoundary와 Worker 둘 다 동일하게 처리합니다.

- `/auth/login`, `/auth/signup` / GET / 200 / text/html → same-origin.
- callback / 리다이렉트 / 오류 / 이미지 / API → no-referrer.
- 모든 응답 no-store 유지.
- null/누락/외부 Origin 및 cross-site 요청 차단 유지.
- Worker는 브라우저 Origin을 대체하거나 만들어 보내지 않습니다.

## 복귀 대상과 링크 연결

명시적인 `return_to`가 우선이며, 없으면 승인된 같은 출처 Referer의 경로만 참고합니다. 유효한 힌트가 없으면 `/`입니다.

허용 경로: `/`, `/index.html`, `/apply.html`, `/portal/mypage`, `/portal/admin`, `/portal/enrollments`, `/portal/manual`.

정식 사이트의 로그인 링크를 연결할 때는 현재 페이지를 명시해야 합니다. 특히 첫 Cloudflare Access 인증의 중간 이동에서는 Referer가 달라질 수 있으므로, Referer만으로 이전 페이지가 항상 복원된다고 가정하면 안 됩니다.

- 메인: `/auth/login?return_to=%2F`
- 신청: `/auth/login?return_to=%2Fapply.html`
- 마이페이지: `/auth/login?return_to=%2Fportal%2Fmypage`

명시 값은 위 일곱 경로만 받습니다. 외부 URL/중복 return_to/인증경로/쿼리/해시/경로 우회는 허용하지 않습니다. 작성 중 신청서 값과 스크롤 위치는 복원 대상이 아닙니다. 이번 PR은 기존 메인·신청 HTML을 수정하거나 일반 고객에게 로그인 버튼을 노출하지 않습니다.

카카오·네이버에 등록하는 callback 주소는 기존의 `/auth/kakao/callback`, `/auth/naver/callback` 그대로입니다. 최종 복귀 경로를 callback 등록란에 넣지 않습니다. 복귀 대상은 기존 OAuth 시도/가입 대기 DB 기록으로 이어집니다. 역할 검사는 별개이므로 `/portal/admin` 복귀 요청이 관리자 권한을 부여하지 않습니다.

## DB 적용과 배포 순서 — 자동 실행 없음

기존 `007_oauth_handoff.sql`은 이미 적용된 정본이므로 수정하지 않습니다. 두 OAuth 테이블의 return_to CHECK에 세 정적 경로만 더하는 `008_login_return_paths.sql`을 별도 적용해야 합니다. 행 삭제/수정·새 권한·테이블 추가는 없습니다. 적용 도구는 의존 마이그레이션 체크섬과 advisory lock을 검사하고 한 트랜잭션으로 처리합니다. 이 도구와 migration 파일은 런타임 포털 이미지에 포함되지 않습니다.

1. 소유자가 대상/백업/잠금 영향을 확인하고 별도로 승인한 뒤 `python backend/login_return_migrate.py --apply`를 실행합니다. DB 접속 비밀값은 보안 환경에서만 제공합니다.
2. 현재 GCP 자동배포는 IAM-private 전용입니다. 이미 승인된 네트워크 공개+앱 gate 모드를 검사하는 배포 경계를 별도 검토하기 전에는 기존 guard를 무시하거나 무작정 deploy하지 않습니다.
3. 서버 이미지와 Worker 변경을 함께 테스트 배포합니다. 기존 Cloudflare의 본인 이메일 Allow 제한을 유지합니다. 새 브랜치의 wrangler 준비값을 그대로 운영에 덮어쓰지 않습니다.
4. 실제 카카오 최초 가입/재로그인/취소/로그아웃, 신청 페이지 복귀, 일반 회원 관리자 차단을 브라우저에서 확인합니다. CI의 가상 제공자 성공을 실제 카카오 로그인 성공으로 표현하지 않습니다.
5. 실제 수집 항목에 맞게 약관·개인정보 안내를 완료한 후 일반 공개를 검토합니다.

롤백은 이전 앱/Worker 코드 복원으로 합니다. 추가된 경로 CHECK는 기존 코드와 호환되므로 자동으로 되돌리거나 고객 데이터를 삭제하지 않습니다. 네트워크/IAM/Secret 변경은 이 PR의 롤백 대상이 아닙니다.

## 검증

- 기존 전체 백엔드 CI의 폐기 가능한 loopback PostgreSQL로 008 적용/재진입과 provider별 신규·기존 회원 복귀를 검사합니다.
- `node --test edge/worker.test.mjs edge/login-flow.test.mjs`.
- `cd backend && python -m pytest tests/test_login_flow.py tests/test_oauth.py tests/test_auth.py`.
- `cd backend && python tests/login_browser.py`: Chromium의 실제 Origin을 검사하며 네트워크/DB/제공자 응답은 모두 가상입니다.

## 이번 보완

- 가입 기록을 확인한 뒤 회원 등록/세션 발급에 실패해도, 검증된 가입 대기 기록의 복귀 경로를 재시도 링크에 유지합니다. POST 입력값의 임의 return_to는 사용하지 않습니다.
- 카카오 이미지 비율을 유지하면서 버튼 외곽 클릭 영역을 최소 44px로 설정했습니다. 원본 PNG는 변경하지 않았습니다.
- Naver 미연결/키 한쪽만 설정/정확한 callback/state/secret 비노출 설정 검사를 추가했습니다. 실제 Naver 연결은 하지 않았습니다.
- 008 마이그레이션의 의존 체크섬 불일치/재진입/DDL 실패 시 ledger 미기록을 모의 연결로 검사합니다. 실제 SQL/잠금 동작은 별도 폐기 가능한 PostgreSQL CI가 검증합니다.

## 네이버 준비 현황

사용자가 앱 등록과 `https://richonacademy.com/auth/naver/callback` 등록을 확인했습니다. 서버 측 `NAVER_CLIENT_ID`와 `NAVER_CLIENT_SECRET` 연결은 아직 확인되지 않았습니다. 키는 채팅/Git/프런트엔드에 올리지 않습니다. 준비된 OAuth 어댑터는 두 값이 모두 있을 때만 네이버를 구성하며, 한쪽만 있으면 시작을 거부합니다.

현재 Cloud Run 배포 가드는 기존 카카오 시험 구성의 Secret 목록만 허용합니다. 네이버 Secret 바인딩 추가는 해당 가드와 함께 별도 검토한 뒤 배포해야 합니다. 등록 완료가 키 연결이나 실계정 로그인 성공을 뜻하지 않습니다. 이번 PR은 네이버/카카오 실계정 로그인, 공식 검수 신청, 일반 공개를 자동 실행하지 않습니다.
