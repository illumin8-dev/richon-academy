# CHECKPOINT-029 / 승인된 카카오·네이버 테스트 연결 / 2026-09-24

사용자 승인: 본인 이메일 Access 제한을 유지하고 이미 준비한 후보를 기존 로그인 주소에 연결. DB/IAM/키/홈페이지/방침문구/#10/결제 변경은 포함하지 않는다.

현재 기준은 backend d0b2c7389b2394de9c6bfd110c3e7933a90d38f5 / 실제 Worker209887a0f685e720eeb203a2e319b7992ee355b2다. 이전 로컬 ZIP의 Worker 패치는 이 기준과 같다. 이번 PR은 원격 저장·검증을 위한 한 작업 단위이며, PR 병합만으로 Worker 배포됐다고 표시하지 않는다.

## 실행 순서

1. 이번 PR의 준비된 Worker와 기존 후보 읽기검사를 CI에서 검증한다. backend branch는 기존 .github/portal-deploy.request가 바뀔 때만 GCP 작업을 실행하므로 코드 PR 자체는 GCP를 변경하지 않는다.
2. inspect-edge 요청을 새 ID로 실행한다. 이제 기존후보가 있으면 candidate_readback.py가 정확한 후보와 롤백revision을 읽기 검증한다. stage-edge/stage-edge-naver의 기존후보 금지 가드는 그대로다. 새로운 후보 생성·자동 트래픽 승격 없음.
3. 후보 richon-portal-gh-35946050229-1 / source d0b2c7389b2394de9c6bfd110c3e7933a90d38f5와 registry image 일치, Ready, 제한runtime, Naver 두version1, 기존100% 트래픽 richon-portal-gh-35810692921-1, portal-candidate tag와 고정URL, 현재Access와 원본키경계를 확인한다. 다른값이면 중단한다.
4. 검증된 edge/worker.mjs / edge/wrangler.toml / edge/candidate-transition.test.mjs만 실제 Worker branch로 적용한다. 같은 PR에서 검증된 social-login-ci.yml의 테스트범위 변경도 적용할 수 있다. backend 전체나 배포요청을 역병합하지 않는다. 기존 실제Worker의 cookie regression 검사는 보존한다.
5. Cloudflare Git build/deployment의 실제 성공을 확인하고 다시 무인증 접근·공개메인·후보상태를 확인한다. 사용자에게는 그 후 원래 /auth/login을 제공한다. 실제 계정은 사용자가 인증한다.

## 연결·보안·철회

PORTAL_UPSTREAM을 기존서비스URL에서 정확한 portal-candidate 태그URL로 바꾼다. 기본 Cloud Run URL 트래픽은 이전revision100%로 남지만 Worker를 통과한 승인된 테스트사용자의 요청은 새후보가 처리한다. tag는 가변이므로 앞으로 다른후보로 이동시키기 전 반드시 이 연결을 검토한다. 공개서비스 전환/검수승인은 별도다.

Naver PNG는 정확한 GET 경로만 추가한다. Secret값은 Git에 저장하지 않는다. workers_dev/preview_urls/observability는 false, dashboard관리 routes는 선언하지 않고 기존 Access를 변경하지 않는다. 세션쿠키/Origin/no-store/제공자redirect검사는 유지한다. Worker upstream을 https://richon-portal-amjmgyepbq-as.a.run.app 로 복원·배포하면 이전경로로 돌아간다. 문제가 발생해도 DB/IAM을 자동 역변경하지 않는다.

## 검증 상태

로컬 원래Worker15+후보8=23개 Node검사를 재실행해 통과했다. 새로운9개 후보읽기 unittest와 기존 전체검사는 GitHub CI에서 검증하고 실제 결과를 PR에 기록한다. 로컬 Python구문검사만 통과했으며 로컬전체Backend CI를 실행했다고 하지 않는다. 기존 후보/DB를 현재 턴에서 읽기조회하기 전 과거성공을 최신관측이라고 표시하지 않는다.

참조: Cloud Run rollouts-rollbacks-traffic-migration / Cloudflare Wrangler configuration 공식문서. 사용자 첨부PDF의 서버측Secret, 안전쿠키, state, response.id 식별은 그대로 보존하며 탈퇴/방침/검수미완료는 후속이다. TinyFish미사용.
