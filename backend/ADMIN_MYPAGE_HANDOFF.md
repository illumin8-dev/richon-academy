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
