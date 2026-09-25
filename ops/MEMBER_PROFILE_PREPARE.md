# 회원정보 DB009 준비 / 승인 2-2

사용자 승인: 연령대와 성별은 선택 유지. DB009 및 필요한 최소권한 준비만 실행.
기존 회원/주문 변경·삭제, 상담정보 철회 기능 재도입, 계정 연결/탈퇴 구현,
수집 활성화, 서버/Worker/Access/정책 공개는 이 작업의 범위가 아니다.

## 실행 경로
Neon connector의 run_sql은 입력 스키마에 없는 project_id를 요구해 실행 전 실패했다.
다른 API에 SQL을 숨겨 실행하거나 관리자 권한을 추가하지 않는다.
소유자가 기존 SQL Editor의 richon-academy / production / neondb를 선택하고
neondb_owner로 `ops/prepare_member_profiles.sql` **전체를 한 번** 실행한다.
프로젝트/브랜치는 SQL만으로 독립 확인되지 않으므로 실행 전 콘솔 선택을 확인한다.

## 검증/변경 범위
- 기존 001/002/007/008의 정확한 파일 체크섬, DB 이름/소유자, 스키마 소유,
  제한 runtime 역할과 membership/DDL 제한을 검사한다.
- 같은 migration advisory lock. 다른 준비 작업이 실행 중이면 즉시 중단.
- 테이블 또는009 적용기록이 이미 있으면 덮어쓰기·자동수리 없이 중단.
- 승인된009 원문을 그대로 실행하고 같은 checksum으로 ledger를 기록한다.
- richon_portal_login에 프로필 SELECT와 정확한10열 INSERT만 부여한다.
  동의시각은 서버/DB 기본값으로 기록하며 클라이언트가 INSERT하지 못한다.
- unexpected default ACL·과도한 열/테이블 권한이면 생성/권한/ledger가 모두 rollback.
- DO 한 문장 안에서 검증·DDL·GRANT·기록을 수행한다. 영구 함수/스키마/역할을 추가하지 않는다.
- 기존 회원/주문/신원/세션 행과 기존 테이블 권한을 수정하지 않는다.
- 맨 마지막 조회의6개 값이 모두 true(t)여야 준비 성공. 고객정보를 출력하지 않는다.
- 실제 runtime 자격증명으로 Cloud Run에서 로그인한 검증은 아니다.
  앞으로 정책 활성화 전 기존 startup 최소권한 검사를 다시 통과해야 한다.

## 재실행/오류
성공 후 반복 실행하지 않는다. ALREADY_PRESENT는 기존 상태를 먼저 읽으라는 뜻이다.
다른 STOP/SQL 오류가 나오면 오류만 공유하고 table/ledger를 수동 삭제하지 않는다.
이 파일은 missing table/ledger에 대한 승인된 준비이며 임의의 기존 객체를 채택하지 않는다.

## 검증
`backend/tests/member_profile_prepare_check.py`는 GitHub CI의 폐기용 loopback PostgreSQL에서만 실행.
DB명/소유자는 실행 guard까지 검증하기 위해 운영과 동일하되 프로젝트/고객자료는 복제하지 않는다.
canonical bytes/hash, empty profile, 기존행/권한 유지, 최소권한 실제 INSERT/SELECT,
UPDATE/DELETE/TRUNCATE/DDL/ledger 접근 차단, 중복/동시요청, 실패 rollback을 검사한다.
CI17/18 결과는 해당 commit의 workflow를 확인한다. 테스트 성공과 운영 적용은 구분한다.

## 참고
PostgreSQL 공식 GRANT: https://www.postgresql.org/docs/current/sql-grant.html
SQL은 명시적 owner 실행용이다. Docker/업로드 allowlist에 넣거나 자동배포에서 실행하지 않는다.
