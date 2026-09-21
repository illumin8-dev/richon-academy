# 리치온 백엔드: 비공개 점검 / 결제 대기 주문

## 이번 범위

기존 `apply.html`, 메인 홈페이지, 네이버폼, 프론트 배포 설정은 변경하지 않습니다.
실제 강의·수강료는 임의로 등록하지 않습니다. PG 호출 / 결제 완료 / 수강 확정 / 로그인 / 알림 / 고객관리 화면도 아직 없습니다.

| 기능 | 동작 |
|---|---|
| `GET /health` | DB 접근 없는 프로세스 점검 |
| `GET /health/db` | 읽기 전용 `SELECT 1` 점검. 주기적 프로브로 사용하지 않음 |
| `POST /orders` | 서버가 등록한 강의·금액으로 결제 대기 주문을 저장 |
| `migrate_orders.py --apply` | 명시적으로 주문용 DB 구조 생성. 자동 시작/HTTP 요청에서는 실행하지 않음 |

**Cloud Run IAM으로 보호되는 비공개 개발 API입니다.** 아직 일반 고객에게 공개하거나 `apply.html`에 연결하지 마세요.
CORS 허용 / 고객의 주문 조회 / 주문 상태 변경 API는 만들지 않았습니다. 브라우저에서 서비스 URL이 차단되는 것은 정상입니다.

## 파일 변경 위치

- `orders.py`: 입력 확인 / 금액·강의명 서버 조회 / 주문 생성 / 동일 요청 재전송 처리.
- `main.py`: 주문 API 등록 / 입력값을 노출하지 않는 검증 오류 처리. 기존 점검 API 유지.
- `migrations/001_pending_orders.sql`, `migrate_orders.py`: 강의·주문 테이블과 이력 / 트랜잭션·체크섬 기반 재실행 보호.
- `Dockerfile`, `.dockerignore`, `.gcloudignore`: 필요한 새 서버 파일만 빌드에 포함.
- `scripts/prepare-orders.sh`: Cloud Shell에서 비밀값을 출력하지 않고 DB 구조를 적용.
- `tests/test_orders.py`: API·저장 로직 모의 테스트.
- `tests/test_orders_postgres.py`: 별도 빈 테스트 PostgreSQL에서 실행하는 선택적 SQL·동시성 테스트.

## GCP / 비밀 설정

프로젝트 `richon-academy`, 리전 `asia-southeast1`, 서비스 `richon-backend-test`를 사용합니다.
런타임은 `richon-backend@richon-academy.iam.gserviceaccount.com`, 빌드는 `richon-build`로 분리합니다.
비밀 `richon-database-url` 하나에만 런타임의 Secret Accessor 권한을 둡니다.
비밀 값에는 `postgresql://...` 주소만 넣고 `psql ` / 양끝 따옴표는 제외합니다.
키·DSN·비밀번호·토큰은 소스 / PR / 로그 / 채팅에 올리지 않습니다.

### 1. 주문 테이블 준비 — 명시적인 DB 변경

인증된 Cloud Shell에서 이 브랜치를 받은 뒤 실행합니다.

```bash
bash backend/scripts/prepare-orders.sh
```

대상 프로젝트와 비밀 버전을 확인하고 `CREATE`를 입력해야 진행합니다.
`richon` 스키마에 `courses`, `orders`, `schema_migrations`를 생성합니다.
**실제 강의 / 임시 1,000원 상품 / 고객 / 주문은 하나도 넣지 않습니다.**
같은 체크섬의 적용 이력이 있으면 테이블 생성 SQL을 다시 실행하지 않습니다.
다른 용도의 기존 `richon` 스키마가 있거나 체크섬이 다르면 중단합니다. 오류 시 DDL 전체를 롤백합니다.
이 명령은 서버를 배포하지 않습니다. Cloud Shell 실행 계정에 비밀 읽기 권한이 필요합니다.

### 2. 비공개 서버 재배포

```bash
bash backend/scripts/deploy-test.sh
```

기존처럼 `YES` 확인 후 `backend/`만 빌드합니다. Secret의 최신 활성 버전을 숫자로 고정합니다.
최소 인스턴스 0 / 최대 설정 1 / CPU 1 / 512MiB / 동시 요청 4를 유지합니다.
IAM 생성·권한 전파가 지연되면 수 분 뒤 재시도합니다. 권한을 공개로 바꿔 우회하지 마세요.
빌드·이미지 보관·네트워크 등 과금은 별도이며 인스턴스 제한은 비용의 절대 상한이 아닙니다.
기존 배포 스크립트의 `PASS`는 **IAM 차단 + 서버 응답 + DB 읽기**만 의미합니다. 주문 저장 검증은 별도로 해야 합니다.

