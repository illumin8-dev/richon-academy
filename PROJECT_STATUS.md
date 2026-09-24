# 리치온아카데미 / 작업·배포 지도

최신 확인: **2026-09-24 / CHECKPOINT-034 / PR23**. 이 문서 → PR 체크포인트 → 실제 refs/서비스 상태 순서로 확인한다. 코드 병합, 후보 기동, Worker 연결, 실제 계정 인증, 일반 공개를 구분한다.

## 현재 결론

**카카오·네이버 새 후보를 기존 로그인 주소에 연결하는 Worker 배포와 배포 후 서버 검사를 완료했다. 이제 사용자가 실제 계정으로 로그인하는 단계다.** 추가 PR 병합·DB008·네이버 키 권한·BIC 규칙 설정을 반복하지 않는다.

사용자 테스트 주소: **https://richonacademy.com/auth/login**. 기존 본인 이메일 Cloudflare Access 제한을 변경하지 않았다. 무인증 검사는 예상 Access gateway까지 확인했으며, 정책의 이메일 내용이나 인증 후 실제 로그인 화면·OAuth 성공을 독립적으로 확인한 것은 아니다.

| 순서 | 작업 | 상태 |
|---|---|---|
| 1 | 메인 히어로 | 완료 / 원본 PR8·Pages·사용자 실제 화면 확인 |
| 2 | DB008 / 최신 카카오 서버·Worker | **제한 테스트용 실제 연결 완료** / DB·후보·Worker·배포 후 검사 확인 |
| 3 | 네이버 키 서버 연결 | **완료** / 사용 중인 후보에 두 Secret 버전1 연결 |
| 4 | 실제 계정 전체 동선 | **지금 진행** / 카카오부터, 이어서 네이버 신규가입·재로그인·취소·로그아웃·복귀·일반회원 관리자 차단 |
| 5 | 개인정보·운영방침·탈퇴·파기 / 검수 | 후속 / 이번에 문구나 기능을 바꾸지 않음. 일반 공개 전 정합성 확인 필요 |
| 6 | PR10 / 명단 이관 / 결제 | 사용자 지시로 보류 |

## 실제 연결 상태와 복구 기준

| 구분 | 값 |
|---|---|
| Worker 운영 branch | feat/backend-social-login |
| 현재 Worker commit | **b7f4b6d3a37c15d37b59917d73f49b1e23640e5f** |
| 연결 코드 commit | e640ec223938a057988888df58fde08383af2376 |
| Cloudflare Worker | richon-account-router |
| Cloudflare Version | **c01d6cd7-4e2c-4c53-8b51-94b2bd9a31bb** |
| Cloudflare build | 11c4ea4a-fe2f-48ea-a67c-e78dddd18b4f / completed-success / 03:31:00 UTC |
| Worker upstream | https://portal-candidate---richon-portal-amjmgyepbq-as.a.run.app |
| 연결된 후보 revision | **richon-portal-gh-35946050229-1** / Ready |
| 후보 원본 source | d0b2c7389b2394de9c6bfd110c3e7933a90d38f5 |
| 검증된 image digest | sha256:b5db98ff97299c81ff36aac7ec5e0364e5f1bf1da54af80dc38efd5783aa3495 |
| Naver 참조 | NAVER_CLIENT_ID=richon-naver-client-id:1 / NAVER_CLIENT_SECRET=richon-naver-client-secret:1 |
| 기본 Cloud Run URL | https://richon-portal-amjmgyepbq-as.a.run.app |
| 기본 URL rollback revision | richon-portal-gh-35810692921-1 / 기본 URL 트래픽100% |
| backend 작업 branch / ref | feat/backend-portal-deploy / **cefbbcf41678ff02bfe0facec077bfc0b17774fd** |

**Cloud Run 기본 URL 트래픽이 후보0%라는 것은 Worker 미연결이라는 뜻이 아니다.** 기본 URL은 이전 버전에 남겨두었지만, 실제 Worker를 통과한 허용 사용자 요청은 태그 URL로 새 후보에 전달된다. tag는 가변이므로 다른 revision으로 이동시키기 전에 이 연결을 반드시 검토한다. 후보 생성용 stage 명령을 무작정 다시 실행하지 않는다.

