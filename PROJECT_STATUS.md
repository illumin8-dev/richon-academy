# 리치온아카데미 / 작업·배포 지도

마지막 확인: 2026-09-24. 이 문서 → 최신 PR 체크포인트 → 실제 GitHub/서버 상태 순서로 확인한다. 코드 병합과 운영 배포를 구분한다. 과거 PR의 당시 상태를 현재 상태로 읽지 않는다.

## 현재 완료·미완료

| 항목 | 상태 |
|---|---|
| 메인 히어로 | **완료.** 원본 marururu00 PR8 병합097f7b74f995a11ac0360c76f42b081adc5f53ae / Pages35897836106 성공 / 사용자가 실제 메인 화면 확인 |
| PR4 주문 HTTP·PostgreSQL 검사 | **완료.** 검증 후 백엔드에 병합a0ef6fc4108bf9ffa3e20901aabbf2e925a71982 |
| PR10 가격·고객 메모 | 사용자 지시로 **나중에 진행**. 소스/SQL/가격 변경하지 않음 |
| 브랜치 정리 | 23개 옛/임시 branch를 복구 태그로 보존 후 삭제. 5개 기준선 유지, 현재 PR19 임시 작업 branch 하나가 추가로 남음 |
| 카카오·네이버 배포 준비 PR19 | **코드·전체 CI 검증·병합 완료.** 병합7452fdff7a0357a44a90ff0737de61cc47f719c8 |
| DB008 / 네이버 Secret runtime 권한 | **운영 적용 확인 전.** 소유자 준비 명령 실행 필요 |
| 최신 로그인 서버 / Naver env 연결 | **미배포·미연결.** 준비 코드 병합이 실제 서버 전환은 아님 |
| 개인정보·운영방침 문구 | 사용자 지시로 후속 단계. 이번에는 수정·게시하지 않음 |

## 기준선 / 헷갈리지 않기

공개 홈페이지는 `marururu00/richon-academy/main`이다. 히어로는 이제 원본에도 반영됐다. 이전의 '원본 반영 대기'는 과거 기록이다. 사용자 직접 병합이 연결 앱 쓰기권한 복구를 의미하지는 않는다.

| 역할 | 작업 저장소 illumin8-dev/richon-academy의 branch |
|---|---|
| 홈페이지 소스·작업 지도 | `main` |
| 로그인·관리 서버 통합·배포 기준 | **`feat/backend-portal-deploy`** |
| 실제 Cloudflare Worker Git 경로 | `feat/backend-social-login` |
| 기존 주문 서버 WIF 경로 | `feat/backend-gcp-deploy` |
| PR10 보류 소스 | `feat/backend-pricing-notes-oauth` |

현재 단기 branch `fix/login-release-prerequisites`의 PR19는 병합됐다. 새로운 기능을 옛 단계별 branch 위에 계속 쌓지 않는다. 외부 WIF/Cloudflare가 참조하는 세 운영 branch 이름을 임의 변경·삭제하지 않는다.

## 현재 로그인 작업 / PR19

- 읽기 전용 실제 GCP 확인: run35899190553 / portal job107311068568. 제공 revision `richon-portal-gh-35810692921-1`, Naver runtime binding 없음, 비밀키 없음/오류 요청403 edge_required, Access gateway inconclusive. 서비스·IAM·트래픽 쓰기 없음.
- Neon describe_project와 고정 production branch SELECT가 project_id 누락 입력검사 오류로 중단됐다. 공개 도구 schema에 project_id 필드가 없어 SQL은 실행되지 않았다. 다른 입력에 SQL을 숨겨 우회하지 않는다.
- 검증 head **cf5383dd9d5c847eda803f6737a6cc45962eccb4** / 실제 병합 **7452fdff7a0357a44a90ff0737de61cc47f719c8**.
- 전체 Backend/PostgreSQL/Docker35901901115, Login·브라우저35901901506, Edge이미지35901901140, 배포가드35901901187 모두 completed/success. 최초 검사는 varchar CHECK 표현을 인식하지 못해1개 실패했고, 실제 출력의 정확한 두형식만 허용하도록 고쳐 회귀검사 포함 재실행했다.
- PR19에서 준비한 것: runtime의 pg_constraint 읽기 검사, 고정·짝지어진 숫자버전 Naver Secret 참조 검사, 소유자용 DB008+두Secret 최소권한 준비 helper, 첨부 PDF/공식 가이드 대조표.
- `backend/LOGIN_RELEASE_CHECKPOINT.md`에 쪽수/요구/구현/보류가 있다. Next.js 예제를 복사해 FastAPI 구조를 바꾸지 않았고, 문서에 있는 탈퇴/revoke/파기는 아직 별도 작업이다. 일반 공개·검수 완료로 표현하지 않는다.

