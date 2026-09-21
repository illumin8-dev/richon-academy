# 리치온 백엔드 1단계: 비공개 서버 / DB 연결 점검

## 범위

기존 HTML / CNAME / 신청 링크 / 프론트 배포 설정은 변경하지 않습니다.
이 폴더에만 FastAPI 테스트 서버를 추가합니다. 결제 / 로그인 / 고객관리 / 알림 / 테이블 생성은 포함하지 않습니다.

- `GET /health`: 프로세스 응답. DB에 접근하지 않습니다.
- `GET /health/db`: 짧은 **읽기 전용 트랜잭션**으로 `SELECT 1` 확인 후 연결 종료.
- 인증은 앱 자체 로그인이 아니라 **Cloud Run IAM**에 맡기는 비공개 시험 단계입니다.
  **공개 서비스로 전환하거나 이 경로를 프론트에 연결하지 마세요.**
- DB 점검은 수동 확인용입니다. 주기적인 생존 점검에 사용하면 Neon을 계속 깨워 무료 사용량을 소모할 수 있습니다.

## 파일

| 파일 | 역할 |
|---|---|
| `main.py` | 두 점검 API / 고정된 안전한 오류 응답 |
| `db.py` | URL 형태 확인 / TLS 연결 / 읽기 전용 쿼리 |
| `Dockerfile` | Python 3.13 / 비루트 사용자 / Cloud Run PORT 지원 |
| `.gcloudignore`, `.dockerignore` | 실행 파일만 허용하는 업로드·빌드 목록 |
| `tests/test_backend.py` | 외부 DB 없이 실행하는 모의 연결 테스트 |
| `scripts/deploy-test.sh` | Cloud Shell에서 실행하는 비공개 배포·점검 |

## 준비된 GCP 구성

- 프로젝트 ID: `richon-academy`
- 리전: `asia-southeast1` (싱가포르)
- 런타임 서비스 계정: `richon-backend@richon-academy.iam.gserviceaccount.com`
- Secret Manager: `richon-database-url`
- 런타임 계정에는 **위 비밀 하나에만** Secret Accessor 권한을 부여합니다.
- 비밀 값은 `postgresql://...` 주소 전체입니다. `psql ` / 양끝 따옴표 / 줄바꿈 명령을 넣지 마세요.
- 포트원 계정과 키는 이 단계에 필요하지 않습니다.

## Cloud Shell에서 배포

이미 인증된 Cloud Shell에서 이 브랜치를 복제한 다음 실행합니다.

```bash
bash backend/scripts/deploy-test.sh
```

실행 전 대상 프로젝트와 변경 사항을 출력하고 `YES`를 입력해야 진행합니다.
스크립트는 빌드 전용 계정 `richon-build`에 `roles/run.builder`만 부여하며, 런타임 계정과 분리합니다.
서비스 `richon-backend-test`를 비공개로 배포합니다. 빌드에는 `backend/`만 전달되고 비밀 원문은 읽거나 출력하지 않습니다.
최신 **활성** 비밀 버전을 숫자로 고정해 해당 배포에 연결합니다. 비밀을 바꾸면 새 버전으로 다시 배포해야 합니다.

설정: CPU 1 / 512 MiB / 요청 기반 CPU 할당 / 최소 인스턴스 0 / 최대 설정 1 / 동시 요청 4.
최대 인스턴스 설정은 비용의 절대 상한이 아닙니다. 빌드·이미지 보관·네트워크 등을 포함한 과금과 예산 알림은 별도로 확인하세요.

배포 후 다음 항목을 실제로 점검합니다.

1. 인증 없는 요청이 HTTP 401 또는 403으로 차단되는지.
2. 본인 GCP 로그인으로 `/health`가 `{"status":"ok"}`를 반환하는지.
3. `/health/db`가 `{"status":"ok","database":"reachable"}`를 반환하는지.

이 세 항목이 통과하기 전까지 **GCP 배포·실제 Neon 연결 검증 완료로 보지 않습니다**.
웹브라우저로 서비스 URL을 바로 열면 권한 오류가 나오는 것이 이 단계에서는 정상입니다.
스크립트 실행·점검 중 실패하더라도 이미 만들어진 서비스·빌드 이미지가 자동 삭제되지는 않습니다.