Rollback은 승인된 범위에서 Worker upstream을 기존 기본 URL로 복원해 배포하는 방식이다. DB·IAM·키를 자동으로 역변경하지 않는다. 후보 직접 URL은 연결키 없으면403이며 사용자 테스트 링크로 주지 않는다. 키를 브라우저·대화에 입력하도록 요청하지 않는다.

## 배포·검증 증거 / PR23

- 코드 PR23 검증 head8e2a89aca6215bdc107bb102c0214eb152894b7a / mergefc32a3b86f5715fd7050f8b33c36e76d326325b3.
- PR CI4개 성공: Backend35949781829 / Login35949782048 / Edge-image35949781838 / Automation35949781837.
- 기존 Worker209887a...에서 e640ec...로4파일만 선택 반영했다. backend 전체 역병합 없음. 기존 쿠키·캐시15개 검사 보존, 후보 경로·보안8개 추가. 정확한 Naver PNG GET 및 고정 후보호스트만 추가했다.
- e640ec... Cloudflare build113876da-ddf9-4ea2-bd4b-2f5aa11a0b17 / Version1b10b021-5ef5-485b-a4e8-16d8996b8c8b 성공.
- b7f4...는 과거 Worker boundary 검사에 승인된 진단 UA와 Accept를 맞춘 CI 보완이다. 앱 소스와 upstream은 e640과 같다. 최신 Cloudflare check107481632028 completed/success 확인.
- 실제 Worker CI: Edge-image35951577446 성공. b7f4... Backend35951737480 / boundaries35951737521 성공.
- 사전 실제 후보 조회: **35951198550 / portal107480106071**, 03:24:41 UTC 성공.
- 사후 실제 후보 조회: **35951789242 / portal107481911249**, 03:33:10 UTC 성공. sourcecefbbcf41678ff02bfe0facec077bfc0b17774fd.
- 사후: 고정후보·두revision·Ready·runtime·tag·두Naver참조1·이미지source/digest·기본100% 유지 확인. auth/login·kakao/callback·naver/callback·portal/mypage302 / main·apply200. 원본과 후보의 없는·틀린 연결키는403 edge_required. 서비스·IAM·트래픽 재조회 불변.
- 해당 작업의 자동화108개 / Worker15개와 전체backend·임시PostgreSQL·Docker검사 통과. CI에 찍히는 모의403/실패예제를 실제 장애로 혼동하지 않는다.

### 도중 발견한 검사 오류

서비스 API는 컨테이너 name 미기재, 고정 Revision API는 portal-1 자동이름으로 조회됐다(실제run35950905055). rawspec 직접 비교가 이 표기차이를 오류처리했다. 한 후보/한컨테이너/정확한absent→portal-1쌍만 보정하고 다른필드·명시이름·의존성·배포전후 비교는 유지했다. 회귀4개 추가 후 사전·사후 실제검증 성공. 범용 이름정규화 helper는 저장되지 않았으며 사용하지 않는다.

실제 Worker의 과거 edge-rollout-check.yml만 기본 Python UA가 남아 BIC403이었다(run35951577451). 기존 엄격한 판정은 유지하고 소유자가 허용한 동일6주소/GET/빈query/진단 UA를 적용한 후 성공했다. 403을 PASS로 취급하거나 새 방화벽 예외를 만들지 않았다.

## 바로 다음 행동

사용자는 기존 /auth/login을 새로 열고 Cloudflare 인증을 거쳐 카카오부터 확인한다. 카카오 인증 → 처음이면 가입동의 → 리치온 복귀 → 세션유지를 확인하고, 이후 네이버로 같은 흐름을 확인한다. 오류는 화면 본문만 받는다. code/state가 포함된 주소·Cookie·Secret·고객 개인정보는 요청하지 않는다.

정상 로그인을 실제로 확인하기 전 검수통과/일반공개완료로 표시하지 않는다. 다음 기능을 마구 추가하지 않고 취소·재로그인·로그아웃·이전페이지 복귀·권한 차단을 확인한다. 개인정보 문구·탈퇴/연결해제·물리적 파기·국외처리 정합성은 사용자와 별도 확정해 진행한다. 기존 명단/PR10/결제는 지금 섞지 않는다.

## 이미 완료된 설정 / 반복 금지

