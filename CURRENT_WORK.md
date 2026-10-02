# CURRENT WORK / 리치온아카데미

기준일: 2026-10-02

이 파일은 현재 작업의 짧은 인덱스다.
과거 작업 이력이나 완료 체크리스트를 중복 보관하지 않는다.

## 현재 authority

- 코드 정본: `illumin8-dev/richon-academy` / `main`
- 상세 운영 이력: `backend/ADMIN_MYPAGE_HANDOFF.md`
- 2026-10-02 저장소 정리 기록: `backend/OPS_CLEANUP_AUDIT_20261002.md`
- 저장소 유지관리 원칙: `REPO_MAINTENANCE.md`
- 포털 클라우드 작업 요청: `.github/portal-deploy.request`

충돌하는 과거 문구가 있으면 최신 실제 운영 readback과 위 문서의 최신 checkpoint를 우선한다.

## 현재 운영 상태

- public / auth / portal 운영 경로 정상.
- 공개 캘린더는 60초 edge cache 적용 완료.
- protected portal candidate는 최신 main 계열 코드로 검증 완료.
- deploy request는 `hold`.
- Pre리치온 9기 canonical program/run 및 관리자 수강권 -> 내 강의 E2E 확인 완료.
- 현재 저장소의 장기 작업 branch는 `main` 하나를 원칙으로 한다.
- 결제/가격 초안 `feat/backend-pricing-notes-oauth`만 명시적 HOLD 예외로 보존한다.
- GitHub `delete_branch_on_merge=true` 설정을 사용한다.

## 명시적 HOLD

- Kakao / Naver 플랫폼 심사
- 결제 / PG
- 실제 일반회원 대상 E2E
- Pre리치온 session / 영상 / 자료 운영 데이터 입력

HOLD 항목은 사용자 재개 결정 전 구현/배포하지 않는다.

## 작업 원칙

- 운영 변경 전 실제 상태를 read-only로 확인한다.
- 코드 병합 / Cloudflare Worker / Cloud Run candidate / DB 변경을 구분한다.
- migration / rollback / one-time ops helper를 단순 reference count로 dead code 처리하지 않는다.
- 완료된 short-lived branch는 merge 후 자동 삭제한다.
- unique history를 폐기해야 할 때는 필요하면 archive tag로 exact HEAD를 보존한 뒤 branch를 정리한다.
