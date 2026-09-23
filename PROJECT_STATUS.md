# 리치온아카데미 / 작업·배포 지도

마지막 확인: 2026-09-24 / CHECKPOINT-018. 이 문서 → 최신 PR 체크포인트 → 실제 GitHub/서버 상태 순서로 확인한다. 코드 병합과 운영 배포를 구분한다. 과거 PR의 당시 상태를 현재 상태로 읽지 않는다.

## 현재 완료·미완료

| 항목 | 상태 |
|---|---|
| 메인 히어로 | **완료.** 원본 marururu00 PR8 병합097f7b74f995a11ac0360c76f42b081adc5f53ae / Pages35897836106 성공 / 사용자가 실제 메인 화면 확인 |
| PR4 주문 HTTP·PostgreSQL 검사 | **완료.** 검증 후 백엔드에 병합a0ef6fc4108bf9ffa3e20901aabbf2e925a71982 |
| PR10 가격·고객 메모 | 사용자 지시로 **나중에 진행**. 소스/SQL/가격 변경하지 않음 |
| 브랜치 정리 | 23개 옛/임시 branch를 복구 태그로 보존 후 삭제. 5개 기준선 유지. PR19의 단기 branch를 PR20에 재사용, 새 branch 추가 없음 |
| 카카오·네이버 배포 준비 PR19 | **코드·전체 CI 검증·병합 완료.** 병합7452fdff7a0357a44a90ff0737de61cc47f719c8 |
| DB008 | **사용자 실행 출력 verified.** owner와 제한계정 검증 후 상태. 제가 이번에 운영 DB를 독립 재조회한 것은 아님. 다시 미적용으로 간주하지 않음 |
| 네이버 Secret runtime 권한 | 첫 richon-naver-client-id grant 시도 후 readback 비교에서 중단. 실제 적용됐을 수 있음. 둘째 처리는 시작 전. 완료판정 보류 |
| 권한 확인 코드 PR20 | **수정·CI·병합 완료.** backend94c88af33d93ccb64e55b71a72c4af707f06e2e1. 새 고정소스로 --resume-grants 실행 필요 |
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

단기 branch `fix/login-release-prerequisites`는 PR19에 이어 PR20에서 재사용했고 둘 다 병합됐다. 새로운 기능을 옛 단계별 branch 위에 계속 쌓지 않는다. 외부 WIF/Cloudflare가 참조하는 세 운영 branch 이름을 임의 변경·삭제하지 않는다.

## 현재 로그인 작업 / PR20

사용자가 PR19 고정소스를 실행한 결과는 `database_008:verified`, 첫 Naver Secret `grant_attempted`, `secret_grant_not_confirmed`, `server_deployed:false`였다. DB DDL을 무작정 반복하지 않는다. 첫 권한 추가 명령 이후 비교에서 멈춘 상태이므로 권한 자체가 없다고 단정하지 않는다.

- 기존 helper가 버전 생략/0과 명시적1인 동일권한 응답을 다르게 판단하는 조건을 재현했다. 실제 사용자 IAM 전후 응답은 확인하지 못했으므로 운영원인 단독 확정은 아니다.
- PR20: Secret 전용 비교에서 유효한 기본 metadata만 정규화. 실제 binding/member/조건/audit/unknown 필드는 유지. 조건이 숨겨진 표현·비정상 version은 거부한다. common의 Cloud Run 정책 검사는 그대로다.
- 정확한 이전 정책만 보일 때 최대5번 읽기 재시도. 각 Secret 쓰기는 최대1번. 다른 정책변경은 즉시 중단한다.
- `--resume-grants`는 기존008의 checksum/CHECK/제한계정을 읽기 검증하며 **migration 함수를 호출하지 않는다.** 있는 권한은 건너뛰고 없는 두 Secret runtime 권한만 처리한다.
- 검증 head **0e1190bdbeb6b84ac325cd81d3db7bcf520aafa6** / 실제 병합 **94c88af33d93ccb64e55b71a72c4af707f06e2e1**.
- Backend/PostgreSQL/Docker35933136352, Login·브라우저35933136699, Edge이미지35933136410 모두 completed/success. 새 회귀검사 포함. 실제 GCP IAM·사용자 OAuth 성공을 뜻하지 않음.
- 셸 기본 프로젝트가 달라도 helper의 모든 요청은 `--project=richon-academy`, 계정은 richon 소유자로 고정된다. mybutour 프로젝트 기본설정을 바꿀 필요 없다.

## 바로 다음 행동

