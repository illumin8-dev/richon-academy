# GitHub → GCP 비공개 테스트 배포

## 이번 범위

- 작업 저장소: `illumin8-dev/richon-academy` (기존 작업용 포크).
- 전용 브랜치: `feat/backend-gcp-deploy`.
- 대상: GCP `richon-academy` / `asia-southeast1` / 기존 서비스 `richon-backend-test` 한 곳.
- 프론트, 원본 `marururu00/richon-academy`, main, DB 스키마·고객정보·결제 기능은 변경하지 않습니다.
- GCP 계정 로그인은 ChatGPT/GitHub 연결과 별개이므로 최초 GCP 권한 설정은 프로젝트 소유자의 Cloud Shell에서 실행합니다.

## 한 번만 실행할 설정

검토한 커밋으로 체크아웃한 뒤 Cloud Shell에서 다음을 실행합니다.

```bash
python3 .github/gcp/connect.py
```

대상 확인 뒤 `CONNECT`를 입력해야 변경을 시작합니다. 그 전에는 메타데이터만 읽습니다.
성공 메시지 `SETUP READY`는 권한 저장·조회 완료이지, GitHub OIDC 로그인·실제 배포 성공을 뜻하지 않습니다.
기존 이름의 리소스가 예상 설정과 다르거나 비활성화되어 있으면 덮어쓰거나 재활성화하지 않고 멈춥니다.
IAM 전파 지연에는 제한된 재시도를 합니다. 일부 단계가 성공한 뒤 실패해도 리소스를 자동 삭제하지 않습니다.

## 인증 및 권한

장기 서비스 계정 키를 만들거나 GitHub Secrets에 비밀번호를 저장하지 않습니다.
Workload Identity Federation이 아래 조건을 모두 만족하는 GitHub OIDC 토큰만 수용합니다.

- repository ID `1380040761`, owner ID `251193658`.
- ref `refs/heads/feat/backend-gcp-deploy`.
- workflow `.github/workflows/backend-deploy-test.yml`의 해당 브랜치 버전.
- event `push`만 허용. 외부 포크, PR 이벤트, 다른 브랜치와 워크플로는 수용하지 않음.

전용 계정 `richon-github-deploy`에 주는 권한:

| 범위 | 역할 |
|---|---|
| 기존 Cloud Run 테스트 서비스 한 개 | `roles/run.developer`, `roles/run.invoker` |
| 전용 Artifact Registry `richon-backend-ci` | `roles/artifactregistry.writer` |
| 기존 런타임 계정 `richon-backend` | `roles/iam.serviceAccountUser` |
| 프로젝트 | `roles/serviceusage.serviceUsageConsumer` |
| 배포 계정에 대한 제한된 WIF 주체 | `roles/iam.workloadIdentityUser` |

Owner/Editor, Secret Accessor, Cloud Build 실행, 프로젝트 IAM 수정 권한은 배포 계정에 부여하지 않습니다.
**다만 배포 권한자는 런타임 계정으로 실행될 코드를 변경할 수 있으므로, 런타임의 기존 DB 접근도 간접적으로 사용할 수 있습니다.**
따라서 해당 브랜치의 쓰기 권한자를 신뢰해야 합니다. 이 PR은 GitHub 보호 규칙을 설정하지 않습니다.
운영 배포로 확대하기 전 branch/environment 승인 보호와 DB 런타임 최소권한을 별도로 확정해야 합니다.

## 연결 후 배포 실행

사용자가 SETUP READY를 확인하면, 승인된 작업만 담긴 전용 브랜치에서 `.github/test-deploy.request`를 생성/갱신하는 요청 커밋을 만듭니다.
이 파일은 현재 PR에 일부러 포함하지 않았습니다. 지금은 실제 GCP 작업이 시작되지 않습니다.
요청 파일 변경을 감지하는 push 트리거이므로 default branch 병합이나 workflow_dispatch 설정이 필요하지 않습니다.
일반 소스 변경과 PR만으로는 배포하지 않습니다. 향후 배포도 검토·승인된 코드에 대해 별도의 요청 커밋으로 실행합니다.

1. 같은 커밋의 기존 CI를 재사용: PostgreSQL 임시 DB 테스트 / 업로드 목록 / Docker 빌드.
2. 클라우드 자격 증명이 생기기 전에 Docker 이미지를 생성.
3. WIF 인증 후 기존 서비스의 비공개 설정 / 런타임 / 숫자로 고정된 DB 비밀 버전 / 인스턴스 제한 확인.
4. 전용 이미지 저장소에 push, 태그가 아닌 digest로 후보 리비전을 배포 (`--no-traffic`).
5. 후보에서 익명 접근 차단 / 인증된 `/health`, 읽기 전용 `/health/db` 확인.
6. 후보 리비전과 이미지가 바뀌지 않았는지 다시 확인한 후 테스트 서비스 트래픽 전환.

기존 비밀 버전·환경변수·런타임 계정·스케일 설정은 재설정하지 않습니다. 실제 고객/주문 쓰기나 마이그레이션은 실행하지 않습니다.
후보 점검 실패 시 트래픽 전환 단계는 실행하지 않습니다. 이미 올라간 후보와 이미지가 자동 삭제되지는 않습니다.
트래픽 전환 자체가 실패하면 실제 상태를 확인해야 합니다. 모든 실패에 자동 rollback을 약속하는 구성은 아닙니다.
기존 수동 Cloud Build 스크립트와 달리 빌드는 GitHub에서 하고, GCP에는 이미지를 배포합니다.
이미지 보관·Cloud Run 사용량은 별도 과금될 수 있으며 이번 PR은 자동 삭제 정책을 적용하지 않습니다.

## 중단 / 철회

GCP IAM의 워크로드 아이덴티티 연합에서 `richon-github-test` 풀 또는 `github-test` 제공자를 비활성화하면 새 토큰 발급을 막습니다.
이미 발급된 단기 토큰은 만료 전까지 유효할 수 있습니다. 긴급 차단은 배포 계정 비활성화·리소스 권한 철회도 검토합니다.
중단만 필요하면 GitHub Actions의 `Deploy private Richon test backend` 워크플로를 비활성화할 수도 있습니다.
기존 DB, Secret Manager 비밀, 실행 중인 서비스를 삭제할 필요는 없습니다.

## 검증 경계

로컬/CI 안전장치 테스트는 실제 GCP API나 OIDC 왕복 인증 검증을 대신하지 않습니다.
최초 소유자 설정과 실제 GitHub 배포 실행이 성공하기 전에는 연결·배포 완료로 판정하지 않습니다.

## 공식 근거

- https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines
- https://github.com/google-github-actions/auth
- https://docs.cloud.google.com/run/docs/reference/iam/roles
- https://docs.cloud.google.com/run/docs/rollouts-rollbacks-traffic-migration
- https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows
