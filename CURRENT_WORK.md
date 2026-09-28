# CURRENT WORK / 리치온아카데미

- 기준일: 2026-09-28
- 용도: 승인된 결정 / 현재 장애 / 다음 순서를 잊지 않기 위한 단일 작업 체크리스트
- 원칙: 대화 기억이나 PR 제목만 믿지 않고, 이 문서 + 최신 PR 체크포인트 + 실제 배포 상태를 함께 확인한다.

## 0. 최우선 / 로그인 안정화

현재 확정 상태:
- /portal/mypage 비로그인 gate → 간편 로그인 팝업 노출 정상
- 만 14세 이상 체크 UI 정상
- Cloud Run access log에서 POST /auth/start가 실제 발생하고 303을 반환하는 것 확인
- Chromium 진단에서 provider GET 시도 직후 CSP 오류와 net::ERR_ABORTED 확인
- 원인: form POST 뒤 cross-origin provider 303 redirect가 Chromium CSP form-action 처리에 걸림
- 버튼 이벤트 / CSRF / backend start 실패가 원인이 아님
- PR #44에서 same-origin handoff document + /auth/assets/handoff.js 방식으로 수정 완료 / 아직 protected candidate 재반영 전

완료:
- [x] DB012 oauth_signups provider_name/provider_phone/provider_email 적용
- [x] runtime 최소권한 / readback PASS
- [x] provider 제공값 가입단계 read-only + 서버측 강제
- [x] 가입 후 이름 self-service 수정 차단
- [x] /auth/assets 공통 CSS/JS 경계
- [x] account-aware Worker / link/reauth/unlink/withdraw redirect + __Host-richon-link
- [x] Worker 실제 배포
- [x] PR #40 로그인 안정화 병합
- [x] protected candidate richon-portal-login-260927180059 반영
- [x] PR #41 modal native submit 후속 병합
- [x] protected candidate richon-portal-modal-260927185145 반영
- [x] 버튼 무반응 원인을 실제 로그로 확정
- [x] PR #44 OAuth provider handoff CSP 수정 병합
- [x] richon-portal-deploy 서비스계정에 Logs Viewer 최소권한 추가 / GitHub WIF 로그 조회 가능
- [ ] PR #44 이미지를 protected candidate에 재반영
- [ ] Kakao 실제 로그인 E2E
- [ ] Naver 실제 로그인 E2E
- [ ] Kakao↔Naver 계정 연결
- [ ] 연결 해제 / 마지막 로그인 수단 보호
- [ ] 회원탈퇴 / provider unlink-revoke
- [ ] 탈퇴 후 재가입
- [ ] 로그인 전체화면 / 팝업 CSS / 모바일 확인
- [ ] E2E 완료 후에만 공개 홈페이지 로그인 버튼 노출

현재 운영 경계:
- Worker upstream은 portal-candidate Cloud Run tag
- default Cloud Run 100% revision은 로그인 후보 시험 중 변경하지 않음
- ACCOUNT=true / MARKETING=true 유지
- IAM / Access 경계 유지
- 진단용 추가 권한: richon-portal-deploy@richon-academy.iam.gserviceaccount.com 에 roles/logging.viewer만 추가

## 1. Frontend / UI foundation cleanup

9/25 승인됐지만 아직 미구현 또는 부분 구현:
- [ ] 리치온 초이 큰 대표 이미지 제거
- [ ] 직함을 '리치온 아카데미 대표 멘토'로 정리
- [ ] 별도 인사말 생략하는 B안
- [ ] 핵심 소개 설명 유지
- [ ] 하단을 '실전 멘토' 구성으로 변경
- [ ] 실전 멘토는 개인 강의 링크 없이 간단 소개
- [ ] 강의별 주차 담당 강사는 강의 안에서 표시
- [ ] index/apply base64 이미지 외부 asset 분리
- [ ] lazy loading / WebP / 표시크기 최적화
- [ ] 중복 CSS / 폰트 굵기 정리
- [ ] public/apply/member/admin 공통 header/footer/mobile menu 정합
- [ ] apply의 {{구글폼URL}} / {{결제링크URL}} / {{입금계좌}} launch 전 점검
- [ ] OAuth HTML/CSS embedded refactor는 인증 안정화 후 별도 검토

## 2. 강의 데이터 / 관리자

사용자 결정:
- course data = DB + admin page
- 결제보다 내 강의 / 수강생 관리 우선

예정:
- [ ] courses = 프로그램/template
- [ ] course_runs/cohorts = 기수/회차, 일정/가격/상태/정원/모집기간
- [ ] OPEN / WAITLIST / UPCOMING / CLOSED 상태/CTA
- [ ] admin 강의 생성/수정/보관
- [ ] enrollment는 course_run 기준
- [ ] 주문/결제 금액은 browser 값을 믿지 않고 server가 course_run에서 조회
- [ ] 기존 신청 페이지와 DB 강의 카탈로그 연결

## 3. 수강생 관리 / 내 강의

- [ ] 관리자 수강생 관리
- [ ] 수강권/enrollment 생성·해제
- [ ] 내 강의
- [ ] 신청 이력 / 수강 상태
- [ ] 주문 이력과 수강권 관계 정리
- [ ] 결제는 이후 '수강권 생성 입력 경로'로 연결

## 4. 결제

- [ ] PG 계정 준비 후 provider 확정
- [ ] 결제 성공 → course_run 기반 enrollment 생성
- [ ] 서버측 가격 검증
- [ ] 결제 대기 / 주문번호 / 금액 UI 연결
- [ ] 환불/취소 정책과 실제 동작 정합

## 5. 정책 / 운영

- [ ] Kakao/Naver production review/승인 상태 실제 콘솔 확인
- [ ] 공개 terms/privacy 최신 정본 통합
- [ ] member-info-v1 시행일/문구/기능 일치
- [ ] 개인정보 파기/탈퇴 운영 절차 최종 확인
- [ ] 광고수신동의 문자/이메일 실제 발송 기능은 별도

## 작업 순서

1. PR #44 protected candidate 재반영
2. Kakao / Naver 로그인 전체 E2E 완료
3. Frontend/UI foundation cleanup + 누락된 멘토/성능 작업 회수
4. course DB + admin
5. 수강생 관리
6. 내 강의
7. 결제

## 주의

- 추정으로 운영 수정하지 않는다.
- 코드 병합 / Cloud Run candidate / Worker / public homepage 배포를 각각 구분한다.
- 사용자 승인과 구현 완료를 구분한다.
- 새 결정/완료/차단사항이 생기면 이 문서를 먼저 갱신한다.
