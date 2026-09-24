# 리치온아카데미 / 작업·배포 지도

마지막 확인: 2026-09-24 / **CHECKPOINT-027, PR22**. 이 문서 → 최신 체크포인트 → 실제 refs/클라우드 상태 순서로 확인한다. 코드 병합, 후보 배포, 기존 주소의 트래픽 전환, 실제 OAuth 성공을 구분한다.

## 사용자 6단계 표에서 현재 위치

| 순서 | 작업 | 현재 상태 |
|---|---|---|
| 1 | 원본 홈페이지 히어로 | **완료.** 원본 PR8·Pages 성공·사용자 실제 메인 확인 |
| 2 | DB008 / 최신 카카오 서버·Worker 배포 | **새 후보 서버 실제 배포·기동 검증 완료. 기존 로그인 주소 전환은 아직.** DB008 준비 반복 불필요 |
| 3 | 네이버 키 서버 연결 | **후보 서버에 두 Secret 버전1 연결 완료.** 기존 제공 버전은 그대로여서 사용자 로그인 주소에는 아직 미반영 |
| 4 | 실제 계정 전체 동선 | **대기.** 신규가입·재로그인·취소·로그아웃·복귀·일반회원 관리자 차단의 실제 OAuth 시험 전 |
| 5 | 개인정보·운영방침·탈퇴 / 검수 | **후속.** 이번 문구·탈퇴·수집항목·보유정책 변경 없음 |
| 6 | PR10 / 명단 이관 / 결제 | **보류.** 가격·고객메모·PortOne을 로그인 문제 해결에 섞지 않음 |

## 지금 실제 서버 상태

| 구분 | revision / 상태 |
|---|---|
| 기존 서비스주소 제공 | `richon-portal-gh-35810692921-1` / 기존100% 트래픽 유지 |
| 새 카카오·네이버 후보 | **`richon-portal-gh-35946050229-1`** / Ready / 서비스주소 트래픽0% |
| 후보 tag | `portal-candidate` |
| 후보 source | `d0b2c7389b2394de9c6bfd110c3e7933a90d38f5` |
| Naver 후보 참조 | NAVER_CLIENT_ID → richon-naver-client-id:1 / NAVER_CLIENT_SECRET → richon-naver-client-secret:1 |
| 현재 backend 작업 ref | feat/backend-portal-deploy / d0b2c7389b2394de9c6bfd110c3e7933a90d38f5 |

**새 후보를 실제로 만들었다. 이전의 'BIC로 후보 생성 전 중단'은 이제 과거 상태다. 그러나 기존 로그인 주소를 새 버전으로 전환하거나 실제 계정 인증을 완료한 것은 아니다.**

## 이번 실행 증거

### BIC 규칙 저장 후 읽기 검사

사용자 화면에서 `Richon deployment check - BIC only` / Skip / 활성 상태를 확인했다. 목록 화면만으로 전체 표현식과 Skip checkbox를 독립 검증한 것은 아니다.