소유자가 기존 Cloud Shell 인증으로 **0e1190bdbeb6b84ac325cd81d3db7bcf520aafa6**을 새 임시 checkout에 받아 다음을 실행한다:

```bash
bash ops/prepare_login_release.sh --apply --resume-grants
```

`PREPARE LOGIN` 확인 후 DB는 읽기검사만 하고 기존 richon-naver-client-id / richon-naver-client-secret 두 리소스에만 포털 runtime의 Secret Accessor를 추가하거나 기존권한을 확인한다. Naver 값은 읽지 않고 활성 숫자버전을 보고한다. 이미 있는 grant는 재추가하지 않는다. DB008이 없거나 다르면 변경 없이 중단한다.

성공 문구 `LOGIN PREREQUISITES READY`와 상태 JSON의 두 grant verified / DB verified_existing는 **선행조건 완료이지 서버 배포 완료가 아니다.** `server_deployed:false`는 이 단계에서 정상이다. helper는 Cloud Run 이미지·env·트래픽, Worker, Access, WIF, 공개문서, 키값을 바꾸지 않는다. owner/runtime DB DSN은 실행프로세스 메모리에서만 처리한다. 중간 실패는 상태를 남기며 자동 역변경하지 않는다.

결과를 받은 뒤 실제 refs/상태를 읽고 Naver env 포함 명시적 후보 배포·검증과 전환을 준비한다. 기존 stage-edge는 이미지0% 후보만 지원하고 Naver설정/edge승격은 지원하지 않는다. 가드를 끄고 우회 배포하지 않는다. Access inconclusive를 성공으로 취급하지 않는다.

## 선행 검증·실서버 관측 이력

- 읽기 전용 실제 GCP run35899190553 / portal job107311068568: revision richon-portal-gh-35810692921-1, Naver runtime binding 없음, 비밀키 없음/오류403 edge_required, Access gateway inconclusive. 이번 PR20에서 GCP를 새로 조회하지 않음.
- Neon describe_project와 production SELECT는 project_id 입력검사 오류로 실행되지 않았다. 사용자 owner helper의 DB008 verified 결과와 구분한다.
- PR19 검증cf5383dd9d5c847eda803f6737a6cc45962eccb4 / merge7452fdff7a0357a44a90ff0737de61cc47f719c8. Backend35901901115, Login35901901506, Edge35901901140, 배포가드35901901187 성공. 초기 varchar CHECK 표현 실패는 수정 후 재검증했다.
- PR19에서 준비한 runtime pg_constraint 검사, 숫자버전 Naver 참조 검사, owner 준비 helper, PDF/공식 가이드 대조표는 유지한다. `backend/LOGIN_RELEASE_CHECKPOINT.md`에 쪽수/요구/구현/보류가 있다. 탈퇴/revoke/파기는 별도 작업이며 일반공개·검수완료로 표시하지 않는다.

## 이후 순서

1. 히어로: 완료, 반복하지 않음.
2. 카카오·네이버: 위 IAM 재개 →Naver env 포함 서버/Worker 정합 배포 →실제 계정 신규가입/재로그인/취소/로그아웃/이전페이지복귀/관리자차단 확인.
3. 개인정보·운영방침 문구 및 실제 수집·보유·국외처리 확인. 사용자 공식 이메일/계약/보유기간은 추측하지 않음.
4. 회원탈퇴·연결해제·외부 통지·세션회수·파기 설계와 구현, 검수 자료와 일반공개 승인.
5. 재개 지시 후 PR10, 기존 명단 이관, PortOne 준비 후 결제·환불·영수증.

## 보존된 이력

히어로 작업PR18 / 실제 원본PR8. v7 이미지·문구와 기존 후기/과정/강사/푸터/신청 동작 보존, Chromium7시나리오run35894740143. 브랜치 정리run35895921493, archive/2026-09-24/<이전 branch명> 태그로 각 tip 복구 가능. PR4 검사run35893635153/35893634834/35893634316. 과거운영기록PR13/17/18은 당시 실행 증빙이며 새작업승인을 대신하지 않는다.

최신 복구 기록은 PR19 CHECKPOINT-017과 [PR20 CHECKPOINT-018](https://github.com/illumin8-dev/richon-academy/pull/20)이다. 단계마다 commit/검사/배포/오류와 다음 시작점을 기록한다. 실제 DB·배포는 기록만 보고 반복하지 않는다. 모의 OAuth/CI PostgreSQL 성공을 실사용자 인증 성공으로 표시하지 않는다. 키·쿠키·인가코드·고객정보를 Git/로그/artifact에 저장하지 않는다. TinyFish 유료 자동화는 별도 승인 없이 쓰지 않는다.
