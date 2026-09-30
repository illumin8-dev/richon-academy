# ADMIN / MYPAGE NEXT HANDOFF

- 기준일: 2026-09-30
- 선행 조건: 로그인/회원가입 회귀 수정 PR #88 배포 및 확인 후 진행

## 사용자 확인 이슈

1. 관리자 UI 정합
- 강의/수강권 화면과 기존 월별 수강관리/수강생 관리 화면 사이에 구버전/신버전 UI가 섞여 보임.
- 공통 admin visual family와 navigation 구조를 다시 맞춘다.

2. 404 경로
- 관리자 사이드바의 `월별 수강관리`, `수강생 수동 등록/수정` 클릭 시 `{"detail":"Not Found"}` 발생.
- frontend href / Worker allowlist / portal_entry route / router install feature flag / candidate 이미지 source를 각각 비교한다.
- 코드 미배포, route 누락, old-new 혼합 중 무엇인지 추정하지 말고 실제 경계를 확인한다.

3. 마이페이지 내 정보 UX
- 현재 정보가 눈에 잘 안 들어오고 공간 낭비가 큼.
- 불필요한 설명/TMI 축소.
- 라벨/값 폭과 정렬 통일.
- 가입일/광고수신 같은 보조정보는 위계를 낮춘다.
- 휴대전화는 DB canonical 숫자-only 값을 유지하되 화면은 `010-1234-5678`로 표시한다.

4. 로그인 연결 UX
- `연결된 로그인`과 하단 `로그인 연결 관리`가 떨어져 있어 연관성이 약함.
- 연결된 로그인 행 자체에 관리 affordance를 붙이는 방향으로 통합한다.

5. 회원 count
- 관리자 `전체 회원`에 withdrawn/탈퇴 회원을 포함하지 않는 방향.
- active + disabled를 전체 회원으로 볼지 active만 볼지는 status 의미와 운영 목적을 확인해서 결정.
- 탈퇴회원은 필요하면 별도 지표로 분리한다.

6. 회원 상세
- 회원 관리에서 이름/행 클릭 시 상세 확인 가능하도록 검토 및 구현.
- 최소 후보 정보:
  - 기본 회원정보
  - 연결 로그인
  - 현재/과거 수강권
  - 수강 강의/기수
  - 신청/주문 이력
- 상세 패널 또는 상세 페이지 중 현재 admin 구조에 맞는 방식을 선택한다.

7. 실제 데이터 경계
- synthetic placeholder와 production DB 실제 데이터를 구분한다.
- 빈 화면이 데이터 미연결 때문인지 실제 0건인지 API/readback으로 확인한다.

## 우선순위

1. 404 경로 원인 확정/수정
2. admin UI family 정합
3. 회원 count 정의 수정
4. 회원 상세
5. 마이페이지 정보 밀도/연결 로그인 UX


## 로그인 재현 상태 / 2026-09-30

- 로그인/회원가입 UI 회귀 수정 PR #88 병합 및 protected candidate 배포 완료.
- 현재 candidate: `richon-portal-handoff-36597611986-1`.
- 첫 비로그인 마이페이지 진입 시 간편 로그인 modal 자동 오픈.
- standalone auth/signup UI 현대화, provider-locked field, phone display formatting 적용.
- 현재 사용자 재현에서 Kakao 로그인/회원가입이 다시 완료되지 않음.
- 운영 read-only 진단 결과:
  - 현재 candidate `/auth/start` POST 3건 모두 HTTP 200.
  - `/auth/kakao/callback` current-candidate 요청 0건.
  - `oauth_callback_failed stage=...` 이벤트 0건.
  - 따라서 현재 증거로는 callback 내부 / CI / signup DB 저장 실패가 아니라 provider 이동 후 richon callback 도착 전 구간 문제.
