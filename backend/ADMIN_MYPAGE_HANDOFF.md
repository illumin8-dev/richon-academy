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


### 체크포인트 15 / PR #98 병합
- PR #98 CI 3개 PASS.
- PR #98 병합 완료.
- merge commit: 5d4422e15bdf7172adccf0f2c6e50c08d090153c
- 다음: merge commit 기준 Cloud Shell에서 production aggregate inventory 재실행.
- 기대 결과는 성공 시 COUNTS, 실패 시 세분화된 safe code 중 하나.


### 체크포인트 16 / Pre리치온 9기 program/run 생성 준비
- production aggregate inventory PASS:
  - course_domain program/run/session/enrollment = 0
  - legacy monthly/manual = 0
  - active member 1 / active admin 1
  - Naver identity 1 / Kakao identity 0
  - orders 2 / pending 2 / linked 0
- 공개 기능페이지 헤더 PR #100 병합 완료.
- 포털 기능페이지 헤더 PR #99 병합 및 protected candidate rollout 성공.
- 공개 랜딩 실제 calendar markup/JS는 이미 없었고 dead .cal-* CSS만 존재:
  - PR #102 CI PASS 후 병합 완료.
  - 향후 일정은 관리자 중앙관리 캘린더에서 관리.
- Pre리치온 운영 기준:
  - 9기
  - 기본 시작일 2026-10-08
  - fixed 2 months
  - access/run boundary 2026-10-08 ~ 2026-12-07
  - price 176000 KRW
  - sessions는 지금 생성하지 않음
  - 8주차 현장 임장 포함 일정은 추후 관리자 중앙 캘린더에서 입력
- PR #103 생성/검증/병합:
  - owner-only helper ops/create_pre_richon_9.py
  - course_programs + course_runs + course_domain_audit만 write
  - course_sessions/course_enrollments/enrollment_learners/members/orders/payment write 없음
  - DB015/016 checksum, production target, TLS verify-full, active admin exactly-one 검증
  - 한 transaction + advisory lock
  - exact replay NO-OP / conflict overwrite 금지
  - CI 3개 PASS / mergeable clean
  - merge commit: effa2e25825a9118485da8d2ac5751e7ef6c080f
- 다음 시작 지점:
  1. Cloud Shell에서 merge commit 기준 create_pre_richon_9.py 실행.
  2. interactive confirmation CREATE_PRE_RICHON_9 입력.
  3. PROGRAM/RUN 생성 + SESSIONS=0/ENROLLMENTS=0 readback 확인.
  4. 이후 관리자 course 화면에서 9기 표시 확인.
  5. 중앙관리 캘린더 설계/구현은 별도 단계.


### 체크포인트 17 / Pre리치온 9기 production 생성 완료
- 사용자 Cloud Shell 실행 결과:
  - TARGET=richon-academy / production Neon / Pre리치온 9기
  - TLS_MODE=verify-full / TLS_CA=system-file
  - PROGRAM=CREATED
  - RUN=CREATED
  - SESSIONS=0 / ENROLLMENTS=0
  - PRE_RICHON_9=PASS
  - MEMBER_ROWS_CHANGED=NO / ORDERS_CHANGED=NO / CLOUD_CHANGED=NO
- production canonical course state:
  - program: Pre리치온 (프리리치온)
  - cohort: Pre리치온 9기
  - access/run boundary: 2026-10-08 ~ 2026-12-07
  - price: 176000 KRW
  - schedule/session data: intentionally empty
- 다음:
  1. 관리자 강의관리 UI에서 프로그램/9기 노출 확인.
  2. 중앙관리 캘린더는 별도 기능으로 설계/구현.
  3. 일정은 중앙관리 캘린더에서 입력되어 course_sessions에 저장되는 구조로 연결.


### 체크포인트 18 / 중앙 캘린더 경계 배포 완료
- PR #104 CI 4개 PASS / mergeable clean / 병합 완료.
- 관리자 /portal/courses:
  - 프로그램/기수 기본정보 관리 유지
  - 수강권 지급/현황 유지
  - 회차/시간/영상/자료 직접 입력 UI 제거
  - 중앙관리 캘린더에서 일괄 관리 예정 안내로 대체
  - course_sessions DB/API 자체는 유지
