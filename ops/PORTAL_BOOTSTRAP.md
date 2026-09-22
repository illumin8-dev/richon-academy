# 로그인 서버 비공개 준비 / PREPARE 확인 후 실행

현재 Cloudflare Worker는 배포됐지만 PORTAL_ENABLED=false이고 경로 연결도 없습니다.
이번 범위는 **별도 richon-portal 서버 + 로그인 DB 구조 + 최소권한 실행 계정**입니다.
기존 richon-backend-test 공개, 홈페이지/DNS/Worker 경로 변경, 실제 소셜 로그인/회원 등록은 하지 않습니다.

## 사용자 계정에서 실행해야 하는 이유

기존 GitHub WIF는 기존 비공개 주문 테스트 서비스 배포에만 권한이 있습니다.
이번 스크립트는 그 권한을 넓히거나 새 장기 키를 만들지 않습니다.
GCP 소유자의 Cloud Shell에서 새 자원을 만드는 승인을 PREPARE로 한 번 받습니다.
빌드/이미지 보관/서버 사용량 과금이 발생할 수 있으며 무료를 보장하지 않습니다.
서버: 1 CPU, 512 MiB, min 0, max 1, concurrency 20, IAM 인증 유지.

## 실행

이 PR의 고정 커밋을 clean checkout한 뒤 `bash ops/prepare_portal.sh`.
별도 임시 가상환경에 기존과 같은 psycopg[binary]==3.3.4를 설치하며 종료 시 가상환경만 삭제합니다.
소스는 삭제하지 않고, 실제 자원 자동 삭제/원복은 하지 않습니다.
PREPARE 이전에는 GCP 메타데이터 읽기만 합니다. 실제 DB 접속/변경과 Secret 값 읽기는 확인 이후입니다.

## 수행 범위

- 프로젝트 richon-academy / 756298505437 / asia-southeast1로 고정.
- 기존 서버의 private IAM과 DATABASE_URL의 고정 버전을 읽고 대상 Neon endpoint/DB/owner를 대조.
- 새 DB URL을 GCP richon-portal-database-url에 저장. 비밀번호는 Git/출력/빌드/클라이언트 SQL 문자열에 넣지 않음.
- 일반 SQL 역할 richon_portal_login 생성. 원래 비밀번호를 verify-full TLS 연결의 바인드 값으로 전송하며, pg_temp의 SECURITY INVOKER 함수가 고정 CREATE ROLE을 실행함.
- 001 체크섬 검증 후 기존 002/003/007 SQL과 역할/grants를 한 트랜잭션에 적용.
- 회원 신규 생성/세션 유지/일회성 OAuth 처리와 포털 조회에 필요한 열 단위 권한만 부여.
- 회원 role/status 변경, 주문/과정 변경, 주문 소유권 연결, schema/DDL/migration 접근은 불가.
- 기존 확정 수강 기록/결제정보/주문 rows에 대한 UPDATE/DELETE/backfill 없음. 004/005/006 적용 안 함.
- 새 runtime richon-portal@ 계정에 새 DB 비밀과 기존 Kakao 비밀 2개의 접근권한만 부여.
- 기존 richon-build 계정으로 portal 전용 이미지만 생성. 이 계정의 권한은 변경 안 함.
- 전용 Artifact Registry richon-portal-ci에 이미지 저장. source와 image 저장료가 남을 수 있음.
- 모든 기능 OFF 상태의 richon-portal을 **비공개**로 배포. 숫자 Secret 버전과 이미지 digest를 고정.
- 시작 시 실제 runtime DB 연결/권한을 읽기 전용으로 검증한 뒤에만 포트를 엶.
- 마지막에 private IAM/Ready/이미지 및 기존 주문 서버 spec/IAM 불변 확인.

## Neon 전용 비밀번호 처리 오류 수정

