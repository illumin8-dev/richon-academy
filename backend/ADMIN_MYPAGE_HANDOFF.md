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