- protected candidate rollout run 36684483088 PASS.
- source: ce683a9c2afa0a8cf37075129359b1f0de094d1e
- image digest: sha256:2c4a5117ff1a78c0ac34a76918451c825869a39eda7fd8d201f94c95c0c7fa53
- old candidate: richon-portal-handoff-36681481162-1
- new candidate: richon-portal-handoff-36684483088-1
- default 100% unchanged: richon-portal-gh-35810692921-1
- IAM/edge/access checks PASS.
- deploy request returned to hold.
- production Pre리치온 9기 already exists:
  - program/run only
  - sessions=0 / enrollments=0
- next:
  1. decide/implement central admin calendar later.
  2. if desired, grant a member enrollment separately with explicit row-write approval.
  3. verify My Courses after an enrollment exists.


### 체크포인트 19 / 관리자 계정 수강권 지급 helper 준비
- PR #105 CI 3개 PASS / mergeable clean / 병합 완료.
- merge commit: c120e81ef0078789c57649e0334b77e3a94059a5
- helper: ops/grant_pre_richon_9_admin.py
- 아직 production write 실행 안 함.
- 실행 시 write 범위:
  - enrollment_learners: sole active admin의 member-linked learner가 없을 때만 +1
  - course_enrollments: Pre리치온 9기 +1
  - course_domain_audit: +1
- 변경 금지:
  - members / member_profiles
  - orders / payment / member_order_links
  - course_sessions
  - legacy monthly/manual
  - Cloud Run / IAM / feature flags
- exact replay NO-OP / conflict overwrite 금지 / customer identifier 출력 금지.
- 실제 실행 직전 사용자 승인 필요.


### 체크포인트 20 / Pre리치온 9기 관리자 수강권 production 지급 완료
- 사용자 Cloud Shell 실행 결과:
  - TARGET=richon-academy / production Neon / Pre리치온 9기 admin enrollment
  - TLS_MODE=verify-full / TLS_CA=system-file
  - LEARNER_LINK=CREATED
  - ENROLLMENT=CREATED
  - SESSIONS=0
  - PRE_RICHON_9_ADMIN_ENROLLMENT=PASS
  - MEMBER_PROFILE_CHANGED=NO / ORDERS_CHANGED=NO / CLOUD_CHANGED=NO
- expected My Courses:
  - sole active admin member has member-linked enrollment for Pre리치온 9기
  - access 2026-10-08 ~ 2026-12-07
  - current status before start date should resolve to SCHEDULED
  - sessions array intentionally empty until central admin calendar is implemented.
- next: inspect actual mypage course rendering and verify production UI.


### 체크포인트 21 / production 내 강의 end-to-end 검증 완료
- 사용자 실제 production 화면 확인 완료.
- /portal/mypage -> 내 강의에서 Pre리치온 9기 정상 노출 확인.
- production data path end-to-end PASS:
  - course_programs -> course_runs -> enrollment_learners -> course_enrollments -> /portal/api/me/courses -> 마이페이지 렌더링
- 현재 sessions=0이므로 회차/영상/자료 영역 미노출이 정상.
- admin/mypage/course-domain 기본 흐름 검증 완료.
- 다음 큰 기능은 중앙관리 캘린더:
  - 일정/회차/영상/자료의 단일 입력 지점
  - course_sessions를 중앙 캘린더가 소유
  - /portal/courses에서는 일정 직접 입력 금지 유지


### 체크포인트 22 / 관리자 UI 정리 중단 지점
- 사용자 실제 화면 피드백:
  - 회원 목록 이름 아래 내부 member UUID가 노출되어 불필요함.
  - 회원 상세 dialog가 "회원 상세를 불러오지 못했습니다."로 실패.
  - 신청·주문 / 회원 관리 메뉴가 관리자 페이지별로 다르게 보임.
  - 관리자 페이지 header/footer가 공용화되지 않고 page-specific topbar/sidebar가 남아 있음.
  - 조회 버전 / PG 미연결 / 별도 집계 / 정확한 기록 / 이 화면에서는... 같은 개발단계 TMI 문구가 과다함.
- 확인 결과:
  - member UUID는 backend/portal_static/portal.js의 memberPrimary()가 직접 렌더링 중.
  - /portal/admin에서는 신청·주문 / 회원 관리가 내부 tab button이고, courses/enrollments/manual에서는 "회원 / 신청·주문" 단일 링크라 navigation drift 존재.
  - mypage는 shared site header/footer 사용하지만 admin pages는 별도 topbar/sidebar 구조.
  - Worker는 /portal/api/admin/members/{uuid} 같은 동적 경로를 허용하므로 상세 실패 원인은 edge allowlist 문제 아님.
  - member_detail backend는 profile + marketing + canonical learning + legacy learning + orders를 한 번에 조합하며 이 production 조합에 대한 회귀 테스트가 부족했음.
