# 운영 정리 감사 / 2026-10-02

## 범위
이 문서는 cleanup 후보를 정리하기 위한 감사 결과다.
실제 PR close, branch 삭제, 코드 삭제, DB/Cloud 변경은 수행하지 않는다.

현재 기준:
- canonical repository: `illumin8-dev/richon-academy`
- canonical branch: `main`
- main SHA at audit start: `026f485d7e276e671774999c6029ceeafa73b999`
- portal deploy request: `hold`
- login provider review: HOLD
- payment / PG: HOLD

## Open PR 감사

### Close 후보 / 현재 main에 병합하지 말 것
1. PR #101 / ops: add guarded Pre Richon 9 course bootstrap
   - 운영값과 직접 충돌하는 과거 bootstrap 초안.
   - 초안: 132,000원 / 2026-10-01 시작 / 2026-11-30 종료 / 7개 session 자동 생성.
   - 현재 production: 176,000원 / 2026-10-08~2026-12-07 / sessions=0.
   - 다시 병합하면 안 됨.

2. PR #86 / fix(auth): restore polished login and signup experience
   - 이후 auth UX / shared chrome / 운영 rollout이 여러 차례 완료됨.
   - PR에 있던 `/portal/courses` return 허용은 최신 #137에서 별도로 정본화 완료.
   - 현재 운영 기준으로 superseded.

3. PR #72 / feat(catalog): add course programs runs and weekly sessions
   - 이후 canonical course domain / entitlement / admin UI가 main에 구현됨.
   - 실제 Pre리치온 9기 program/run/enrollment E2E도 운영에서 통과.
   - 과거 catalog foundation은 superseded.

4. PR #59 / refactor(ui): bring apply page onto shared chrome
   - apply gallery asset과 shared chrome은 이후 통합 main에 반영됨.
   - 현재 single-source site chrome 구조가 더 최신 authority.
   - superseded.

5. PR #48 / docs: record login E2E and profile consent follow-up
   - 문서 전용 PR.
   - 현재 `backend/ADMIN_MYPAGE_HANDOFF.md`의 이후 체크포인트가 대체.
   - superseded documentation.

6. PR #43 / test(login): verify modal 303 reaches provider
   - 오래된 draft test PR.
   - 이후 login-flow regression / customer-route probes / provider handoff 검증 체계가 main에 존재.
   - superseded test draft.

7. PR #25 / DB009 회원정보 저장 공간·최소권한 준비
   - 과거 DB009 준비용 SQL/CI.
   - 현재 main에는 canonical `009_member_profiles` 및 이후 account lifecycle 계열이 존재하고 운영 적용 이력이 있음.
   - 과거 owner-prepare draft를 다시 병합하지 않음.

### 보존 / HOLD
8. PR #10 / 1·2·6개월 가격 / 고객 메모 초안
   - 일부 unique scope가 아직 main에 없음:
     - `backend/pricing.py`
     - `006_pricing_notes`
     - learner notes draft
   - OAuth 007 계열은 이후 main에 별도 구현됐지만 pricing/notes 부분은 독립적으로 남아 있음.
   - 결제/PG를 현재 보류하기로 했으므로 이번 cleanup에서는 보존.
   - 향후 결제/가격 정책 재개 시 요구사항부터 다시 검토하고 필요한 부분만 재작성하는 편이 안전함.

## Branch 감사

현재 branch 수: 134.

### main에 완전히 흡수된 것이 확인된 안전 삭제 후보
아래 branch head는 GitHub compare에서 `branch_unique_commits=0`으로 확인됨.

- `feat/enrollment-restore`
- `fix/public-calendar-edge-cache`
- `fix/worker-courses-return-sync`
- `fix/admin-shell-spacing-consistency`
- `fix/pages-canonical-route-probe`
- `fix/restore-original-font-loading`
- `fix/sticky-shared-footer`
- `fix/unify-admin-site-chrome`
- `refactor/shared-admin-css-source`
- `refactor/single-shared-site-chrome`
- `integration/main-portal-unify-20261001`
- `integration/unified-main-20261001`

이 12개는 이번 감사에서만 delete 후보로 분류한다.
실제 삭제는 별도 승인 전 수행하지 않는다.

### 이번에 자동 삭제 후보로 분류하지 않는 branch
- 현재 open PR의 head branch.
- Kakao/Naver 심사 자료 branch.
- 과거 production recovery/diagnostic branch.
- main에 없는 unique commit 여부를 아직 확인하지 않은 branch.
- payment/pricing draft branch.

134개 전체를 이름만 보고 일괄 삭제하지 않는다.

## Dead-code 감사

이번 pass에서는 main 내부 코드 파일을 삭제 후보로 확정하지 않는다.

이유:
- migration 파일은 실행 완료 후에도 schema checksum/history authority로 보존 필요.
- `.github/portal/*`의 과거 operation/recovery helper는 workflow 또는 장애복구 경로와 연결될 수 있음.
- ops helper는 일반 앱 import가 없어도 owner-run one-time tool일 수 있음.
- 단순 reference count만으로 dead code를 판정하면 위험함.

따라서 이번 cleanup의 안전한 1차 효과는:
1. stale open PR 정리 후보 확정.
2. main에 완전히 흡수된 branch 12개 삭제 후보 확정.
3. 과거 상충 문서를 최신 checkpoint로 덮어쓰기.
4. 실제 code deletion은 별도 audit 후 진행.

## 현재 보류 항목
- Kakao CI / Naver 공개 심사
- 결제 / PG
- 실제 일반회원 E2E
- Pre리치온 session / 영상 / 자료 입력

위 항목은 이번 cleanup 범위에서 구현/실행하지 않는다.