057c008 버전은 libpq가 만든 SCRAM 검증자를 CREATE ROLE에 전달했습니다.
분리된 Neon PostgreSQL 18 검증 브랜치에서 이 방식을 실행하면 control plane이 HTTP 400과
`Neon only supports being given plaintext passwords`를 반환함을 재현했습니다.
일반 PostgreSQL CI만으로는 이 관리형 서비스의 제한을 검증할 수 없었습니다.

수정한 ops/portal_credentials.py는 이미 GCP Secret에 저장한 비밀번호를 그대로 사용합니다.
비밀번호를 포함하는 SQL 문자열을 클라이언트에서 만들지 않고 바인드 인자로 전달합니다.
서버 내부에서는 원래 값으로 CREATE ROLE을 실행하고 PostgreSQL이 저장용 해시를 계산합니다.
Neon control plane도 원래 비밀번호를 처리합니다. 비밀번호가 서비스 제공자에게 전달되지 않는다는 의미는 아닙니다.

전송 전에 현재 세션의 SQL/파라미터/오류/중첩문/디버그/감사 로그 설정을 확인합니다.
노출 우려가 있으면 `credential_logging_not_safe`로 중단하며 로그 설정이나 권한을 자동 변경하지 않습니다.
임시 함수는 해당 소유자 연결이 닫히면 사라지고 runtime 이미지에 포함되지 않습니다.
기존 최소권한, TLS 인증서·호스트 검증, PUBLIC/IAM 보호, 오류 원문 비출력은 유지합니다.

## 재실행/중단

같은 코드와 같은 고정 Secret을 재사용하며 DB 비밀번호를 임의로 교체하지 않습니다.
실패 시 이미 생성된 자원은 남을 수 있고 단계/안전한 오류 코드만 출력합니다.
다른 사람이 만든 동명 자원, 활성화된 포털, 공개 IAM, 체크섬 충돌은 중단합니다.
상세 예외/DSN/키가 포함된 터미널 출력을 채팅에 붙이지 않습니다.
Cloud/API/IAM 메타데이터 확인과 쓰기는 여러 트랜잭션이므로 전체가 단일 원자 연산은 아닙니다.

## 아직 하지 않는 것

PORTAL PRIVATE READY는 실제 카카오 인증 완료가 아닙니다.
개인정보/약관의 실제 승인 버전, edge 공유 비밀, callback 로그/요청 제한 정책,
공개 포털 IAM 전환과 Cloudflare 경로 활성화, 운영자 지정, 실제 브라우저 시험은 별도 단계입니다.
월별/수동 관리와 가격 1/2/6개월 변경은 해당 PR 상태 그대로이며 이번에 활성화하지 않습니다.
새 포털에 대한 GitHub 자동배포 권한은 이번에 새로 연결하지 않습니다.

## 검증

backend/tests/test_portal_bootstrap.py: 대상/공개 차단/활성 서비스 덮어쓰기 거부/오류 비노출.
backend/tests/test_portal_bootstrap_postgres.py: 폐기 가능한 loopback CI에서 002/003/007,
최소권한 회원 생성/세션/포털 조회/로그아웃, 관리자 승격/주문 변경/DDL 차단,
새 역할 비밀번호 접속과 기존 역할 재실행 시 비밀번호 미변경을 검사합니다.
backend/tests/test_portal_credentials.py: 바인드 전송, 로그 검사 실패 시 비밀번호 미전송, 임시 INVOKER 함수와 고정 역할 권한을 검사합니다.
기존 social-login-ci에서 portal image의 build/startup도 검사합니다.
실제 GCP 실행 결과는 사용자가 고정 스크립트를 실행한 뒤 별도 확인합니다.

공식 근거:
- https://docs.cloud.google.com/run/docs/configuring/services/secrets
- https://docs.cloud.google.com/run/docs/deploying
- https://docs.cloud.google.com/iam/docs/roles-permissions/run
- https://docs.cloud.google.com/build/docs/securing-builds/configure-user-specified-service-accounts
- https://www.postgresql.org/docs/18/runtime-config-logging.html
- https://www.postgresql.org/docs/18/pgstatstatements.html