- branch: fix/admin-shell-detail-cleanup-20261001
- PR #106: fix(admin): unify shell, trim UI noise and cover member detail
- PR #106 head: b9f43eef41c7ee8f0e0b5210fb78335804e8e7a4
- PR #106 상태 저장 시점:
  - mergeable=true / mergeable_state=unstable
  - Backend checks: in_progress
  - standalone admin preview: in_progress
  - Portal UI checks: in_progress
  - Login flow regression: in_progress
  - Same-domain login edge/image: in_progress
- PR #106에 반영한 내용:
  - frontend/shared/admin-header.html 추가
  - frontend/shared/admin-sidebar.html 추가
  - frontend/shared/admin-footer.html 추가
  - tools/build_site_shell.py가 admin.html/courses.html/enrollments.html/manual.html의 shared admin shell을 렌더링하도록 확장
  - 모든 관리자 페이지 sidebar에 동일하게:
    - 강의 / 수강권
    - 월별 수강관리
    - 수강생 수동 등록 / 수정
    - 신청·주문
    - 회원 관리
    - 마이페이지
  - /portal/admin?tab=orders|members 직접 진입 지원
  - 회원 목록의 raw member UUID 노출 제거
  - admin/courses/enrollments/manual의 반복 TMI 문구 축소
  - 공용 최소 admin footer 추가
  - shared admin shell drift 회귀 테스트 추가
  - member_detail + canonical enrollment + legacy enabled 조합의 disposable PostgreSQL 회귀 테스트 추가
- 아직 하지 않은 것:
  - PR #106 CI 결과 확인 / 실패 시 수정 / 병합
  - PR #106 protected candidate rollout
  - production 회원 상세 실제 재확인
  - 회원 상세 실패의 실제 원인 확정(새 회귀 테스트 결과를 먼저 봐야 함)
- 공개 원본 동기화 별도 진행 상태:
  - fork branch: fix/upstream-public-ui-sync-20260930
  - 원본 marururu00/main SHA eb77ee61cd365660e6d3ef9c75751d6cc02cf12a에서 직접 분기
  - 원본 대비 5개 파일만 변경:
    - apply.html: 랜딩 메뉴/햄버거/회원가입 안내 링크 제거, 상세 갤러리 유지
    - signup-guide.html: 랜딩 메뉴/햄버거/회원가입 안내 링크 제거, 페이지 자체 유지
    - index.html: dead calendar CSS + 회원가입 안내 링크 제거, 랜딩 메뉴 유지
    - frontend/shared/footer.html: 회원가입 안내 링크 제거
    - tools/check_public_ui.py: 새 계약으로 갱신
  - compare result: ahead 5 / behind 0
  - 두 GitHub 연결 모두 원본 PR create API가 403 Resource not accessible by integration
  - 사용자가 compare 페이지에서 수동 Create pull request 해야 함:
    https://github.com/marururu00/richon-academy/compare/main...illumin8-dev:fix/upstream-public-ui-sync-20260930?expand=1
  - 제안 PR title: fix(ui): sync public functional navigation cleanup
- 다음 시작 지점:
  1. PR #106 CI 결과 확인.
  2. 실패 시 해당 job log만 확인해 수정.
  3. PASS면 병합.
  4. protected candidate code-only rollout.
  5. 사용자 production admin에서 UUID 제거 / sidebar 통일 / TMI 정리 / 회원 상세 재확인.
  6. 회원 상세가 계속 실패하면 production-safe diagnostic helper로 상세 경로를 row 출력 없이 분리 진단.
  7. 별도 공개 원본 PR 번호가 생기면 CI 확인 후 병합 준비.