## 바로 다음 행동

소유자가 기존 Cloud Shell 인증으로 검증된 고정 commit을 checkout하고 `bash ops/prepare_login_release.sh --apply`를 실행한다. `PREPARE LOGIN` 확인 이후에만 다음을 수행한다.

1. 고정 project/service/database/role/선행체크섬 검증 →008 반환경로 단일 트랜잭션 적용 또는 이미 적용됨 확인 →제한 runtime 계정의 실제 읽기 접속·권한·constraint 재검사.
2. 기존 richon-naver-client-id / richon-naver-client-secret 두 리소스에만 포털 runtime의 Secret Accessor를 추가하거나 기존권한 확인. Naver 값은 읽지 않고 활성 숫자버전을 보고한다.

성공 문구 `LOGIN PREREQUISITES READY`와 상태 JSON은 **선행조건 완료이지 서버 배포 완료가 아니다.** helper는 Cloud Run 이미지·env·트래픽, Worker, Access, WIF, 공개문서, 키값을 바꾸지 않는다. owner/runtime DB DSN은 실행프로세스 메모리에서만 처리한다. 중간 실패는 상태를 남기며 자동 역변경하지 않는다.

그 결과를 받은 뒤 실제 refs/상태를 읽고 Naver env 포함 명시적 후보 배포·검증과 전환을 준비한다. 기존 stage-edge는 이미지0% 후보만 지원하고 Naver설정/edge승격은 지원하지 않는다. 가드를 끄고 우회 배포하지 않는다. Access inconclusive를 성공으로 취급하지 않는다.

## 이후 순서

1. 히어로: 완료, 반복하지 않음.
2. 카카오·네이버: 위 DB008/Secret 준비 →Naver env 포함 서버/Worker 정합 배포 →실제 계정 신규가입/재로그인/취소/로그아웃/이전페이지복귀/관리자차단 확인.
3. 개인정보·운영방침 문구 및 실제 수집·보유·국외처리 확인. 사용자 공식 이메일/계약/보유기간은 추측하지 않음.
4. 회원탈퇴·연결해제·외부 통지·세션회수·파기 설계와 구현, 검수 자료와 일반공개 승인.
5. 재개 지시 후 PR10, 기존 명단 이관, PortOne 준비 후 결제·환불·영수증.

## 보존된 이력

히어로 작업PR18 / 실제 원본PR8. v7 이미지·문구와 기존 후기/과정/강사/푸터/신청 동작 보존, Chromium7시나리오 검증run35894740143. 브랜치 정리run35895921493, `archive/2026-09-24/<이전 branch명>` 태그로 각 tip 복구 가능. PR4 검사run35893635153/35893634834/35893634316. 과거운영기록PR13/17/18은 당시 실행 증빙이며 새작업승인을 대신하지 않는다.

단계마다 commit/검사/배포/오류와 다음 시작점을 기록한다. 실제 DB·배포는 기록만 보고 반복하지 않는다. 모의 OAuth/CI PostgreSQL 성공을 실사용자 인증 성공으로 표시하지 않는다. 키·쿠키·인가코드·고객정보를 Git/로그/artifact에 저장하지 않는다. TinyFish 유료 자동화는 별도 승인 없이 쓰지 않는다.
