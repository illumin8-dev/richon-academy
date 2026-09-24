# 리치온아카데미 / 작업·배포 지도

마지막 확인: 2026-09-24 / **CHECKPOINT-024, PR22**. 이 문서 → 최신 PR 체크포인트 → 실제 refs/클라우드 상태 순서로 확인한다. **코드 병합과 실제 서버 반영을 구분한다.**

## 사용자 6단계 표에서 현재 위치

| 순서 | 작업 | 현재 상태 |
|---|---|---|
| 1 | 원본 홈페이지 히어로 | **완료.** 원본 PR8·Pages 성공·사용자 실제 메인 확인 |
| 2 | DB008 / 최신 카카오 서버·Worker 배포 | **진행 중.** DB008 검증 완료. 새 서버는 배포 전 접근 검사에서 중단 |
| 3 | 네이버 키 서버 연결 | **진행 중.** 두 Secret의 runtime 권한·숫자버전1 준비 완료. 실제 환경변수 연결은 아직 없음 |
| 4 | 실제 계정 전체 동선 | **대기.** 신규가입·재로그인·취소·로그아웃·복귀·일반회원 관리자 접근 차단 |
| 5 | 개인정보·운영방침·탈퇴 / 검수 | **후속.** 이번에 문구·탈퇴·수집항목·보유정책 변경 없음 |
| 6 | PR10 / 명단 이관 / 결제 | **보류.** 가격·고객메모·PortOne을 로그인 문제 해결에 섞지 않음 |

## 지금 남은 장애물 — BIC 원인 확인 완료, 예외 설정은 아직

사용자 스크린샷의 **2026-09-24 10:16:28 GMT+9 / GET /apply.html / 빈 query** 이벤트는 **브라우저 무결성 검사(BIC), 차단**, User-Agent는 Python-urllib/3.12다. 실제 실패 run35942079551과 시각/경로가 대응한다. 화면에 보이는 인접 이벤트도 같은 서비스로 표시된다. 이제 국가/IP 차단을 원인으로 안내하지 않는다. BIC 내부 시그니처나 무관한 모든403까지 단정하지 않는다.

**PR22는 실제 병합했다.** backend `f50e32ce25b05f3e72d0c97d1dadf8ba29f7abb8`.
- 검증 head `b3e875e911811517ced0913002c2e4d820726f12`.
- Portal automation guards35944696028 / Login regression35944696116 모두 completed/success.
- 검사 요청에 **RichonPortalDeployCheck/1.0** User-Agent를 명시. 정상 브라우저로 위장하지 않음.
- 기존 고정6주소/GET/빈 query/쿠키·인증 미전송/redirect미추적/엄격한Access·403검사를 유지. 회귀검사5개 추가.
- 변경3파일: .github/portal/edge_ops.py, test_probe_identity.py, CLOUDFLARE_BIC.md.
- **Cloudflare 실제 규칙, DB/IAM, 서버 image/env/traffic, Worker, 홈페이지는 변경하지 않았다. 배포 요청 파일도 변경하지 않았다.** 단순 UA변경으로 BIC가 해결됐다고 하지 않는다.

## 바로 다음 실행

**DB/IAM 준비 스크립트 재실행 불필요.** 소유자가 아래 최소규칙을 검토·저장한 것을 확인한 뒤, 최신backend에서 **inspect-edge**부터 명시적으로 실행한다. 예외 저장 확인 전 실패 배포를 반복하지 않는다.

Cloudflare richonacademy.com → 보안 → 보안 규칙 → 규칙 생성 → 사용자 지정 규칙.
규칙명: `Richon deployment check - BIC only`

```text
(http.host eq "richonacademy.com"
 and http.request.method eq "GET"
 and http.request.uri.query eq ""
 and http.user_agent eq "RichonPortalDeployCheck/1.0"
 and http.request.uri.path in {"/" "/apply.html" "/auth/login" "/auth/kakao/callback" "/auth/naver/callback" "/portal/mypage"})
```

동작은 **Skip / Browser Integrity Check 하나만**. 나머지 custom/managed/rate-limit/Super Bot Fight/User Agent/Security Level skip은 선택하지 않는다. Access Bypass 추가, owner이메일정책 변경, 전역BIC해제, 미국/Azure전체 허용은 금지한다. matching request logging 유지.

**User-Agent는 누구나 복사 가능하므로 인증수단이 아니다.** 동일한 요청조건의 제3자도 BIC 하나를 건너뛸 수 있다. 다른보안·Access·원본edge key·회원인증은 계속 적용된다. POST/인가code·state query/다른주소에는 해당하지 않는다. 진단예외가 불필요해지면 이 규칙 하나를 비활성화해 철회한다. 고정egress/mTLS가 현재 있다고 가정하지 않는다.

저장확인 → inspect-edge의 auth/portal Access gateway 및 main/apply200 확인 → stage-edge-naver → 후보기동/DB008/두고정참조/원본키경계/기존100%트래픽 확인 → 별도 서비스전환 → 실계정검사. 다른제품차단이 나오면 예외를 자동 확대하지 않는다. Access로그인redirect가 owner이메일정책 내용의 검증까지 의미하지는 않는다. 현재코드에는 edge후보 자동승격이 없다.

