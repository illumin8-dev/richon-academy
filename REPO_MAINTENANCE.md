# Repository maintenance policy

리치온아카데미 저장소의 branch / PR / dead-code 정리 원칙이다.

## 1. Source of truth

- canonical repository: `illumin8-dev/richon-academy`
- canonical production branch: `main`
- normal feature/fix branch는 short-lived로 취급한다.
- GitHub repository setting `delete_branch_on_merge=true`를 유지한다.
- 장기간 보존해야 하는 unmerged branch는 이유를 문서에 명시한다.

현재 예외:
- `feat/backend-pricing-notes-oauth`
  - payment / pricing HOLD 자료.
  - 현재 main에 그대로 merge하지 않는다.

## 2. PR lifecycle

merged PR:
- merge 후 head branch는 자동 삭제한다.
- PR discussion / diff / merge commit이 history authority다.

superseded PR:
- 바로 삭제하지 않고 왜 더 이상 merge하면 안 되는지 comment를 남긴다.
- 이후 PR을 close한다.
- head에 unique history가 있고 참고 가치가 있으면 archive tag를 먼저 만든다.

HOLD PR/branch:
- 재개 조건과 보존 이유를 적는다.
- 최신 main과 자동으로 동기화하려고 하지 않는다.
- 재개할 때 현재 schema / product decision 기준으로 다시 검토한다.

## 3. Archive tags

branch ref는 작업 포인터이고 archive tag는 역사 보존점이다.

unique branch를 폐기할 때 history 보존이 필요하면:

`archive/YYYY-MM-DD/<original-branch>`

형식으로 exact HEAD를 태그한 후 branch를 삭제한다.

archive tag는 명시적인 history cleanup 없이는 삭제하지 않는다.

## 4. Dead-code 삭제 기준

"검색 결과 0건"만으로 dead code를 판정하지 않는다.

삭제 전 아래를 모두 확인한다.

1. application reference
   - Python import
   - JS import / script
   - route registration
   - HTML/CSS asset reference
2. build / generated reference
   - Dockerfile
   - build script
   - source -> generated artifact sync
3. CI / deploy reference
   - GitHub Actions
   - Cloudflare / Cloud Run deploy helper
4. operational reference
   - owner-run ops helper
   - migration / ACL preparation
   - incident recovery / rollback
5. documentation reference
   - runbook / handoff / recovery instruction
6. production history
   - schema migration checksum
   - rollback revision compatibility
   - audit/readiness verification
7. tests
   - current behavior or historical compatibility contract

하나라도 현재 필요한 역할이 있으면 삭제하지 않는다.

## 5. Files that look duplicated but are not dead

`frontend/shared/*`는 editable canonical source가 될 수 있고,
`backend/portal_static/*`는 Cloud Run runtime용 generated artifact가 될 수 있다.

두 파일이 byte-identical하다는 이유만으로 하나를 삭제하지 않는다.
생성기와 CI가 source/output 관계를 강제하는지 먼저 확인한다.

## 6. Migrations and one-time operations

다음은 일반 import가 없어도 정상이다.

- `backend/migrations/*`
- migration helper
- `ops/prepare_*.py`
- `.github/portal/*` recovery/stage/inspect helper

production schema checksum, runtime grant 복구, rollback 호환성에 사용될 수 있다.
대체 경로가 증명되기 전에는 dead code가 아니다.

## 7. Cleanup cadence

대규모 milestone 뒤에는 아래 순서로 정리한다.

1. open PR audit
2. `git branch --merged main` branch cleanup
3. unmerged branch 분류
4. 필요 시 archive tag 생성
5. stale current-work 문서 정리
6. dead-code reference audit
7. CI PASS
8. production deploy request가 `hold`인지 확인

branch 수 자체를 줄이는 것이 목표가 아니라, 각 branch와 파일의 보존 이유가 명확한 상태를 유지하는 것이 목표다.