### 체크포인트 23 / PR #106 수정 후 CI 진행 + CSS 구조 파악
- 사용자 요청으로 timeout 방지를 위해 이 지점에서 중단.
- PR #106: fix(admin): unify shell, trim UI noise and cover member detail
- branch: fix/admin-shell-detail-cleanup-20261001
- latest head: 1ce5771810c1704956c508f3f66b231096c6d6e4
- 첫 CI에서 실제 원인 발견:
  1. 회원 상세 실패 실제 원인:
     - backend/portal_store.py member_detail()가 _rows(cur)를 호출하지만 _rows가 정의되지 않아 NameError.
     - production 화면의 "회원 상세를 불러오지 못했습니다."와 일치하는 실제 backend bug.
  2. 중앙 캘린더 안내 문구를 간소화했는데 옛 exact-copy 테스트가 이전 문구를 요구.
  3. admin browser가 기존 [data-tab] button 구조를 기대했으나 shared sidebar의 [data-admin-tab-link] link 구조로 변경됨.
  4. standalone manual preview는 공용 admin header 적용 후 제거된 #identity 요소를 manual.js가 계속 참조하여 JS boot 중단.
- 위 4개 모두 수정 완료:
  - portal_store.py에 _rows(cur) 추가.
  - course admin calendar boundary test를 간결 문구 기준으로 수정.
  - portal_browser.py를 data-admin-tab-link 기준으로 변경.
  - manual.js에서 page-specific #identity 의존 제거.
- 현재 PR #106 CI 상태 마지막 확인:
  - Same-domain login edge/image = PASS
  - Login flow regression = PASS
  - Backend checks = PASS
  - Standalone admin preview = PASS
  - Portal UI checks = 아직 in_progress (Playwright install/test 대기 중)
  - mergeable=true / mergeable_state=unstable (마지막 UI job 미완료 때문)
- PR #106 UI 변경 범위:
  - raw member UUID 목록 노출 제거
  - 관리자 4페이지 공용 admin header/sidebar/footer source 추가
  - 모든 관리자 sidebar 메뉴 통일:
    강의 / 수강권, 월별 수강관리, 수강생 수동 등록 / 수정, 신청·주문, 회원 관리, 마이페이지
  - /portal/admin?tab=orders|members 직접 진입 지원
  - 개발단계 TMI 문구 대폭 축소
  - shared admin shell drift test 추가
  - production과 유사한 canonical enrollment + legacy ON member_detail PostgreSQL 회귀 테스트 추가
- CSS / main / portal 구조 파악:
  - 현재 전체 사이트 CSS는 단일 정본이 아님.
  - public main:
    - frontend/shared/site.css
    - assets/hero/home-hero.css
    - index.html의 큰 inline <style>
    - apply.html의 inline <style>
  - portal 회원/로그인:
    - backend/portal_static/site.css (frontend/shared/site.css에서 build)
    - account.css / auth.css
  - portal 관리자:
    - ops.css 공통 base/token
    - portal.css 공통 admin layout/components
    - courses.css / enrollments.css / manual.css 페이지별 CSS
  - 같은 경로 frontend/shared/site.css도 main과 feat/backend-portal-deploy 내용이 이미 다름:
    - main site.css blob sha c4d06dc3...
    - portal branch site.css blob sha 6e721829...
  - header.html도 main과 portal branch가 다르고 footer만 현재 동일.
  - 즉 "shared" 이름은 쓰지만 main/public과 portal이 branch 단위로 갈라져 있어 진짜 single source of truth는 아님.
- CSS 정리 권장 최종 방향:
  1. 전 사이트 공통 design tokens + logo/header/footer + button/form base를 하나의 shared core로 만든다.
  2. admin은 sidebar/table/filter/dialog만 admin layer로 둔다.
  3. page-specific CSS는 실제 고유 레이아웃만 남긴다.
  4. index/apply inline CSS는 별도 파일로 추출해 공통/페이지 전용 경계를 명확히 한다.
  5. main/public과 portal branch의 frontend/shared를 eventually 하나의 authoritative source로 합친다.
- 이 CSS 전체 리팩터링은 PR #106에 섞지 않음. 공개 main까지 영향 범위가 커 별도 PR/작업으로 진행.
- 공개 원본 동기화 별도 브랜치:
  - fix/upstream-public-ui-sync-20260930
  - original main 대비 ahead 5 / behind 0
  - 원본 PR 생성 API는 403이라 사용자가 compare 페이지에서 수동 PR 생성 필요.
