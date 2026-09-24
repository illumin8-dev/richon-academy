# 리치온아카데미 / 작업·배포 지도

마지막 확인: 2026-09-24 / CHECKPOINT-022. 이 문서 → 최신 PR 체크포인트 → 실제 GitHub/서버 상태 순서로 확인한다. 코드 병합과 운영 배포를 구분한다. 과거 PR의 당시 상태를 현재 상태로 읽지 않는다.

## 사용자 6단계 표에서 현재 위치

| 순서 | 작업 | 현재 상태 |
|---|---|---|
| 1 | 원본 저장소 접근 확인 → 히어로 배포 | **완료.** 원본 PR8 병합·Pages 성공·사용자 실제 화면 확인 |
| 2 | DB008 상태 확인 → 최신 카카오 서버·Worker 배포 | **진행 중 / 배포 전 접근 확인에서 중단.** DB008 verified_existing, 코드/이미지 검사 성공. 최신 서버와 Worker 정합 배포는 미완료 |
| 3 | 이미 저장한 네이버 키를 서버에 연결 | **진행 중.** 두 Secret 권한·버전1 준비 완료. 서버 환경변수 연결은 아직 없음 |
| 4 | 실제 계정으로 전체 동선 확인 | **대기.** 신규가입·재로그인·취소·로그아웃·복귀·일반회원 권한 차단의 실제 통합 시험 필요 |
| 5 | 개인정보 안내·운영방침·회원탈퇴 정리 → 검수·공개 | 사용자 지시대로 후속 작업. 이번에는 문구 수정·게시 또는 탈퇴 기능 변경 없음 |
| 6 | 이후 PR10 / 관리자 운영·명단 이관 / 결제 | **보류.** 가격·고객 메모·명단·PortOne 결제는 이번 작업에 섞지 않음 |

## 바로 다음 할 일 — Cloudflare 차단 원인 확인

**DB/IAM 준비를 다시 실행할 필요 없다. 새 PR을 무조건 병합하거나 실패 배포를 반복하지 않는다.**

실제 배포 workflow35942079551 / portal job107452142060에서 2026-09-24 01:16:28 UTC(10:16:28 KST)에 홈페이지 경유6주소가 모두403이었다. 새 후보 생성 전 `access_gateway_not_confirmed`로 중단됐다.

Cloudflare 해당 도메인의 보안 Analytics → Events에서 이 시각의 GET /auth/login을 우선 확인한다. 필요한 것은 적용 서비스, 규칙명/규칙ID, Action, 국가, 시각이다. 쿠키·Authorization·Client Secret·인가code/state는 필요하지 않다. 기록이 안 보이면 시간대·샘플링·원본응답 여부도 확인한다.

국가/IP/자동화·봇 제한은 가설이며 실제 규칙은 아직 확인되지 않았다. CF-Ray 헤더 존재만으로 어떤 보안 제품이403을 생성했는지 확정하지 않는다. 전체 방화벽·봇보호·owner-only Access를 끄거나403을 성공으로 취급하지 않는다. 원인을 확인하고 최소 변경 범위를 정한 뒤 후보 배포를 다시 진행한다.

후보 배포 다음은 기동·DB008·고정Naver참조·앱경계·기존100%트래픽 보존 확인 → 서비스 전환 → 실제 계정 테스트다. 현재 edge 작업 코드에는 자동승격이 없다.

## 실제 배포 시도 결과 / PR21

- 검증 head: `46731645c556a3ff5d2e189d4dfa47bae9e1d8ff`.
- 실제 backend 병합: `9724b146e43d2cdde6bd2e1d76c715b5e7eb9e0e`.
- 명시적 stage-edge-naver 요청: `608857e811663f1e1c8441e6528f10e4ecad26a4`.
- 실제 workflow: https://github.com/illumin8-dev/richon-academy/actions/runs/35942079551
- portal job:107452142060 / completed/failure. 이 로그를 직접 읽었다.
- 전체 backend·폐기용 PostgreSQL·Docker 검사 성공. Portal 자동화90개/Worker11개 성공, 최신 포털 이미지 생성·모의 Kakao/Naver 기동 검사 성공.
- 단기 GitHub→GCP WIF 인증, 실제 서비스/IAM/설정 조회 성공.
- 조회된 실제 제공 revision: `richon-portal-gh-35810692921-1`. Naver runtime binding: absent.
- 원본 서버에 연결키 없음/잘못된키 요청은 모두 정확한403 edge_required로 거절됐다.
- /auth/login, /auth/kakao/callback, /auth/naver/callback, /portal/mypage, /, /apply.html 모두403. 모두CF-Ray존재/CF-Mitigated:challenge표시없음. 원문 헤더·본문·쿠키·쿼리는 기록하지 않음.
- 서비스/IAM/트래픽의 변경 없음도 중단 직전 읽기 확인했다. stage()의 접근 확인에서 멈춰 레지스트리push/Cloud Run update를 실행하지 않았다. **후보revision 미생성, 서버image/env/traffic·DB·IAM·Worker·Access 변경 없음.**
- 코드CI Backend35941787122 / Login·브라우저35941787496 / 배포가드35941787161 성공 후 PR21병합. 이미지 빌드나 모의 테스트 성공은 실제 배포·사용자OAuth성공이 아니다.

### 이번에 추가한 배포 기능

stage-edge-naver는 새 이미지와 아래 두 고정 Secret 참조만 설정할 수 있다.
- NAVER_CLIENT_ID → richon-naver-client-id:1
- NAVER_CLIENT_SECRET → richon-naver-client-secret:1

