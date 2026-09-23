# 로그인 서버 전용 GitHub 자동배포 / 진단

## 승인·현재 상태

사용자는 반복적인 Cloud Shell 복사/붙여넣기를 줄이기 위해 기존 주문 서버 연결은 유지하고
`richon-portal`만 대상으로 자동배포·진단을 추가하도록 승인했습니다.
기준 소스는 PR #12의 `565b02fa590fa8c7ba8e2e540fb3edd83445e887`입니다.
로그인·DB 로직·마이그레이션·기존 주문 WIF·Cloudflare 설정 파일은 수정하지 않습니다.

사용자 실행 로그에 따른 기존 상태: PORTAL PRIVATE READY, edge secret 양쪽 저장 및
Cloud Run 바인딩, Cloudflare Access/경로 연결, callback 기본 요청 로그 제외 설정 완료.
그 뒤 로그인 플래그 활성화 명령은 활성 Google 계정 없음으로 실패했다고 보고됐습니다.
이는 사용자 보고이며 이 PR에서 실제 GCP 상태를 직접 검증했다는 뜻이 아닙니다.

처음 요청 파일은 `hold`입니다. 브랜치를 만들거나 이 PR을 올리는 것만으로
GCP 인증·배포를 실행하지 않습니다. 최초 연결 스크립트는 소유자 확인 뒤에만 IAM을 수정합니다.

## 최초 1회 / 소유자 Cloud Shell

현재 로그인된 `richon-academy` 소유자 Cloud Shell에서 이 PR의 검증된 고정 커밋을
깨끗하게 checkout한 뒤 `python3 -B .github/portal/connect.py`를 실행합니다.
`CONNECT PORTAL`을 입력한 뒤에만 다음 **새 연결**을 준비합니다.

- WIF pool `richon-github-portal`, provider `github-portal`.
- 배포 계정 `richon-portal-deploy@richon-academy.iam.gserviceaccount.com`.
- 신뢰: 저장소 ID 1380040761 / 소유자 ID 251193658 / `feat/backend-portal-deploy` /
  `portal-deploy.yml` / push가 모두 일치해야 합니다.
- `richon-portal` 서비스에만 `roles/run.developer`, `roles/run.invoker`.
- 기존 `richon-portal-ci` 이미지 저장소에만 `roles/artifactregistry.writer`.
- 기존 `richon-portal` 실행 계정에만 `roles/iam.serviceAccountUser`.
- 프로젝트에는 서비스 사용을 위한 `roles/serviceusage.serviceUsageConsumer`만 추가.
- 마지막으로 위 WIF principal에 새 배포 계정의 `roles/iam.workloadIdentityUser` 부여.

Owner/Editor, 배포 계정의 Secret Accessor, 서비스 계정 JSON 키, 기존 WIF 권한 확대는 없습니다。
IAM 변경은 위의 새 연결에 필요한 항목에 한정하며 공개 접근 권한을 추가하지 않습니다.
새 runtime이나 DB 계정·비밀번호·테이블은 만들지 않습니다.

**주의:** 배포 권한을 가진 코드는 실행 계정의 DB/Secret 권한을 간접적으로 사용할 수 있습니다.
소스의 검사 코드를 악의적으로 바꾸는 경우까지 IAM이 자동으로 막는다는 뜻이 아닙니다.
지정 브랜치와 워크플로 변경 권한을 보호하고 사용자 승인 후 요청을 커밋해야 합니다.
상속된 조직 IAM 전체를 감사한 것으로 간주하지 않습니다.

연결 성공 출력: `PORTAL AUTOMATION CONNECTED`.
이는 권한 저장·재조회 완료이며 실제 GitHub OIDC 인증 성공은 다음 `inspect` 실행으로 검증합니다.
연결 실패 시 일부 새 IAM 자원이 남을 수 있습니다. 임의로 삭제하거나 재활성화하지 않습니다.

## 연결 후 / 사용자는 명령을 복사하지 않음

어시스턴트는 사용자 승인에 맞는 작업을 `.github/portal-deploy.request`에 커밋하고,
GitHub에서 해당 push 실행의 결과와 안전한 진단을 확인합니다.

```json
{"operation":"inspect","request_id":"owner-approved-check-001"}
```

| operation | 수행 범위 |
|---|---|
| hold | 클라우드 작업 없음 |
| inspect | 현재 서비스·IAM·고정 Secret 참조·제한값·직접 접근 차단 확인. 배포 없음 |
| configure-internal-login | 앞서 승인한 시험용 플래그·문서 버전만 적용. 이미지/Secret 참조는 유지 |
| deploy | 검증한 현재 브랜치의 포털 이미지를 build/push한 뒤 후보 검증 후 전환 |