- 다음 시작 지점:
  1. PR #106 Portal UI checks 최종 결과 확인.
  2. PASS면 PR #106 병합.
  3. protected candidate code-only rollout.
  4. 사용자 실제 admin 화면에서 UUID 제거 / 메뉴 통일 / TMI 정리 / 회원 상세 정상 동작 확인.
  5. 그 다음 별도 작업으로 main+portal CSS/shared source 통합 계획을 구체화하고 PR 진행.


### 체크포인트 24 / PR #106 병합·배포 완료
- PR #106 CI 5개 전부 PASS 후 병합 완료.
- merge commit: c4aeb85a77d6e5b717de9c7ae0e1eceb8621fde3
- 실제 회원 상세 실패 원인 수정:
  - portal_store.member_detail()에서 사용하던 _rows(cur)가 정의되지 않아 NameError 발생.
  - portal_store.py에 _rows helper 추가.
  - canonical enrollment + legacy ON 조합의 disposable PostgreSQL 회귀 테스트 PASS.
- 관리자 UI:
  - 회원 목록 raw member UUID 제거.
  - 관리자 4페이지 shared admin header/sidebar/footer source 사용.
  - 신청·주문 / 회원 관리 메뉴를 모든 관리자 페이지에서 동일하게 분리 노출.
  - /portal/admin?tab=orders|members 지원.
  - 반복 TMI 문구 축소.
  - manual.js의 제거된 #identity header 의존 제거.
- rollout 첫 시도 run 36738579206:
  - 모든 code/build/db checks PASS.
  - live preflight에서 /auth/login만 Cloudflare 520 1회 발생.
  - handoff_customer_routes_not_confirmed로 candidate 변경 전 fail-closed.
  - 다른 live routes는 callback 303 / mypage 200 / public 200 / modal 200 정상.
- 새 request id로 동일 rollout 재시도 run 36739145776.
- 재시도 PASS:
  - LOGIN HANDOFF CANDIDATE ROLLOUT=PASS
  - source=6f64c4ec1b88f5efac4160c75e3a14b159286d7a
  - image digest=sha256:2c81d11fae1c4275f584c0669f6989924a8a1018ec43a4a14f4949a3ade5b975
  - old candidate=richon-portal-handoff-36684483088-1
  - new candidate=richon-portal-handoff-36739145776-1
  - default 100%=richon-portal-gh-35810692921-1 unchanged
  - IAM / EDGE_GATE / ACCESS_GATE PASS
- deploy request hold 복귀.
- 사용자 실제 확인 필요:
  1. 회원 목록 UUID 제거
  2. 회원 상세 정상 오픈
  3. sidebar 메뉴 동일
  4. TMI 정리 체감 확인
- CSS architecture:
  - 아직 site-wide single source가 아님.
  - public main / portal member-auth / portal admin의 3 layer로 분리.
  - main과 portal branch의 frontend/shared/site.css/header.html도 서로 drift 중.
  - 별도 CSS consolidation PR 필요.


### 체크포인트 25 / 운영 정본 이전 결정 + 남은 전체 로드맵
- 사용자 실화면 확인 완료:
  - 관리자 UUID 제거 확인
  - 회원 상세 정상 동작 확인
  - 신청·주문 / 회원 관리 메뉴 통일 확인
  - TMI 문구 축소 확인
  - 관리자 페이지별 여백 차이는 존재하나 CSS 통합 단계에서 같이 정리하기로 결정
- 소스/호스팅 전략 최종 결정:
  - 현재 public 운영 소스는 marururu00/richon-academy main + Cloudflare Pages.
  - portal/backend 정본은 illumin8-dev/richon-academy feat/backend-portal-deploy.
  - GPT의 marururu00 write 접근 제약 때문에 public/portal이 계속 갈라지는 구조가 비효율적.
  - 앞으로 illumin8-dev/richon-academy를 유일한 운영 정본으로 만들기로 결정.
  - 이후 필요 시 최초 frontend 개발자에게 illumin8-dev repo 권한을 역으로 부여.
  - marururu00 repo는 당분간 과거 frontend 원본/백업으로 보존.