--no-traffic·지정후보tag를 사용하며 기존 IAM/edge key/Kakao참조/자원제한/문서버전은 그대로여야 한다. 이미 다른 Naver버전이 있으면 자동 덮어쓰지 않는다. Secret payload/DB DDL/IAM 쓰기는 이 배포에 없다. 기존 private/stage-edge 검사는 유지한다. Access 미확인을 성공 처리하지 않는다.

## 이미 완료된 소유자 준비 / 반복하지 않기

사용자가 검증된 PR20 helper source `0e1190bdbeb6b84ac325cd81d3db7bcf520aafa6`을 실행해 다음 결과를 전달했다.
- LOGIN PREREQUISITES READY
- database_008: verified_existing
- richon-naver-client-id: verified / added:false / version:1
- richon-naver-client-secret: verified / added:true / version:1
- server_deployed:false

이는 실제 소유자 실행 결과다. 제가 별도 운영DB/IAM을 독립 재조회한 것과는 구분한다. 첫 Secret의 권한은 이미 있었고 둘째만 추가됐다. 이전 secret_grant_not_confirmed 상태나 '준비 스크립트 재실행 필요' 안내는 이제 과거 기록이다.

PR20은 빈 IAM정책의 version생략/0과 명시적1을 같은 권한으로 비교하도록 수정하고, 실제 binding/member/조건/audit/unknown 필드는 보존했다. --resume-grants는 기존008읽기검증만 하며 migration함수를 호출하지 않는다. 각Secret쓰기 최대1회, 정확한 이전정책만 보일 때 읽기재시도 최대5회다. 이 준비와 서버배포는 별개다.

## 기준선 / 헷갈리지 않기

공개 홈페이지는 **marururu00/richon-academy/main**이다. 작업 저장소main과 혼동하지 않는다. 히어로의 '원본 반영 대기'는 과거 기록이다. 사용자 직접 병합이 연결앱 쓰기권한 복구를 의미하지는 않는다.

| 역할 | 작업 저장소 illumin8-dev/richon-academy의 branch |
|---|---|
| 홈페이지 소스·작업 지도 | main |
| 로그인·관리 서버 통합·배포 기준 | **feat/backend-portal-deploy** |
| 실제 Cloudflare Worker Git 경로 | feat/backend-social-login |
| 기존 주문 서버 WIF 경로 | feat/backend-gcp-deploy |
| PR10 보류 소스 | feat/backend-pricing-notes-oauth |

23개 옛/임시branch를 복구태그로 보존 후 삭제했다. 기준선5개와 단기branch fix/login-release-prerequisites를 유지한다. 단기branch는 PR19/20/21에서 최신backend를 기준으로 재사용했고 모두 병합됐다. 외부 WIF/Cloudflare가 참조하는 운영branch 이름을 임의 변경·삭제하지 않는다.

## 완료 이력·후속 문서

- 히어로: 원본marururu00 PR8 병합097f7b74f995a11ac0360c76f42b081adc5f53ae / Pages35897836106성공 / 사용자 실제메인확인. 기존 후기/과정/강사/푸터/신청동작 보존, Chromium7시나리오run35894740143.
- PR4 주문HTTP·PostgreSQL검사: 검증후백엔드병합a0ef6fc4108bf9ffa3e20901aabbf2e925a71982. 검사run35893635153/35893634834/35893634316.
- PR10가격·고객메모: 사용자지시로 나중에 진행. 코드/SQL/가격변경하지 않음.
- PR19검증cf5383dd9d5c847eda803f6737a6cc45962eccb4 / merge7452fdff7a0357a44a90ff0737de61cc47f719c8. Backend35901901115 / Login35901901506 / Edge35901901140 / 배포가드35901901187성공. startup DB008읽기검사·숫자버전Naver검사·owner준비helper·문서대조표 포함.
- PR20merge94c88af33d93ccb64e55b71a72c4af707f06e2e1. Backend35933136352 / Login35933136699 / Edge35933136410성공. 당시 수정의 세부증거는 PR20 CHECKPOINT018.
- Neon describe_project/production SELECT는 project_id입력스키마오류로 실행되지 않았다. 이후사용자owner helper의DB008성공과 혼동하지 않는다.
- 첨부PDF/공식가이드 쪽수별 대조는 backend/LOGIN_RELEASE_CHECKPOINT.md. 서버 Secret/state/안전한쿠키/response.id식별 등 기존구현·회귀검사를 유지한다. 회원탈퇴/revoke/세션회수·파기·국외처리·운영방침은 후속이다. PDF문서전체준수·검수완료로 표시하지 않는다.
- 브랜치정리run35895921493, archive/2026-09-24/<이전branch명> 태그로 복구가능. 과거PR13/17/18은 당시증거이며 새작업승인을 대신하지 않는다.

최신 재개 기록: [PR21 CHECKPOINT-022](https://github.com/illumin8-dev/richon-academy/pull/21). 단계마다commit/검사/배포/오류/다음시작점을 기록한다. 실제DB·배포는 기록만 보고 반복하지 않는다. 모의OAuth/CI PostgreSQL성공을 실사용자인증성공으로 표시하지 않는다. 키·쿠키·인가코드·고객정보를 Git/로그/artifact에 저장하지 않는다. Cloudflare관리 커넥터 검색은 결과없음. TinyFish유료자동화는 별도승인없이 사용하지 않는다.
