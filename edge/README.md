# A안 / 같은 도메인 로그인 라우터

`https://richonacademy.com/auth/*`와 `/portal/*`만 별도 포털 진입점에 연결합니다.
root/index/apply/terms/privacy는 기존 정적 호스팅에 남깁니다. 홈페이지 HTML과 DNS는 이 PR에서 수정하지 않습니다.

## 아직 실제 배포가 아닌 준비 코드

- 이 PR은 소스/CI만 변경합니다. Cloudflare 계정 연결 도구는 현재 검색에서 확인되지 않았습니다.
- 기존 비공개 Cloud Run `richon-backend-test`를 공개하거나 upstream으로 사용하지 않습니다.
- 별도 서비스 제안 이름은 `richon-portal`이며 아직 생성하지 않았습니다. 생성·공개·비용 발생 승인이 필요합니다.
- 기존 GCP WIF 배포 권한은 테스트 서비스에 한정돼 있습니다. 이를 넓히거나 새 배포 권한을 만들지 않았습니다.
- `wrangler.toml` 기본 설정은 live routes 없음 / workers.dev OFF / preview URL OFF / 포털 OFF입니다.
- 따라서 이 파일을 Git에 합쳐도 홈페이지 트래픽이나 실제 DB가 바뀌지 않습니다.

## 배포 전 확인 순서 (운영자가 검토할 체크리스트)

1. richonacademy.com이 현재 Cloudflare의 활성 zone인지, 기존 호스트가 proxied 상태인지 확인합니다.
   이미 적용된 Worker Routes/Pages Functions가 있는지 읽어 충돌을 확인합니다. DNS 원본 호스트를 추측해 변경하지 않습니다.
2. 승인된 최소권한 DB 역할에 검토한 001/002/003/007 스키마 권한을 연결합니다.
   월별/수동 화면 활성화에는 해당 기능의 스키마도 필요합니다. 이번 작업은 DDL을 적용하지 않습니다.
3. `docker build -f backend/Dockerfile.portal -t <approved-image> .`로 전용 이미지를 만듭니다.
   Dockerfile별 allowlist가 private entry/주문/마이그레이션/자격정보를 이미지에서 제외합니다.
4. 별도 포털 서비스에 전용 entry `portal_entry:app`, scale-to-zero, max instances 제한을 설정하고
   확인된 Secret 버전과 RICHON_OAUTH_ORIGIN=https://richonacademy.com을 연결합니다.
   RICHON_EDGE_SECRET은 암호학적으로 무작위 생성해 Secret Manager/Worker secret에만 저장합니다.
   Cloud Run 서비스계정 JSON 키나 카카오 시크릿을 Worker에 복사하지 않습니다.
5. 실제 키 사용 전에 Cloud Run 자동 request log의 callback query 보관 방지 정책을 설정합니다.
   앱은 access log OFF, no-proxy-headers이며 Worker observability는 OFF지만, 이것만으로 플랫폼 로그가 꺼지지 않습니다.
   로그 제외는 신규 포털의 callback 요청 범위에만 적용하고 관련 감사 로깅은 유지합니다.
6. 카카오 앱 1585992에 https://richonacademy.com/auth/kakao/callback을 등록합니다.
   네이버 준비 후에는 https://richonacademy.com/auth/naver/callback을 정확히 등록합니다.
7. Worker 환경에 확인된 신규 richon-portal-*.run.app upstream과 matching gate secret을 설정합니다.
   먼저 테스트 요청과 비인증 차단을 확인하고, callback 경로에는 cache bypass/rate limit을 검증합니다.
8. 배포 승인 후 Routes 두 개만 연결합니다. zone 전체 Custom Domain이나 richonacademy.com/*로 대체하지 않습니다.
9. 실제 브라우저에서 카카오 취소/동의 거부/첫 가입/재로그인/로그아웃과 일반회원의 관리자 차단을 검증합니다.
   실제 운영자 계정은 별도 소유 확인 후 지정합니다. 첫 가입자 자동 admin이나 이름·연락처 자동 병합은 없습니다.
10. 검증 후에만 기존 홈페이지의 로그인 링크를 공개합니다.

## 중단 / 롤백

- 신규 두 Routes를 제거하거나 PORTAL_ENABLED를 false로 하면 로그인·포털 요청을 중단할 수 있습니다.
- 기존 주문 서버는 대상이 아닙니다. Worker를 끄면서 기존 서비스 IAM이나 DB를 되돌리지 않습니다.
- 쿠키/회원 DB 기록 삭제는 별도의 데이터 변경이며 소스 롤백과 함께 자동 실행하지 않습니다.
- 유출이 의심되는 edge secret은 Worker와 포털의 양쪽에서 함께 회전하고 필요 시 회원 세션도 회수합니다.

## 검증 명령

`node --test edge/worker.test.mjs`는 모의 transport 검사입니다. live provider/Cloudflare 호출이 없습니다.
`edge/check_image.py`는 CI의 127.0.0.1:8081 컨테이너만 검사합니다.
실제 reverse-proxy/브라우저 검증은 배포 단계에서 별도로 해야 합니다.

공식 문서:
https://developers.cloudflare.com/workers/configuration/routing/routes/
https://developers.cloudflare.com/workers/runtime-apis/headers/
https://docs.cloud.google.com/run/docs/authenticating/public