- 중요한 Cloudflare 구분:
  - 삭제한 것은 Cloudflare Access의 /auth/*, /portal/* 사전 인증 application 2개.
  - /auth/*, /portal/* 실제 route는 삭제되지 않았고 Worker -> Cloud Run portal로 현재도 동작.
  - repo/Pages 이전 시 Worker route는 유지해야 함.
- main / portal divergence:
  - portal branch는 fork main 대비 약 701 commits ahead / 131 behind.
  - 양쪽에서 동시에 수정된 실제 overlap file은 4개:
    1. frontend/shared/header.html
    2. frontend/shared/footer.html
    3. frontend/shared/site.css
    4. frontend/shared/site.js
  - 최신 original marururu00/main SHA 확인 당시: 0e6567655bcf56f9dbb5ad73e6582f3a73c7cfe4
  - 최신 public main에만 있고 portal branch에 없는 파일은 hero/apply gallery/images/public workflow/signup-guide 등 다수.
- PR #107:
  - integration: merge portal codebase into unified main line
  - draft exploratory PR
  - mergeable=false / dirty
  - 이 PR을 그대로 병합하지 않음.
  - 통합 구조/충돌 범위 확인용으로만 사용.
- repo 통합 최종 방법:
  1. illumin8-dev 쪽에 통합 브랜치 생성.
  2. portal/backend/auth/admin/edge/ops/workflow 전체 보존.
  3. 최신 marururu00/main 공개 페이지/assets/public CI를 그대로 가져옴.
  4. shared overlap 4개는 명시적으로 재구성.
  5. portal deploy branch hardcode(feat/backend-portal-deploy)를 main authority로 이전:
     - .github/workflows/portal-deploy.yml
     - .github/portal/common.py
     - 관련 branch/ref guard/test
  6. public CI + backend CI + portal UI/login/edge CI 모두 통과.
  7. illumin8-dev/main을 새 단일 정본으로 확정.
- Cloudflare Pages 이전 안전 순서:
  1. 기존 marururu00 Pages + richonacademy.com은 그대로 유지.
  2. 새 Cloudflare Pages project를 illumin8-dev/richon-academy main에 연결.
  3. 새 *.pages.dev 주소에서 공개 랜딩/apply/images/privacy/terms/signup-guide/mobile 전체 확인.
  4. /auth/*, /portal/* Worker routes가 새 Pages와 공존하면서 정상 동작하는지 확인.
  5. 마지막에 richonacademy.com custom domain만 새 Pages project로 cutover.
  6. 기존 marururu00 Pages project는 즉시 삭제하지 않고 rollback 여유 확보 후 정리.
- CSS/UX 통합은 repo/hosting 통합 후 별도 단계:
  - 지금 site-wide CSS single source가 아님.
  - public main:
    - frontend/shared/site.css
    - assets/hero/home-hero.css
    - index.html inline <style>
    - apply.html inline <style>
  - portal member/auth:
    - site.css + account.css / auth.css
  - portal admin:
    - ops.css + portal.css + courses.css / enrollments.css / manual.css
  - 목표:
    - 전체 사이트 공통 tokens/base/header/footer/buttons/forms를 하나의 authoritative source로 통합
    - admin은 sidebar/table/filter/dialog만 admin layer
    - account/auth와 public은 page-specific 부분만 남김
    - index/apply inline CSS를 외부 파일로 추출
    - 같은 단위(버튼/input/panel/spacing 등)는 사이트 전체 규칙 통일
    - 관리자 페이지별 여백 차이도 이 단계에서 통일
- 카카오 / 네이버 현재 남은 상태:
  - 공통:
    - 실제 /auth/* /portal/* customer route는 Access 사전 인증 없이 정상 동작하도록 전환 완료.
    - 회원 로그인/마이페이지/계정 연결 코드와 production path는 구현됨.
  - Naver:
    - production aggregate에서 Naver identity 1건 확인됨.
    - 실제 Naver 로그인 기술 E2E는 동작한 증거가 있음.
    - 일반 이용자 공개용 Naver 검수 신청/승인 완료 증거는 저장소에 없음.
    - 따라서 platform 검수 신청/승인 상태는 별도 수동 확인 필요.
  - Kakao:
    - Kakao CI 개인정보 동의항목 재심사용 문서/회원가입 화면/CI 사용 사유 자료는 준비됨.
    - 과거 반려 사유에 맞춰 가입 절차, 필수/선택 항목, CI 처리 설명 보강함.
    - production aggregate에서는 Kakao identity 0건.
    - Kakao CI 추가 동의항목 재심사 실제 제출/승인 완료 증거는 저장소에 없음.
    - 따라서 재심사 제출 여부/결과는 Kakao Developers 콘솔에서 수동 확인 필요.
    - 심사 완료 전 signup-guide.html URL은 유지하되 일반 사용자 footer 노출은 숨기는 방향.
  - provider 후속:
    - 플랫폼 심사/실사용 과정에서 요구되면 외부 provider unlink/account-state webhook 범위는 별도 검토.
- 중앙관리 캘린더:
  - 아직 구현하지 않음.
  - public calendar는 제거.
  - /portal/courses의 직접 session 입력 UI도 제거.
  - course_sessions DB/API는 유지.
  - 현재 Pre리치온 9기 sessions=0.
  - 향후 중앙 관리자 캘린더가 회차/일시/영상/자료를 단일 입력 지점으로 소유.
  - 범위 확장 후보: 강의 / 특강 / 브리핑 / 임장 / 기타 운영 일정.
- 강의/수강권:
  - Pre리치온 9기 program/run production 생성 완료.
  - 기간 2026-10-08 ~ 2026-12-07 / 가격 176000.
  - 관리자 계정 수강권 production 지급 및 마이페이지 내 강의 E2E 확인 완료.
  - 실제 수강생 운영은 real member 대상으로 검색 -> 수강권 지급 -> 관리자 현황 -> 학생 마이페이지 흐름을 운영하면서 UX 보완 가능.
- 결제:
  - 의도적으로 뒤로 미룸.
  - production aggregate 당시 orders total 2 / pending 2 / linked 0.
  - PG 미연결.
  - 이후 신청 -> 결제 -> 회원 연결 -> 자동 수강권 지급 흐름으로 연결 필요.
  - PortOne / StepPay / 토스 등 PG 결정도 후속.
- 기타 후속:
  - 오래된 superseded open PR 정리 필요 (#101/#86/#72/#59/#48/#43/#25/#10 등).
  - public upstream 임시 sync 브랜치 fix/upstream-public-ui-sync-20260930은 새 정본 이전으로 대체될 예정.
- 최종 안전 우선순위:
  A. illumin8-dev/main 단일 코드베이스 통합
  B. 새 Cloudflare Pages를 illumin8-dev/main에 연결하고 pages.dev 검증
  C. richonacademy.com cutover + auth/portal route 재검증
  D. 전체 사이트 CSS/shared source 통합
  E. Kakao CI 재심사 / Naver 일반 공개 검수 상태 확인 및 필요 시 제출
  F. 중앙관리 캘린더 구현
  G. 실제 수강생 운영 UX 보완
  H. 결제/PG 연결
  I. 오래된 PR/임시 브랜치 정리
- 다음 대화 시작 지점:
  - A 단계부터 진행.
  - PR #107은 병합하지 말고 exploratory 상태로 유지/필요 시 닫기.
  - 최신 marururu00/main public files/assets를 portal/backend 통합 브랜치에 가져오고,
    deployment authority를 main으로 옮기는 통합 계획/구현부터 시작.



### 체크포인트 26 / public + portal 단일 main 통합 PR #108 진행 중
- 이번 대화 최우선 목표:
  - marururu00/richon-academy 최신 public main과 illumin8-dev/richon-academy portal/backend를 illumin8-dev/main 단일 운영 정본으로 통합.
  - 기존 Cloudflare Pages / richonacademy.com 운영 연결은 아직 변경하지 않음.
- 기준 소스 재확인:
  - 최신 upstream public main: `0e6567655bcf56f9dbb5ad73e6582f3a73c7cfe4`
  - 최신 portal/backend authority: `79e8efb03a97ae0d81c3e431aec599f9c5533bf7`
  - 기존 illumin8-dev/main: `8c14c4cc8b37bc4960b16c10cf273bbf788bc18f`
- 실제 tree 비교:
  - upstream public blobs: 85
  - portal blobs: 281
  - upstream only: 73
  - portal only: 269
  - 공통인데 내용이 다른 파일: 7개
    - apply.html
    - index.html
    - index-test.html
    - privacy.html
    - terms.html
    - frontend/shared/header.html
    - frontend/shared/site.css
  - footer.html / site.js는 양쪽 blob이 동일.
- 통합 브랜치:
  - `integration/unified-main-20261001`
- 통합 방식:
  - portal tree를 base로 사용.
  - 최신 upstream public의 index/apply/index-test/privacy/terms/signup-guide/assets/public UI workflow/check script를 overlay.
  - public 화면/assets는 upstream blob을 그대로 보존.
  - portal/backend/auth/admin/edge/ops는 portal branch 내용을 그대로 보존.
- shared 명시적 해결:
  - `frontend/shared/header.html`: upstream public landing header를 유지.
  - `frontend/shared/portal-header.html`: 기존 portal 기능 페이지용 header를 별도 source로 추가.
  - `tools/build_site_shell.py`: private mypage/portal이 portal-header.html을 사용하도록 변경.
  - `frontend/shared/site.css`: public CSS를 기준으로 유지하고 standalone auth fallback만 `.auth-main` 범위로 추가.
  - `backend/portal_static/site.css`: 위 merged shared CSS와 exact sync.
  - `tools/test_shared_shell.py`: public header / portal header 경계를 각각 검증하도록 변경.
- Git history 보존:
  - 첫 integration commit `e89aaffd83f4a5ff80ce31aaca616965f3f02391`은 portal head + upstream public head를 두 parent로 사용.
  - 기존 illumin8-dev/main에 integration이 포함하지 않던 21개 커밋이 있었음.
  - 이 21개는 모두 public UI 계열이고 upstream public main이 더 최신 정본임을 확인.
  - 내용은 upstream을 유지하되 기존 main SHA를 merge parent로 포함한 commit `e0a5f22408d7af47d18e08ebf9a6992e2149c7c0` 생성.
  - 현재 integration branch는 main 대비 behind 0.
- deploy authority main 이전:
  - commit `bb2ee78a1eb96ca877457246d785ef9d98a34e86`
  - `.github/workflows/portal-deploy.yml` push branch / github.ref guard를 main으로 변경.
  - `.github/portal/common.py` BRANCH/REF/WORKFLOW authority를 main으로 변경.
  - connect.py / README / automation tests도 main trust 기준으로 갱신.
  - portal automation / portal UI / login flow / same-domain edge/image / admin preview workflow가 main push에서도 빠지지 않도록 trigger 보강.
  - `.github/portal-deploy.request` 이외의 일반 코드 변경은 GCP operation을 실행하지 않는 구조 유지.
- 보존 검증:
  - public exact files mismatch = 0
  - assets mismatch = 0
  - portal backend/edge/ops unexpected change = 0
  - portal source missing = 0
  - upstream public source missing = 0
- PR #108:
  - title: `integration: unify public and portal on main`
  - head: `integration/unified-main-20261001`
  - base: `main`
  - 생성 직후 최종 확인에서 mergeable=true / mergeable_state=unstable(CI 진행 중).
  - PR #107은 exploratory draft 그대로이며 병합하지 않음.
- PR #108 첫 CI:
  - Public UI checks만 먼저 failure.
  - 원인은 통합 구조/CSS 충돌이 아니라 `tools/check_public_ui.py`가 읽는 `CURRENT_WORK.md`를 public overlay에서 제외한 것.
  - upstream `CURRENT_WORK.md`를 추가하는 수정 commit 생성:
    - current head: `1c3b0e0ba46fb450081d5cf8ee7f7be26dad6a6b`
  - 이 수정 후 CI 7개가 새 head에서 다시 실행 중:
    - Public UI checks
    - Backend checks
    - Portal automation guards
    - Portal UI checks
    - Login flow regression
    - Same-domain login edge and portal image
    - Build standalone admin preview
- 현재 절대 금지/미실행:
  - Cloudflare Pages 새 project 연결 안 함.
  - richonacademy.com cutover 안 함.
  - Worker route 변경 안 함.
  - GCP/Neon/customer row 변경 안 함.
  - site-wide CSS/shared 전체 리팩터링 안 함.
- 다음 시작 지점:
  1. PR #108 current head `1c3b0e0...`의 7개 CI 최종 결과 확인.
  2. 실패 job이 있으면 해당 job log만 보고 최소 수정.
  3. public/backend/portal/login/edge/admin preview 전부 PASS 확인.
  4. PR #108 mergeability 재확인 후 main 병합.
  5. 병합 후 illumin8-dev/main이 public + portal/backend 단일 코드 정본인지 tree/readback으로 재검증.
  6. 여기까지 완료 후에만 다음 단계:
     - 새 Cloudflare Pages를 illumin8-dev/main에 연결
     - pages.dev 검증
     - auth/portal Worker route 검증
     - richonacademy.com cutover
  7. 전체 사이트 CSS/shared source 통합은 hosting cutover 이후 별도 PR.