- 실제 Kakao/Naver E2E 성공 기록은 PR #49에 있고, 해당 handoff 구현은 PR #46.
- PR #46 성공 시점과 현재 `provider_handoff` / `HANDOFF_JS` 핵심 이동 방식은 동일함.
- 다음 확인은 실제 브라우저에서 Kakao 버튼 클릭 후:
  1. Kakao 도메인 화면이 실제 나타나는지
  2. 나타난다면 인증/동의 뒤 어느 URL로 이동하는지
  3. Kakao 화면 자체에서 오류가 나는지
  를 사용자 개인정보/코드 없이 관찰하고, 필요 시 provider console redirect URI/consent 상태와 대조.


## 작업 체크포인트 / admin-mypage-operations-unification

### 완료된 코드 변경
- 404 원인 확정:
  - `/portal/enrollments`, `/portal/manual` route/code/Worker allowlist/static file 모두 존재.
  - 실제 원인은 `RICHON_MONTHLY_ENABLED=false`, `RICHON_MANUAL_ENABLED=false`로 route가 설치되지 않은 상태.
- `monthly_store.py`가 runtime에서 `schema_migrations`를 읽던 경로 제거.
  - manual feature가 ON일 때 실제 `manual_enrollments` table 존재 여부로 fail-closed.
- `portal_readiness.py`에 monthly/manual feature flag와 DB004/005 runtime ACL 계약 초안 추가.
- 관리자 UI shell:
  - `courses`와 동일한 topbar/sidebar/page heading family로 `enrollments`, `manual` 외형 통합 초안 적용.
- 회원 count:
  - `members_total`은 withdrawn 제외하도록 수정.
  - 회원 목록 기본 전체도 withdrawn 제외, `status=withdrawn` 명시 필터일 때만 탈퇴회원 조회.
- 회원 상세:
  - `GET /portal/api/admin/members/{member_id}` endpoint 골격 추가.
  - canonical course enrollment / legacy monthly enrollment / linked orders를 한 응답으로 보는 store query 추가.
  - 관리자 회원 이름 클릭 시 상세 dialog를 여는 UI 초안 추가.
- 마이페이지:
  - 내 정보 2열 compact grid로 재구성.
  - 긴 활용 목적 문구 제거.
  - 연결된 로그인과 `관리` action을 같은 블록으로 통합.
  - 이름 수정 field는 설명문 대신 회색 잠금 field + lock mark.
  - phone/email placeholder 보강.
- shared source와 portal_static의 mypage/account 파일 동기화 완료.

### 아직 하지 않은 것
- monthly/manual 운영 ACL 실제 적용 helper는 아직 생성되지 않음.
- `RICHON_MONTHLY_ENABLED=true`, `RICHON_MANUAL_ENABLED=true`는 아직 적용하지 않음.
- protected candidate에 이 branch 코드는 아직 배포하지 않음.
- current branch 전체 CI/브라우저 테스트는 아직 실행 전.
- 회원 상세 response model / SQL / UI 회귀 테스트 추가 필요.
- enrollments/manual 공통 shell의 CSS 충돌 및 모바일 확인 필요.
- production API readback으로 실제 데이터 0건/synthetic 여부 확인 필요.
- Kakao callback 미도착 문제는 별도 미해결:
  - current candidate /auth/start는 200 성공.
  - /auth/kakao/callback 요청은 0건.
  - callback stage failure도 0건.

### 다음 작업 단위
1. 현재 branch CI가 깨지지 않도록 테스트/타입 정리.
2. DB004/005 legacy admin runtime ACL 전용 owner helper 작성 + disposable PostgreSQL 검증.
3. PR 생성/CI.
4. ACL owner 적용 후 protected candidate에서 monthly/manual feature ON.
5. 실제 /portal/enrollments, /portal/manual route/API readback.
6. production data 경계 확인 후 UI 세부 마감.


### 체크포인트 1 / PR #91 1차 CI
- Draft PR #91 생성: `fix(admin): unify operations, member detail and account UX`.
- 첫 CI에서 Same-domain edge/image PASS, standalone admin preview PASS.
- Portal UI failure는 기능 오류가 아니라 shared shell drift:
  - `frontend/shared/mypage.html` 수정 후 `backend/portal_static/mypage.html`을 단순 복사해 build 규칙과 달라짐.
  - `tools/build_site_shell.py` 규칙대로 shared header/footer를 삽입해 generated mypage를 재생성.