- PR20 helper source0e1190bdbeb6b84ac325cd81d3db7bcf520aafa6: LOGIN PREREQUISITES READY / database_008 verified_existing / 두Naver runtime grant verified / version1. owner 출력과 이후 후보기동검증이 있다.
- 후보 생성은 run35946050229에서 완료. 새후보 시작점 portal_readiness가 제한DB접속·권한·008반환경로 catalog를 읽기 검증 후 실행한다.
- BIC 원인은 사용자 Security Events의 Browser Integrity Check였다. 현재 public UA RichonPortalDeployCheck/1.0, 정확한6GET·빈query에 BIC만Skip하는 소유자규칙 사용. UA는 인증수단이 아니며 누구나복사할수있다. Access·WAF·속도제한을 끄지 않는다. 이번 규칙확대 없음.
- Access gateway302는 접근제한 진입 증거이지 이메일정책내용 전체의 독립검증이 아니다.

## 작업 저장소·브랜치 구분

공개 홈페이지: **marururu00/richon-academy/main**. 작업 fork main과 혼동하지 않는다. 사용자 직접 원본PR8을 병합했다고 연결앱 원본쓰기권한도 복구됐다고 가정하지 않는다.

| 역할 | illumin8-dev/richon-academy branch |
|---|---|
| 홈페이지소스 / 이 작업지도 | main |
| 로그인·관리서버통합 / GCP작업 | feat/backend-portal-deploy |
| 실제 Cloudflare Worker Git배포 | feat/backend-social-login |
| 기존 주문서버 WIF호환 경로 | feat/backend-gcp-deploy |
| PR10 보류 초안 | feat/backend-pricing-notes-oauth |

단기branch fix/login-release-prerequisites는 최신backend기준 PR23에 재사용했다. 기존PR들은 merge상태와 운영반영상태를 구분한다. WIF/Cloudflare가 연결한 branch를 임의 이름변경·삭제하지 않는다.

## GitHub 쓰기 문제 대응

**[GITHUB_WRITE_RECOVERY.md](GITHUB_WRITE_RECOVERY.md)**를 참고한다. 기존 illumin8-dev 연결에서 실제 쓰기를 재확인했고 이번 작업도 같은계정으로 완료했다. 도구노출과 앱/API권한, 원본저장소403과Cloudflare403을 구분한다. 필요한 함수 정확히조회 → 최신대상/blob확인 → 승인범위쓰기 → commit재조회 순서. 명시적 권한·안전거절을 우회하지 않는다. 도구목록이빈것만으로 권한을넓히거나 재연결을요구하지 않는다.

## 보존 이력과 근거

- [PR23 / CHECKPOINT029~034](https://github.com/illumin8-dev/richon-academy/pull/23): 이번진단·배포·검증·남은작업.
- [PR22 / CHECKPOINT027](https://github.com/illumin8-dev/richon-academy/pull/22#issuecomment-5806256318): 최초후보배포와BIC해결 당시기록. 'Worker연결아직'은과거상태.
- 히어로 원본PR8 merge097f7b74f995a11ac0360c76f42b081adc5f53ae / Pages35897836106 / 사용자확인. 작업PR18, Chromium7개검사.
- PR4 주문HTTP·PostgreSQL검사 병합a0ef6fc4108bf9ffa3e20901aabbf2e925a71982. PR10은나중.
- PR19 준비 / PR20 권한표현비교수정 / PR21 후보배포 / PR22 BIC진단 / PR23 실제연결 순서.
- 첨부PDF·공식가이드별 대조: backend/LOGIN_RELEASE_CHECKPOINT.md, backend/PROVIDER_REVIEW_AUDIT.md. 서버측Secret/state/안전쿠키/provider+app+response.id식별은보존. 탈퇴/revoke/세션회수·파기·정책·검수는후속이다.
- 옛branch는 archive/2026-09-24/<이전branch명>태그로보존했다. 모든과거PR을다시합치지않는다.

이번 실제 변경은 Worker연결 및 관련검사/기록이다. CloudRun image/기본traffic/DB/IAM/키값/Access/메인/방침/탈퇴/#10/결제는변경하지않았다. 비밀값·쿠키·인가코드·고객정보를Git/로그/artifact에저장하지않는다. TinyFish미사용. 이후작업은최신실제상태와사용자결과부터확인한다.