작업 요청의 `request_id`는 매번 새로 지정합니다. 요청만 읽는 job은 클라우드 인증이 없습니다.
단기 자격증명은 승인한 워크플로 실행 시 발급되므로 Cloud Shell의 로그인 세션과 무관합니다.
이 저장소 default branch에 workflow_dispatch UI를 추가하지 않고 기존처럼 명시적 요청 커밋을 사용합니다.
실시간 사용자 계정 로그인/동의는 여전히 사용자가 브라우저에서 해야 합니다.

## 배포·검증과 실패

1. 현재 head와 요청을 확인합니다. 다른 저장소/소유자/브랜치/워크플로/PR 이벤트와 오래된 head는 거부.
2. 기존 backend CI(폐기 가능한 DB 포함), 자동화 가드, edge 모의검사를 통과해야 합니다.
3. deploy 모드는 Google 인증 전에 포털 Docker를 build하고 가상 설정으로 로컬 기동 검사합니다.
4. 실제 권한은 WIF로 취득하고 기존 서비스 설정을 재조회합니다.
5. 후보 리비전은 `--no-traffic`으로 만들고 기존 서비스 트래픽은 유지합니다.
6. 새 리비전 Ready, 설정 불변, 비공개 IAM, 고정 이미지, 원래 트래픽을 검증합니다.
7. 단기 ID token을 새로 받아 후보에 GET만 보냅니다. 토큰 없는 요청은 차단되어야 하고,
   IAM 인증 후에도 edge 비밀을 보내지 않아 앱의 `edge_required`(또는 OFF의 `portal_not_enabled`)를 확인합니다.
8. 검증 직후 설정과 head를 다시 확인한 뒤 후보에 100% 전환하고 태그를 제거합니다.

상태 파일은 runner 임시 디렉터리에 0600으로만 저장하고 종료 시 제거합니다.
명령 stderr/서비스 JSON/토큰/쿠키/앱 로그 원문을 GitHub 출력이나 artifact에 올리지 않습니다.
실패하면 `STOP: 단계 / 고정분류`와 최신 생성·Ready 리비전만 보고합니다.
실행 코드에 DB 직접 접속, migrations, OAuth 요청, 사용자 데이터 쓰기가 없습니다.
단, 배포된 앱 시작의 기존 read-only DB 준비 검사는 작동하며 임의 소스가 안전하다는 보증은 아닙니다.

검증 전 실패하면 이전 서비스 트래픽을 유지합니다. 후보·이미지 자동 삭제나 DB 자동 롤백은 하지 않습니다.
서비스가 이미 비정상 상태이거나 타인이 동시에 변경했으면 자동 복구 대신 중단합니다.
GitHub concurrency는 이 워크플로끼리의 충돌만 줄이며 콘솔의 동시 편집을 완전히 잠그지는 않습니다.
전환 후 추가 검사에서 실패한 경우 이전 버전으로 자동 되돌리지 않고 결과를 보고합니다.
빌드/이미지/실행 사용량 비용이 발생할 수 있습니다.

## 현재는 비공개 카카오 시험 범위

이번 자동화는 **IAM 비공개** 서비스를 대상으로 합니다. `internal-test-v1`만 허용하고
월별/수동/결제 기능, 네이버 Secret 추가, 실제 문서 승인 버전, 공개 IAM·Cloudflare Routes는 변경하지 않습니다.
공개 전환 또는 네이버 준비 후에는 확정 설정과 권한 경계를 재검토한 다음 가드를 확장합니다.
현재 연결을 공개 서비스에 몰래 재사용하거나 체크를 해제하지 않습니다.

직접 접근 차단 검사와 Ready 상태는 실제 카카오 인증·첫 가입·마이페이지·회원 권한의 종단간 시험을
대신하지 않습니다. 앱 로그인 시험은 Cloudflare 연결 및 보호 설정을 적용한 뒤 별도로 진행합니다.

## 검증 명령 / 공식 근거

`python3 -B -m unittest discover -s .github/portal -p 'test_*.py' -v`

- https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines
- https://github.com/google-github-actions/auth
- https://docs.cloud.google.com/sdk/gcloud/reference/run/services/update
- https://docs.cloud.google.com/sdk/gcloud/reference/run/services/update-traffic
- https://docs.cloud.google.com/iam/docs/roles-permissions/run