- 수정 후 PR은 mergeable=true.
- 다음: 최신 head CI 재확인 후 legacy admin runtime ACL helper 작성.


### 체크포인트 2 / legacy admin ACL helper
- `ops/prepare_legacy_admin.py` 생성.
- 목적: 이미 적용된 DB004/005에 `richon_portal_login`의 월별/수동관리 최소권한만 추가.
- helper가 하지 않는 것:
  - 고객 row 변경 없음
  - DDL/schema 변경 없음
  - Cloud Run feature flag 변경 없음
  - IAM/Secret/provider 변경 없음
- DB004/005 checksum이 정확히 일치해야만 진행.
- 적용 후 restricted runtime readback + `portal_readiness.check_role` 검증.
- confirmation phrase: `APPLY_LEGACY_ADMIN_GRANTS`.
- `manual_store._enrollment`은 실제 수정하지 않는 `monthly_enrollments`까지 FOR UPDATE하던 불필요 lock을 제거하고 `manual_enrollments`만 lock.
- 실제 운영 ACL 적용은 아직 하지 않음.


### 체크포인트 3 / exact legacy runtime test
- `backend/tests/test_legacy_admin_runtime.py` 추가.
- disposable PostgreSQL에서:
  - DB004/005 exact schema
  - `richon_portal_login` ACL 준비
  - readiness exact contract
  - 수동 과정/수강생/수강/term/audit INSERT
  - 허용된 profile/term/manual archive UPDATE
  - monthly trigger 실행
  을 실제 제한 역할로 검증.
- 금지 검증:
  - DELETE
  - TRUNCATE
  - monthly_enrollments 직접 UPDATE
  - schema_migrations SELECT
- helper source가 Cloud Run deploy/env enable/customer row mutation을 포함하지 않는 계약도 검증.
- 다음: PR #91 최신 CI 확인 및 회귀 수정.


### 체크포인트 4 / DB017 restricted-runtime hardening
- exact ACL 테스트에서 DB004 trigger 함수의 `FOR UPDATE / FOR SHARE`가 runtime에 불필요한 UPDATE 권한을 요구하는 문제 발견.
- 권한을 넓히지 않고 새 migration `017_monthly_runtime_hardening` 추가:
  - `validate_monthly_term()`의 row-lock clause 제거.
  - 기존 검증 로직 / confirmed immutability / order snapshot checks 유지.
  - PUBLIC EXECUTE revoke 유지.
- `monthly_runtime_hardening_migrate.py` 추가. 앱 startup 자동 migration 아님.
- `prepare_legacy_admin.py`는 DB004/005 exact 확인 → DB017 적용/재진입 확인 → legacy runtime ACL → restricted readback 순서로 변경.
- confirmation phrase: `APPLY_LEGACY_ADMIN_RUNTIME`.
- 고객 row 변경 없음. schema change는 DB017 function replacement만.
- 실제 production DB017/ACL 적용 및 feature ON은 아직 하지 않음.


### 체크포인트 5 / PR #91 병합 완료
- PR #91 최신 head `13555f4e61386a0fbd9f1aa29e69738c4ce7496a`에서 5개 CI 전부 PASS.
  - Login flow regression PASS
  - Same-domain login edge/image PASS
  - Portal UI synthetic PASS
  - Backend + disposable PostgreSQL PASS
  - Standalone admin preview PASS
- draft 해제 후 `feat/backend-portal-deploy`에 병합 완료.
- merge commit: `1752850e03a449550b343f755bae8a7de2dcf750`.
- production DB017 / legacy runtime ACL / monthly/manual feature는 아직 미적용.
- 다음 작업 단위: feature OFF 상태로 최신 merged code를 protected candidate에 code-only rollout.


### 체크포인트 6 / code-only rollout 진행 중
- PR #91 병합 후 merged admin/mypage/monthly/manual code를 feature OFF 상태로 protected candidate에 rollout 요청.
- request commit: `85d03b13eac458f7cfcae1f2710151c359d29363`.
- workflow run: `36609510020`.
- 현재 확인된 상태:
  - request PASS
  - Gcloud upload context / Docker build PASS
  - Python tests + disposable PostgreSQL PASS
  - `Roll out login handoff code to protected candidate` step 진행 중
- 이 rollout은 DB017 / legacy ACL / RICHON_MONTHLY_ENABLED / RICHON_MANUAL_ENABLED를 변경하지 않음.
- 다음 시작 지점: workflow run 36609510020 최종 결과와 새 candidate revision 확인.

### 체크포인트 7 / code-only rollout recovery 필요
- workflow run `36609510020`은 최종 failure.
  - request / Docker build / disposable PostgreSQL PASS.
  - rollout 중 `stale_request_commit`으로 중단.
  - 원인: rollout 실행 중 체크포인트 문서 커밋 `aa822e671cd39aba3bd11b53a58ffd005c29e701`가 같은 branch HEAD를 변경함.
- 동일 operation을 새 request commit `6cb539c796e6307325bb22c4e5cd97ac3c95e807` / run `36611612893`으로 재요청.
  - request / Docker build / disposable PostgreSQL PASS.
  - rollout은 `handoff_check_tag_already_exists`로 fail-closed.
- 해석:
  - 첫 run은 stale 검사 전에 0% 검증용 `portal-handoff-check` revision/tag 생성과 check URL gate probe까지 통과한 뒤, candidate tag switch 직전 stale HEAD 검사에서 중단된 상태.
  - 따라서 기존 `portal-candidate` 전환은 수행되지 않았고 default 100% serving traffic도 전환되지 않음.
  - 남은 `portal-handoff-check` 때문에 재시도가 의도적으로 차단됨.
- production DB017 / legacy runtime ACL / `RICHON_MONTHLY_ENABLED` / `RICHON_MANUAL_ENABLED`은 여전히 미적용.
- 다음 시작 지점:
  1. 고아 `portal-handoff-check`의 exact tag/revision/0% 상태와 보호 설정 불변을 read-only로 확인.
  2. 확인된 해당 check tag만 제거하는 narrow recovery를 수행.
  3. branch HEAD를 건드리지 않은 상태에서 code-only rollout 재요청/완료 확인.
  4. 그 뒤에만 DB017 / legacy runtime ACL 적용 준비로 이동.

### 체크포인트 8 / one-time recovery + code-only rollout 완료
- 사용자 결정: orphan check 문제는 재사용 자동복구 기능으로 일반화하지 않고 이번 1회만 narrow recovery.
- recovery 준비 전 no-cloud 검증:
  - portal automation guards PASS.
  - backend CI / Docker / disposable PostgreSQL PASS.
- 첫 recovery run `36613399632`은 write 전에 `recovery_unexpected_traffic_rows`로 fail-closed.
  - 원인: 기존 서비스에 candidate/check 외 다른 pre-existing 0% tag가 있었는데 recovery가 traffic row 총 3개를 가정함.
  - 실제 tag 제거/traffic 변경은 수행되지 않음.
- recovery guard를 수정해:
  - exact orphan `portal-handoff-check -> richon-portal-handoff-36609510020-1`만 대상으로 고정.
  - existing `portal-candidate -> richon-portal-handoff-36597611986-1` exact 확인.
  - default untagged 100% exact 확인.
  - 다른 기존 0% tag는 허용하되 before/after에서 그대로 보존되도록 검증.
- recovery run `36613781804` PASS.
  - removed tag: `portal-handoff-check` only.
  - old candidate unchanged: `richon-portal-handoff-36597611986-1`.
  - default 100% unchanged: `richon-portal-gh-35810692921-1`.
  - IAM/config unchanged PASS.
  - DB / feature flags untouched.