### 실패할 때

- IAM 전파가 지연되면 수 분 뒤 같은 스크립트를 다시 실행하세요. 지속되면 오류 마지막 부분만 확인합니다.
- 배포 권한 오류: 실행 계정의 Cloud Run Source Developer / Service Usage Consumer / 두 서비스 계정에 대한 Service Account User 등 권한을 확인합니다. 프로젝트 Owner로 준비한 경우 일부 권한은 이미 있을 수 있습니다.
- 비밀 접근 오류: 런타임 계정이 해당 비밀에 Secret Accessor 권한을 갖는지 확인합니다.
- `database_configuration_invalid`: Secret Manager에서 주소 형식 확인. `psql '...'` 전체를 저장했다면 주소만 새 버전으로 저장합니다.
- `database_unavailable`: Neon 연결정보·역할 비밀번호·네트워크·TLS를 비공개로 확인합니다. 로그에는 보안을 위해 구체적인 드라이버 오류를 남기지 않습니다.
- DB 연결 시 TLS 서버 인증을 위해 `sslmode=verify-full` / `sslrootcert=system`을 사용합니다. 문제가 나도 인증을 끄지 말고 인증서 저장소를 확인하세요.

**DB 연결 문자열·비밀번호·API Secret·토큰은 GitHub / PR / 채팅 / 캡처에 올리지 마세요.**

## 로컬 테스트

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest
python -m uvicorn main:app --host 127.0.0.1 --port 8080
```

테스트는 가짜 연결 객체를 사용합니다. 실제 Neon / TLS / Cloud Run IAM을 검증하는 테스트가 아닙니다.
의존성을 고정했지만 전체 전이 의존성 잠금·취약점 검사는 아직 별도 완료되지 않았습니다. 실결제 공개 전 검증 항목입니다.
DB 스키마·런타임 DB 최소권한 역할 설계는 주문 저장 단계에서 진행합니다. 현재 코드는 기존 계정으로 연결해 읽기 전용 쿼리만 수행합니다.

## 프론트 배포 / 병합 주의

이 PR은 별도 브랜치에서 테스트하고 **프론트 배포 제외 설정 확인 전 main에 병합하지 않습니다.**
GitHub Pages가 켜져 있지만 실제 서비스가 Pages인지 Cloudflare Pages인지 / 빌드 출력 디렉터리가 어디인지까지는 확인되지 않았습니다.
`backend/.gcloudignore`는 GCP 업로드 범위만 제한합니다. **Cloudflare / GitHub Pages의 배포 제외를 대신하지 않습니다.**
Pages 또는 Cloudflare의 프론트 출력물에 `backend/`가 들어가지 않도록, 실제 배포 설정 확인 후 별도 승인받아 설정해야 합니다.
공개 저장소이므로 서버 소스는 GitHub에서 보입니다. 비밀이 소스에 없는 것과 소스 자체를 비공개로 하는 것은 다른 문제입니다.

## 정리 / 되돌리기

main과 기존 프론트 파일은 건드리지 않습니다. PR을 닫으면 코드 제안만 철회됩니다.
이미 테스트 서버를 배포했다면 필요 없을 때 Cloud Run의 `richon-backend-test`만 삭제하세요.
이미지 보관 비용은 서버 삭제와 별개이므로 Artifact Registry에서 이 테스트 빌드 이미지의 정리도 확인합니다.
Neon 프로젝트 / 비밀 / 기존 프론트 / 다른 GCP 리소스를 삭제하는 스크립트는 포함하지 않습니다.

## 공식 참고 문서

- 소스 배포: https://docs.cloud.google.com/run/docs/deploying-source-code
- 빌드 계정: https://docs.cloud.google.com/run/docs/configuring/services/build-service-account
- 비밀 연결: https://docs.cloud.google.com/run/docs/configuring/services/secrets
- 비공개 서비스 점검: https://docs.cloud.google.com/run/docs/authenticating/developers
- Psycopg 연결: https://www.psycopg.org/psycopg3/docs/api/connections.html
- PostgreSQL TLS: https://www.postgresql.org/docs/current/libpq-connect.html