- 요청 commit4978c6509a33a4076e4b404d1a2b8ce25a9c43a9 / operation inspect-edge.
- [workflow35945815215](https://github.com/illumin8-dev/richon-academy/actions/runs/35945815215), portal job107463628375 완료 로그 확인.
- 02:07:50~51 UTC: /auth/login, /auth/kakao/callback, /auth/naver/callback, /portal/mypage는 고정 Access 로그인 gateway302. / 및 /apply.html은200 text/html.
- 실제 원본에 연결키 없음/잘못된 키는 모두403 edge_required.
- 서비스·IAM·트래픽 변경 없이 종료. 전체 backend·임시PostgreSQL·Docker, 자동화95/Worker11개 성공.

### 새 후보 배포

- 요청 commit **d0b2c7389b2394de9c6bfd110c3e7933a90d38f5** / operation stage-edge-naver / request_id naver-stage-after-bic-20260924-02.
- [workflow35946050229](https://github.com/illumin8-dev/richon-academy/actions/runs/35946050229), portal job **107464337433**의 완료 steps/로그 확인.
- 02:12:45 UTC = 11:12:45 KST: `EDGE CANDIDATE STAGED: richon-portal-gh-35946050229-1 / existing 100% traffic unchanged.`
- stage()가 새 image digest / 정확한후보revision·Ready / 고정Naver 두참조 / 다른env·자원제한 / 기존IAM·트래픽 / 지정tag를 생성 후 두차례 재검사했다.
- 후보와 기존 원본에 없는·틀린 연결키를 보내 각각403 edge_required 확인.
- Dockerfile.portal의 시작점은 portal_readiness. RICHON_BOOTSTRAP_VERIFY=true / RICHON_OAUTH_ENABLED=true를 보존했으므로 새 후보의 Ready는 제한계정접속·권한·008반환경로 catalog 읽기검사 후 기동한 근거다. 앱로그/고객행/제공자키값을 조회한 것은 아니다.
- 전체 backend·폐기PostgreSQL·Docker 검사, 포털자동화95/Worker11개, 모의Kakao/Naver이미지검사 성공. CI 모의 인증을 실계정 성공으로 표시하지 않는다.
- 실제 클라우드 쓰기는 이미지등록과 후보image+두Naver참조+후보tag뿐. 서비스주소의 기존100% 트래픽은 유지했다. 다른 legacy 배포/승격 단계는 skipped.

## 바로 다음 작업 — 후보 생성 반복 금지

**이제 후보가 존재한다. 기존 inspect-edge/stage-edge는 '기존후보없음'을 요구하므로 무작정 재실행하지 않는다.** 다음에는 제공·후보revision과 tag를 읽기 조회해 시작한다. 이번 작업의 임시 운영 receipt는 workflow 종료 시 지워졌으므로 이전 receipt 파일이 남아 있다고 가정하지 않는다.

1. 실제 Worker의 정확한 Naver PNG GET 경로를 맞춘다. 이번 조회한 `feat/backend-social-login/edge/worker.mjs`에는 /auth/assets/kakao-login.png만 있고 **/auth/assets/naver-login.png가 아직 빠져 있다.** 승인된 백엔드 구현에 맞는 edge 전용 변경과 테스트만 반영한다. backend 전체를 Worker branch에 역병합하지 않는다.
2. 후보의 인증된 화면·쿠키 확인 방법과 제한 테스트 전환을 명시적으로 확정한다. 현재 edge 운영코드는 자동승격을 지원하지 않는다. 후보를 기존 로그인주소에 연결하거나 서비스트래픽을 전환할 때 접근제한·키·버전·롤백 대상을 유지하고 검증한다.
3. 본인이메일 Access 제한 안에서 실제 카카오·네이버 신규/기존가입·취소·로그아웃·복귀·일반회원 관리자차단을 확인한다. 이 단계는 일반공개·검수승인이 아니다.

후보 원본URL은 연결키 없이 접근하면403이므로 사용자에게 정상 로그인테스트 링크라고 전달하지 않는다. 브라우저에 서버키를 입력시키거나 키·쿠키를 대화에 복사하도록 요구하지 않는다.

이번에는 Worker/upstream/Access 정책·메인홈페이지를 변경하지 않았다. **따라서 현재 홈페이지에서 다시 눌러도 이전 로그인화면이 나올 수 있다.** DB008/Secret IAM 준비명령과 BIC 규칙생성을 다시 안내하지 않는다.

## BIC 예외와 보안 경계

이전 사용자 이벤트(10:16:28 GMT+9, GET /apply.html, 빈query, Python-urllib/3.12)의 차단제품은 BIC였다. 국가/IP차단이나 모든403의 원인으로 확대해 해석하지 않는다.

PR22 mergef50e32ce25b05f3e72d0c97d1dadf8ba29f7abb8은 검사요청을 공개이름 `RichonPortalDeployCheck/1.0`으로 식별한다. 정상브라우저 위장이 아니다. 고정6주소·GET·빈query·무인증·미추적redirect·엄격한Access/403검사를 유지한다. CI35944696028/35944696116 성공.

소유자에게 제안한 규칙은 정확한 host/GET/빈query/위User-Agent/고정6주소에 BIC만 Skip이다. 전체 방화벽/관리규칙/속도제한/Access를 해제하지 않는다. **User-Agent는 누구나 복사할 수 있어 인증수단이 아니다.** 같은 조건의 제3자도 BIC 하나를 건너뛸 수 있다. 다른보안·Access·원본edge key·회원인증은 유지한다. 진단예외가 불필요해지면 해당규칙 하나만 비활성화해 철회한다. 상세표현식·범위는 .github/portal/CLOUDFLARE_BIC.md.

이번 실제302는 예상Access gateway까지 도달했다는 증거이지 owner이메일정책 내용/Skip의전체선택항목을독립검증한것은아니다. 예외범위를 자동확대하지 않는다.

## 이미 완료된 소유자 준비

PR20 helper source0e1190bdbeb6b84ac325cd81d3db7bcf520aafa6 사용자실행:
- LOGIN PREREQUISITES READY / database_008:verified_existing.
- richon-naver-client-id: verified / added:false / version1.
- richon-naver-client-secret: verified / added:true / version1.
- 당시server_deployed:false는 준비명령의정상결과였다. 이후이번후보배포와구분한다.

이번 DB DDL·Secret IAM·새key·비밀번호·WIF·공개문서는 변경하지 않았다. 두키값은 조회/게시하지 않는다.

## 작업 기준선

공개홈페이지는 **marururu00/richon-academy/main**. 작업fork main과 혼동하지 않는다. 히어로는사용자가원본에병합·확인했으며 연결앱의원본쓰기권한복구와는다르다.

| 역할 | illumin8-dev/richon-academy branch |
|---|---|
| 홈페이지소스·작업지도 | main |
| 로그인·관리서버통합·배포 | **feat/backend-portal-deploy** |
| 실제Cloudflare Worker Git경로 | feat/backend-social-login |
| 기존주문서버 WIF경로 | feat/backend-gcp-deploy |
| PR10보류소스 | feat/backend-pricing-notes-oauth |

기준선5개와 단기branch fix/login-release-prerequisites 유지. 이번 새branch/코드PR 생성없음. WIF/Cloudflare 참조 branch명을 임의변경·삭제하지 않는다.

## 보존 이력 / 후속문서

- 히어로: 원본PR8 merge097f7b74f995a11ac0360c76f42b081adc5f53ae / Pages35897836106 / 사용자메인확인. 작업PR18, 기존본문·동작보존, Chromium7시나리오run35894740143.
- PR4: 백엔드mergea0ef6fc4108bf9ffa3e20901aabbf2e925a71982. 검증35893635153/35893634834/35893634316.
- PR10: 나중에진행. 소스/SQL/가격변경없음.
- PR19: cf5383dd9d5c847eda803f6737a6cc45962eccb4, merge7452fdff7a0357a44a90ff0737de61cc47f719c8. 검증35901901115/35901901506/35901901140/35901901187. startup DB008검사/숫자버전참조검사/owner준비helper.
- PR20: merge94c88af33d93ccb64e55b71a72c4af707f06e2e1. 검증35933136352/35933136699/35933136410. SecretIAM형식비교수정·DDL없는재개·권한보존.
- PR21: stage-edge-naver구현. merge9724b146e43d2cdde6bd2e1d76c715b5e7eb9e0e. 첫run35942079551은BIC로후보생성전중단. **이 실패를 이번 성공한run35946050229와혼동하지않는다.**
- Neon연결도구의project_id오류와이후owner helper/후보startup의DB검증성공을구분한다.
- 첨부PDF/공식가이드대조: backend/LOGIN_RELEASE_CHECKPOINT.md. state/서버Secret/안전쿠키/provider+app+response.id식별유지. 탈퇴/revoke/세션회수·파기·국외처리·방침은후속. 전체준수/검수완료로표시하지않는다.
- branch정리run35895921493: 이전23개는archive/2026-09-24/<이전branch명>태그로복구가능. PR13/17/18은과거実행증거.

최신재개점: [PR22 CHECKPOINT-027](https://github.com/illumin8-dev/richon-academy/pull/22#issuecomment-5806256318). 키·쿠키·인가코드·고객정보는Git/로그/artifact에저장하지않는다. Cloudflare관리커넥터는이전검색결과없음. 유료TinyFish는이번에사용하지않았다.