- code-only rollout run `36614094019` PASS.
  - rollout source: `fbb18da39014c202a1e228dc6b0eadb5d5bb39ce`.
  - image digest: `sha256:5f6cb7100b8be620bce812a048bb8e9109a2bc17ef91973cd22b7643fdd27048`.
  - old candidate: `richon-portal-handoff-36597611986-1`.
  - new protected candidate: `richon-portal-handoff-36614094019-1`.
  - `ACCOUNT=true / MARKETING=true / policy=member-info-v1` 유지.
  - default 100% serving revision: `richon-portal-gh-35810692921-1` 유지.
  - IAM / edge gate / Access gate PASS.
  - public homepage login entry unchanged.
- one-time recovery 코드/라우팅은 rollout 완료 후 다시 제거함.
  - `.github/portal/common.py`와 `.github/workflows/portal-deploy.yml`은 recovery 도입 전 blob으로 복원.
  - `login_handoff_recovery.py`, `test_login_handoff_recovery.py` 삭제.
  - cleanup 후 portal automation guards run `36614694988` PASS.
- production DB017 / legacy runtime ACL / `RICHON_MONTHLY_ENABLED` / `RICHON_MANUAL_ENABLED`은 여전히 미적용.
- 다음 시작 지점: DB017 + legacy runtime ACL 적용 전 운영 상태/owner helper 최종 확인 후 적용 단계.

### 체크포인트 9 / apply 복원 + 회사 Access + legacy enable 준비
- public PR #13은 원본 `marururu00/main` 병합 및 GitHub Pages 배포 SUCCESS.
- 사용자 확인: 현재 apply 페이지에 예전 상세 썸네일/강의 소개 갤러리가 누락됨.
- 정상 소스 재확인:
  - fork PR #59 / head `5830565ac11a66c9bcda905083ebede2be483d2e`에 기존 상세 강의 안내 이미지 49장 존재.
  - pre 1 / study 12 / redevelopment 11 / interior 15 / subscription 10.
- 복원 브랜치 `fix/apply-restore-details-20260930` 준비.
  - commit `0e17d871f7996d430b4482a67ab66408f52b1706`.
  - 현재 5개 과정 / 최신 모집상태와 CTA / 공개 로그인 숨김은 유지.
  - 메인 과정 썸네일 + PR #59 상세 갤러리 49장 복원.
  - 원본 upstream PR 생성은 사용자의 compare 화면 클릭이 필요.