### 3. 강의 정보 확정 및 주문 점검 — 별도 후속 단계

실제 강의명 / 기수 / 수강료가 확정된 뒤 `richon.courses`에 등록합니다.
`course_id`는 과정·기수별 고유값이며, 기존 신청 페이지에서 선택하는 강의와의 대응은 연결 단계에서 확정합니다.
가격은 양의 정수 원화입니다. `enabled` 기본값은 FALSE이며, 미등록·비활성 강의는 주문할 수 없습니다.
테스트 금액은 아래 독립 테스트 코드에서만 사용하며 운영 수강료가 아닙니다.

요청 형식(아래는 실제 제출하지 않는 설명용 더미):

```json
{
  "course_id": "example-course-01",
  "customer_name": "테스트 신청자",
  "customer_phone": "01000000000",
  "customer_email": "student@example.invalid"
}
```

`Idempotency-Key` 헤더에는 결제 시도마다 생성한 UUID v4를 넣습니다.
**같은 시도의 더블클릭·재시도는 같은 키를 재사용해야 합니다.** 다른 키는 별도 주문입니다.
동일 키·동일 정규화 입력은 이전 주문을 반환(200), 새 주문은 201, 같은 키로 내용 변경은 409입니다.
`amount`, `status` 등 허용하지 않은 필드는 422로 거부합니다. 강의 미등록·비활성은 404, 저장/설정 오류는 503입니다.
클라이언트가 아니라 DB 강의 정보에서 금액을 가져와 주문에 스냅샷으로 저장합니다.
주문 상태는 `pending_payment`만 허용하며, 응답에는 이름·전화·이메일·재시도 지문을 넣지 않습니다.
전화·이메일 형식 검사는 소유자 인증이나 네이버폼 제출 확인이 아닙니다.

## 검증

```bash
cd backend
python -m pip install -r requirements-dev.txt
python -m pytest
```

기본 테스트는 모의 연결입니다. 실제 PostgreSQL 트랜잭션·Neon·TLS·IAM 검증을 대신하지 않습니다.
`RICHON_EMPTY_TEST_DB=YES`, `RICHON_TEST_DATABASE_URL`을 별도로 설정하면 SQL 통합 테스트가 활성화됩니다.
**반드시 비어 있는 폐기 가능한 전용 DB만 사용하세요.** 통합 테스트는 자체 `richon` 스키마를 만들고 종료 시 삭제합니다.
기존 `richon` 스키마 또는 앱의 `DATABASE_URL`과 같은 주소는 거부합니다. 실제 고객 DB에서 실행하지 마세요.
통합 항목은 저장·재시도 / 동시 요청 8개 / 동일 키·다른 입력 경합 / 가격 스냅샷·비활성화 / 상태 변조 / 마이그레이션 재실행입니다.

공개 전: 실제 PostgreSQL 동시성 검증, 전용 DB 최소권한 역할, 고객 동의·입력 흐름, 요청 제한·남용 방지, 비회원 주문 접근 권한을 확정해야 합니다.
PG 단계에서는 결제 상태·금액 검증 / 웹훅 중복 처리 / 환불·취소 상태 전이를 별도 구현합니다.
현재 DB CHECK도 결제 대기만 허용하므로 결제 상태 추가는 별도 마이그레이션이 필요합니다.
카카오·네이버 회원과 기존 주문 연결은 연락처 문자열 일치만으로 처리하지 않습니다.

## 배포 분리 / 되돌리기

아직 `main`에 합치지 않습니다. 기존 프론트 출력물에서 `backend/`를 제외하는 설정은 별도 확인·승인이 필요합니다.
`.gcloudignore`는 GCP 업로드 제한일 뿐 Cloudflare / GitHub Pages 제외 설정이 아닙니다.
공개 GitHub에 서버 소스가 보이는 것과 비밀 노출은 별개이며, 비밀 원문은 저장하지 않습니다.
서버는 이전 이미지/리비전으로 되돌릴 수 있지만, 이미 적용한 스키마는 자동 삭제하지 않습니다.
이 PR에는 고객 데이터나 다른 사이트 리소스를 삭제하는 운영 스크립트가 없습니다.
통합 테스트의 스키마 삭제는 위의 명시적인 빈 테스트 DB 조건에서만 실행됩니다.

## 참고 문서

- https://docs.cloud.google.com/run/docs/deploying-source-code
- https://docs.cloud.google.com/run/docs/authenticating/developers
- https://docs.cloud.google.com/run/docs/configuring/services/secrets
- https://www.psycopg.org/psycopg3/docs/basic/transactions.html
- https://www.postgresql.org/docs/current/transaction-iso.html
- https://www.postgresql.org/docs/current/sql-insert.html
- https://fastapi.tiangolo.com/tutorial/handling-errors/
