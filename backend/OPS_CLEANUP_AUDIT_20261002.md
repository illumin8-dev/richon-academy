# 운영 정리 감사 / 2026-10-02

## 결과 요약

이번 정리는 "많이 지우기"가 아니라 "삭제 안전성을 Git history와 운영 역할로 증명한 뒤 정리"하는 방식으로 수행했다.

- canonical repository: `illumin8-dev/richon-academy`
- canonical branch: `main`
- portal deploy request: `hold`
- login provider review: HOLD
- payment / PG: HOLD
- cleanup 시작 시 remote branch: 약 134개
- cleanup 완료 후 remote branch: 2개
  - `main`
  - `feat/backend-pricing-notes-oauth` / 결제·가격 정책 HOLD
- GitHub repository setting: `delete_branch_on_merge=true`
- 현재 open PR: 0

## PR 정리

다음 superseded PR은 현재 main과 충돌하거나 더 최신 구현으로 대체되어, 이유를 Conversation comment로 남긴 뒤 closed 처리했다.

- #101 / 과거 Pre리치온 9 bootstrap
  - 132,000원 / 2026-10-01~11-30 / 7개 session seed 가정.
  - 현재 production 176,000원 / 2026-10-08~12-07 / sessions=0과 충돌.
- #86 / 과거 auth UX
- #72 / 과거 catalog foundation
- #59 / 과거 apply shared UI
- #48 / 과거 login E2E 문서
- #43 / 과거 provider 303 test draft
- #25 / 과거 DB009 owner-prepare draft

PR #10은 closed / unmerged 상태다.
해당 `feat/backend-pricing-notes-oauth` branch에는 현재 main에 없는 pricing / learner-note 초안이 있어 결제 HOLD 자료로만 보존한다.
재개 시 그대로 merge하지 않고 현재 요구사항과 schema를 기준으로 다시 검토한다.

## Branch 정리

### 1. Git에서 완전 병합이 증명된 branch

`git branch -r --merged origin/main`으로 확인된 114개 branch를 삭제했다.

이 그룹은 branch tip이 main history에 포함되어 있어 branch ref 삭제로 코드가 유실되지 않는다.

### 2. superseded closed-PR head

고유 commit이 있었지만 PR 자체와 정리 사유가 GitHub history에 남은 다음 7개 head branch를 삭제했다.

- `ops/bootstrap-pre-richon-9-20260930`
- `fix/auth-ui-login-regression`
- `feat/course-catalog-foundation`
- `feat/apply-shared-ui`
- `docs/login-e2e-and-profile-consent-20260928`
- `test/login-modal-provider-redirect`
- `feat/signup-consent-policy`

### 3. unique history archive 후 branch 삭제

나머지 오래된 unique branch 중 현재 main의 더 최신 구현으로 대체된 12개는 exact HEAD를 먼저 아래 archive tag로 보존한 뒤 branch ref를 삭제했다.

- `archive/2026-10-02/feat/backend-social-login`
- `archive/2026-10-02/feat/catalog-admin-ui`
- `archive/2026-10-02/feat/verified-ci-signup`
- `archive/2026-10-02/fix/edge-auth-css-allowlist`
- `archive/2026-10-02/fix/functional-page-header-20260930`
- `archive/2026-10-02/fix/kakao-review-signup-evidence`
- `archive/2026-10-02/fix/public-course-card-apply-polish`
- `archive/2026-10-02/fix/public-mentor-cta-polish`
- `archive/2026-10-02/fix/session-7d-24h`
- `archive/2026-10-02/policy/public-20261001`
- `archive/2026-10-02/sync/original-public-ui`
- `archive/2026-10-02/sync/public-main-20260929`

archive tag는 삭제된 branch의 exact commit을 다시 찾을 수 있는 역사 보존점이다.

## Dead-code 감사

current main ZIP 기준으로 281개 text file / 176개 Python file을 정적 교차 분석했다.

### 안전하게 확인된 것

- unreferenced frontend asset 후보: 0
- shared/runtime 중 byte-identical duplicate 11그룹은 의도된 generated artifact 구조.
  - 예: `frontend/shared/account.js` -> `backend/portal_static/account.js`
  - 예: `frontend/shared/site.css` -> `backend/portal_static/site.css`
- 이 generated 파일은 중복 구현이 아니라 build output이므로 삭제 대상이 아니다.

### 단순 분석에서 orphan처럼 보였지만 보존한 파일

- `ops/prepare_calendar.py`
- `ops/prepare_calendar_freeform.py`
- `ops/prepare_calendar_rollout_compat.py`
- `ops/prepare_calendar_visual.py`

일반 application import가 없지만 각각 DB018 / DB019 / rollout compatibility / visual grant 복구·재적용용 owner operation이다.

특히 `portal_readiness.calendar_grant_profile()`과 테스트가 `legacy / freeform / visual` 세 reviewed grant profile을 의도적으로 인식한다.
따라서 rollback/recovery 정책을 재설계하기 전에는 dead code로 삭제하지 않는다.

### 결론

이번 감사에서 runtime/application code 삭제를 안전하다고 확정한 파일은 0개다.
이는 cleanup 실패가 아니라, 실제 dead code와 운영 복구 artifact를 구분한 결과다.

## 문서 책임 분리

기존 `CURRENT_WORK.md`는 2026-09-29의 오래된 상태와 완료/미완료 항목이 섞여 있었다.
또 `tools/check_public_ui.py`가 그 문서의 특정 운영 문구를 UI 계약처럼 검사하고 있었다.

정리 원칙:
- `CURRENT_WORK.md`: 현재 authority와 HOLD만 가리키는 짧은 인덱스
- `backend/ADMIN_MYPAGE_HANDOFF.md`: 상세 historical checkpoint
- 이 파일: cleanup 실행 기록
- `REPO_MAINTENANCE.md`: 반복 가능한 저장소 유지관리 정책
- public UI CI: HTML/CSS/assets 동작 계약만 검사

## 현재 HOLD

- Kakao CI / Naver 공개 심사
- 결제 / PG
- 실제 일반회원 E2E
- Pre리치온 session / 영상 / 자료 입력

HOLD 범위는 cleanup 과정에서 구현/배포하지 않았다.