- 회사 브라우저 로그인 모달 실패 원인 확정:
  - /auth/* /portal/*는 Cloudflare Access 보호 대상.
  - modal fetch는 redirect:error라 Access 세션 없는 새 브라우저의 Access 302를 의도적으로 fail-closed 처리.
  - 집 브라우저는 기존 Access 세션이 있어 통과 / 회사 브라우저는 별도 Access 인증 필요.
- PR #92: 새 브라우저 Access 필요 가능성을 설명하는 fallback UX로 수정, 4개 CI PASS 후 병합.
- PR #92 code-only rollout run `36656733191` PASS.
  - new candidate `richon-portal-handoff-36656733191-1`.
  - default 100% `richon-portal-gh-35810692921-1` unchanged.
  - IAM / edge gate / Access gate PASS.
- PR #93: monthly/manual을 항상 함께 OFF→ON하는 protected-candidate 전용 stage/inspect guard 추가.
  - partial flag 상태 fail-closed.
  - account/marketing/course=true 선행조건.
  - zero-traffic Ready 검증 후 portal-candidate tag만 전환.
  - DB/IAM/Secret/customer row/public homepage는 operation 범위 밖.
  - Portal guard / Login regression / Backend+PostgreSQL CI PASS 후 병합 완료.
  - merge commit `398160050fabeafedcba55a2c6d87b61ae4c699e`.
- production DB017 + legacy runtime ACL은 아직 미적용. Neon connector는 exact project_id가 없어 직접 접근 불가.
- 다음 시작 지점:
  1. 사용자: apply 복원 upstream PR 생성.
  2. 사용자 Cloud Shell: `prepare_legacy_admin.py --diagnose` read-only 결과 확인.
  3. diagnose PASS 후 DB017 + minimal ACL owner apply.
  4. stage-legacy-admin-enabled → inspect → /portal/enrollments, /portal/manual 실화면 확인.



### 체크포인트 10 / 로그인 Access 경계 전환 + legacy admin 활성화 완료
- 사용자 Cloud Shell 실행 결과 production Neon 준비 완료:
  - DB004=EXACT / DB005=EXACT / DB017=APPLIED.
  - LEGACY_ADMIN_RUNTIME_GRANTS=PASS.
  - RUNTIME_READBACK=PASS.
  - CUSTOMER_ROWS_CHANGED=NO.
  - Cloud Run/Worker 변경 없음.
- 이후 protected candidate의 monthly/manual 활성화 workflow run `36663921269` 전체 PASS.
  - 새 protected candidate: `richon-portal-legacy-36663921269-1`.
  - `RICHON_MONTHLY_ENABLED=true / RICHON_MANUAL_ENABLED=true`.
  - 이전 candidate: `richon-portal-handoff-36656733191-1`.
  - default 100% serving revision은 `richon-portal-gh-35810692921-1` 그대로 유지.
  - DB migration/customer row/IAM/Secret/default traffic 변경 없음.

#### 로그인 근본 원인 재정의
- 실제 외부 요청에서 `https://richonacademy.com/auth/login?... `이 Cloudflare Access 로그인으로 302 이동하는 것을 재현.
- 기존 자동화는 테스트 단계 정책에 맞춰 `/auth/*`, `/portal/*`의 Access 302를 정상으로 간주했음.
- 현재는 실제 회원 로그인 단계이므로 이 테스트용 Access 사전 인증이 고객용 OAuth/간편로그인과 충돌하는 상태로 판단.
- 출시용 경계 결정:
  - 고객 `/auth/*`, `/portal/*`는 Cloudflare Access 사전 인증 없이 Worker/application까지 도달해야 함.
  - Cloud Run direct origin은 기존 `X-Richon-Edge-Key` gate로 계속 보호.
  - 회원 API는 `require_member`, 관리자/월별/수동 API는 `require_admin` 유지.
  - write API Origin/CSRF, OAuth state/PKCE/cookie/provider allowlist 유지.
- Cloudflare 실제 Access application/policy는 아직 변경하지 않음. TinyFish 크레딧 없음으로 dashboard 자동점검은 사용하지 않기로 함.

#### PR #94 / 고객 로그인 경계 수정
- branch: `fix/public-auth-access-boundary-20260930`.
- PR: `#94 fix(login): release customer auth routes from Access gate`.
- 최신 head: `201365a9207af09a4d22401a60b98f17b93116a3`.
- 고객 fallback UX:
  - 기존 내부 문구 `테스트 접근 인증` / `접근 인증 후 로그인 화면 열기` 제거.
  - 새 문구: `로그인을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.`.
  - `다시 시도` 버튼으로 같은 modal에서 bootstrap 재요청.
  - Chromium에서 첫 modal 요청 503 → fallback 표시 → 다시 시도 → Kakao/Naver 버튼 복구 회귀 추가.
- 배포 가드 전환:
  - `/auth/login` 200 HTML 요구.
  - `/portal/mypage` 200 shell 요구.
  - Kakao/Naver 무효 callback은 same-origin `/auth/login?error=login_failed` 303 요구.
  - 실제 modal bootstrap `/auth/login?view=modal&return_to=/portal/mypage` 200 JSON + csrf/provider contract 요구.
  - Cloudflare Access redirect가 남으면 fail-closed.
  - origin edge-secret 403 검증은 별도로 유지.
- 첫 CI에서 옛 Access 기대값을 가진 automation test 4건이 깨졌으나 실제 기능 실패가 아니라 test expectation drift였음.
- 수정 후 최신 head 기준 5개 workflow 모두 PASS:
  - Same-domain login edge and portal image: run `36665172185` SUCCESS.
  - Portal automation guards: run `36665172165` SUCCESS.
  - Backend checks: run `36665172180` SUCCESS.
  - Portal UI synthetic: run `36665172164` SUCCESS.
  - Login flow regression: run `36665172404` SUCCESS.
- PR #94는 아직 병합하지 않음. Cloudflare Access 설정도 아직 변경하지 않음.

#### 다음 시작 지점
1. PR #94 최신 diff/CI 최종 확인 후 병합.
2. 병합 뒤 protected candidate에 새 login/route-guard code rollout.
3. Cloudflare Zero Trust에서 고객용 `/auth/*`, `/portal/*`의 기존 테스트용 Access 사전 인증을 가장 좁은 공개 예외/Bypass 방식으로 해제. 다른 WAF/BIC/Worker route/origin edge-key는 유지.
4. 외부 무인증 readback에서 Access 302가 사라지고 새 customer-route probe가 PASS하는지 확인.
5. 사용자 브라우저에서 마이페이지 → 간편로그인 modal → Kakao/Naver 실제 E2E 확인.
6. 로그인 정상화 후 관리자 화면 확인 → 실제 회원 수강권 1개 부여 → 해당 회원 마이페이지 `내 강의` 확인 순서로 재개.


### 체크포인트 11 / Access 제거·마이페이지 3열·운영데이터 진단 준비
- Cloudflare Zero Trust에서 테스트용 Access application 2개(/auth/*, /portal/*) 삭제 완료.
- 실제 사용자 브라우저에서 로그인 정상 동작 확인.
- 외부 read-only customer-route 검증 PASS:
  - /auth/login = 200
  - /auth/kakao/callback = 303
  - /auth/naver/callback = 303
  - /portal/mypage = 200
  - login modal bootstrap = 200
  - Access redirect 없음
- PR #94 병합 완료: 고객용 로그인 fallback을 범용 문구 + 다시 시도로 변경하고, 배포 가드를 Access 302 기대에서 customer-route 정상응답 기대 방식으로 전환.
- PR #95 병합/배포 완료:
  - 내 정보 6개 항목 = 데스크톱 3열 x 2행.
  - 광고성 정보 / 로그인 연결 = 같은 관리행 2칸.
  - 모바일은 1열.
  - protected candidate rollout run 36669194473 PASS.
  - new candidate = richon-portal-handoff-36669194473-1.
  - default 100% serving traffic / IAM / Secret / 기존 feature config 불변.
- post-rollout inspect run 36669561980 PASS.
  - LEGACY ADMIN INSPECT PASSED.
  - DB/IAM/secret/customer write 없음.
  - monthly/manual 활성 상태 보존 확인.
- 관리자/마이페이지 1~7 중:
  - 1 월별/수동 404 해결 및 ON = 완료
  - 2 관리자 UI family 통합 = 완료
  - 3 withdrawn 회원 total 제외 = 완료
  - 4 회원 상세 강의/수강권/주문 = 완료
  - 5 마이페이지 정보 밀도 = 완료
  - 6 로그인 연결 UX 통합 = 완료
  - 7 production DB 실제 데이터 경계 확인 = 다음 단계
- PR #96 병합 완료.
  - aggregate-only production data helper ops/diagnose_production_data.py 추가.
  - 회원/주문/legacy/canonical course 관련 숫자 집계만 출력.
  - 고객 row/이름/전화/이메일/ID/OAuth subject/DSN/secret 출력 금지.
  - DB read_only SELECT 집계만 허용.
  - 수정 후 CI 전부 PASS.
  - 이 helper 병합 자체로 production DB/Cloud Run 변경 없음.
- portal-deploy.request는 hold로 복귀.

#### 헤더/회원가입 안내 후속 결정
- 랜딩이 아닌 기능 페이지에서 후기 / 정규 프로그램 / 강사·멘토 앵커 메뉴는 제거하는 방향.
- index.html 랜딩만 기존 3개 메뉴 유지.
- 기능 페이지는 로고 / 오픈카톡 / 강의 신청 / 로그인·마이페이지 중심으로 단순화.
- signup-guide.html은 2026-09-28 Kakao 심사용 회원가입 절차/수집항목/CI 증빙 페이지로 생성된 것 확인.
- Kakao CI 심사 완료 전 URL은 유지하되, 일반 사용자 푸터 메뉴에서는 숨기는 방향 검토.
- 헤더 정리는 다음 별도 PR 단위로 처리.

#### 다음 시작 지점
1. Cloud Shell에서 ops/diagnose_production_data.py를 production 대상으로 read-only 실행하고 COUNTS 결과만 확인.
2. 실제 0건인지 / DB에는 있는데 UI가 빈지 판정.
3. 필요 시 실제 회원 1명에 canonical 수강권 1개 부여(이 단계는 customer-row write이므로 실행 직전 사용자 확인).
4. 해당 회원 마이페이지 내 강의 확인.
5. 기능페이지 헤더 단순화 + signup-guide 푸터 노출 정리 별도 PR.


### 체크포인트 12 / production inventory Cloud Shell TLS 보정
- ops/diagnose_production_data.py 첫 실행:
  - venv + psycopg[binary]: owner_tls_verification_failed
  - system Python: owner_connection_failed_unknown
  - 둘 다 secret-access 단계에서 중단되어 customer row 조회/DB write 없음.
- production DB/Secret 자체 문제로 단정하지 않고 Cloud Shell Python/psycopg/libpq/CA 경계 차이로 범위를 축소.
- 보안 결정:
  - sslmode=verify-full 유지.
  - sslmode=require/disable로 완화하지 않음.
  - production app backend/db.py는 변경하지 않음.
  - 진단 helper만 Python system CA의 실제 파일 경로를 sslrootcert로 명시하도록 보정.
- PR #97 생성:
  - branch: fix/production-diagnostic-cloudshell-tls-20260930
  - head: e2cf69315ccd5b4cb13598adda4eae20aa7e1c3f
  - Cloud Shell diagnostic 전용 connect() 추가.
  - psycopg 미설치 시 psycopg_missing safe code.
  - full TLS verification 유지 테스트 추가.
  - 고객 row/식별자 출력 및 DB/Cloud write 없음.
- PR #97 CI는 생성 직후 아직 run 목록이 잡히기 전 상태에서 체크포인트 저장.
- 다음 시작 지점:
  1. PR #97 CI 결과 확인.
  2. PASS면 병합.
  3. 병합 commit으로 Cloud Shell venv 재실행.
  4. COUNTS 집계로 production data boundary 판정.


### 체크포인트 13 / PR #97 병합
- PR #97 CI 3개 PASS:
  - Same-domain login edge and portal image
  - Login flow regression
  - Backend checks
- PR #97 병합 완료.
- merge commit: bd4eb0050e366d8128b3f9e1c2ed7a17156614c4
- 변경 범위는 Cloud Shell production aggregate inventory의 TLS CA 경로 보정만.
- sslmode=verify-full 유지 / production app backend/db.py 불변 / DB·Cloud write 없음.
- 다음 시작 지점: merge commit 기준 Cloud Shell에서 ops/diagnose_production_data.py 재실행 후 COUNTS 판정.


### 체크포인트 14 / production inventory gcloud 오류 분류
- production aggregate inventory 재실행 결과:
  - STOP: cloud-target / command_failed
  - DB 연결/secret-access/aggregate read 단계 진입 전 중단.
  - customer row 조회/DB write 없음.
- generic command_failed로는 정확한 실패 지점을 알 수 없어 helper 진단을 세분화.
- PR #98 생성:
  - branch: fix/production-diagnostic-gcloud-errors-20260930
  - head: 107f82916c5742a3444f199f16187fc256fad00b
  - safe code:
    - project_describe_failed
    - owner_service_describe_failed
    - portal_service_describe_failed
    - owner_secret_access_failed
    - runtime_secret_access_failed
  - gcloud stdout/stderr/Secret/DSN은 출력하지 않음.
  - 기존 sslmode=verify-full + explicit system CA file 유지.
  - production app backend/db.py 불변.
- PR #98 생성 직후라 CI run 목록은 아직 비어 있는 상태에서 체크포인트 저장.
- 다음 시작 지점:
  1. PR #98 CI 확인.
  2. PASS면 병합.
  3. 병합 SHA로 Cloud Shell 재실행.
  4. safe code로 cloud-target 실패 지점을 확정.