## 이미 완료된 소유자 준비

PR20 helper source `0e1190bdbeb6b84ac325cd81d3db7bcf520aafa6` 실제 사용자 실행:
- LOGIN PREREQUISITES READY
- database_008: verified_existing
- richon-naver-client-id: verified / added:false / version1
- richon-naver-client-secret: verified / added:true / version1
- server_deployed:false

소유자 실행증거이며 제가 독립 재조회한 것과 구분한다. 이전 secret_grant_not_confirmed 및 재실행 요청은 과거 상태다. 두키값은 조회/게시하지 않는다. 다음후보의 시작시 DB008 읽기검사를 유지한다.

## 마지막 실제 클라우드 배포 시도 / PR21

- PR21 검증46731645c556a3ff5d2e189d4dfa47bae9e1d8ff / merge9724b146e43d2cdde6bd2e1d76c715b5e7eb9e0e.
- stage-edge-naver 요청608857e811663f1e1c8441e6528f10e4ecad26a4.
- run35942079551 / portal job107452142060 / failure. 상세는 [PR21 CHECKPOINT022](https://github.com/illumin8-dev/richon-academy/pull/21).
- 전체backend·임시PostgreSQL·Docker·이미지생성·모의Kakao/Naver기동·WIF인증 성공. 자동화90/Worker11개 성공.
- 제공 revision richon-portal-gh-35810692921-1 / Naver runtime binding absent. 없는·틀린원본키는403 edge_required.
- 공개6주소가 모두403. 접근검사에서 registry push/CloudRun update 전중단. 후보미생성 / serverimage·env·traffic·DB·IAM·Worker·Access변경없음.
- 이 당시 관측을 새로 조회한 최신상태로 표시하지 않는다. PR22에서는 실클라우드를 호출하지 않았다.

stage-edge-naver는 이미지와 NAVER_CLIENT_ID=richon-naver-client-id:1 / NAVER_CLIENT_SECRET=richon-naver-client-secret:1만 변경할 수 있다. --no-traffic/후보tag, 기존IAM/edge key/Kakao참조/자원제한/문서버전보존. 다른버전이 발견되면 자동덮어쓰기금지. Secret값/DB DDL/IAM쓰기는없다.

## 작업 기준선

공개홈페이지는 **marururu00/richon-academy/main**. 작업fork main과 혼동하지 않는다. 히어로는사용자가원본에병합·확인했으며 연결앱의원본쓰기권한복구와는다르다.

| 역할 | illumin8-dev/richon-academy branch |
|---|---|
| 홈페이지소스·작업지도 | main |
| 로그인·관리서버통합·배포 | **feat/backend-portal-deploy** |
| 실제Cloudflare Worker Git경로 | feat/backend-social-login |
| 기존주문서버 WIF경로 | feat/backend-gcp-deploy |
| PR10보류소스 | feat/backend-pricing-notes-oauth |

기준선5개 + 단기branch fix/login-release-prerequisites를유지. PR19/20/21/22에서최신backend로fast-forward해재사용했다. 새branch없음. WIF/Cloudflare참조branch명이름을임의변경·삭제하지않는다.

## 보존 이력 / 후속문서

- 히어로: 원본PR8 merge097f7b74f995a11ac0360c76f42b081adc5f53ae / Pages35897836106 / 사용자메인확인. 작업PR18, 기존본문·동작보존, Chromium7시나리오run35894740143.
- PR4: 백엔드mergea0ef6fc4108bf9ffa3e20901aabbf2e925a71982. 검증35893635153/35893634834/35893634316.
- PR10: 나중에진행. 소스/SQL/가격변경없음.
- PR19: cf5383dd9d5c847eda803f6737a6cc45962eccb4, merge7452fdff7a0357a44a90ff0737de61cc47f719c8. 검증35901901115/35901901506/35901901140/35901901187. startup DB008검사/숫자버전참조검사/owner준비helper.
- PR20: merge94c88af33d93ccb64e55b71a72c4af707f06e2e1. 검증35933136352/35933136699/35933136410. Secret IAM형식비교수정, --resume-grants는DDL없이읽기검증, 조건·권한내용보존, 쓰기최대1회/읽기최대5회.
- Neon연결도구의project_id오류와이후owner helper의DB008성공을혼동하지않는다.
- 첨부PDF/공식가이드대조: backend/LOGIN_RELEASE_CHECKPOINT.md. state/서버Secret/안전쿠키/provider+app+response.id식별유지. 탈퇴/revoke/세션회수·파기·국외처리·방침은후속. 전체준수/검수완료로표시하지않는다.
- branch정리run35895921493: 이전23개는archive/2026-09-24/<이전branch명>태그로복구가능. PR13/17/18은과거실행증거.

최신재개점: [PR22 CHECKPOINT-024](https://github.com/illumin8-dev/richon-academy/pull/22). 모의OAuth/CI성공을실인증성공으로표시하지않는다. 키·쿠키·인가코드·고객정보는Git/로그/artifact에저장하지않는다. Cloudflare관리커넥터는이전검색결과없음. 유료TinyFish는별도승인없이사용하지않는다.
