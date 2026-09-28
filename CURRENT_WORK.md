# CURRENT WORK / 리치온아카데미

- 기준일: 2026-09-28
- 용도: 승인된 결정 / 현재 장애 / 다음 순서를 잊지 않기 위한 단일 작업 체크리스트
- 원칙: 대화 기억이나 PR 제목만 믿지 않고, 이 문서 + 최신 PR 체크포인트 + 실제 배포 상태를 함께 확인한다.

## 0. 최우선 / 로그인 안정화

현재 확정 상태:
- /portal/mypage 비로그인 gate → 간편 로그인 팝업 노출 정상
- 로그인 시 만14세 체크는 제거 / 신규 회원정보 완료(/auth/signup)에서만 필수
- OAuth form POST 뒤 cross-origin redirect의 Chromium CSP 문제는 same-origin handoff 방식으로 해결
- handoff fallback 문구/링크는 정상 자동이동 중 즉시 보이지 않도록 기본 숨김
- provider 이동이 2초 이상 지연되거나 JS 자동이동에 문제가 있을 때만 "이동이 안 되면 계속" fallback 노출
- 최신 protected candidate: richon-portal-handoff-36372938707-1
- 기존 유일 회원은 member/auth identity 유지 / member_profiles 0 / 세션 0 상태로 의도적으로 대기
- Kakao/Naver 이름·휴대전화·이메일 추가 정보 권한은 아직 신청/승인 전이므로 자동입력 검증은 보류
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
- [x] PR #44 handoff 계열 수정 protected candidate 반영
- [x] PR #46 signup-only age gate + reliable OAuth handoff 병합/배포
- [x] 로그인 화면에서 만14세 체크 제거 / 신규 가입 단계에서만 유지
- [x] Kakao/Naver 1회 클릭으로 provider 로그인 화면 자동 이동 확인
- [x] PR #51 handoff fallback UX 병합/배포 / 정상 이동 중 fallback 즉시 노출 제거
- [x] Kakao 실제 로그인 E2E (사용자 확인 / 2026-09-28)
- [x] Naver 실제 로그인 E2E (사용자 확인 / 2026-09-28)
- [ ] Kakao↔Naver 계정 연결
- [ ] 연결 해제 / 마지막 로그인 수단 보호
- [x] 회원탈퇴 / provider unlink-revoke 실사용 흐름 확인 (사용자 확인 / 2026-09-28)
- [ ] 탈퇴 후 재가입
- [x] 기존 유일 회원 프로필 1회 초기화 / 현재 세션 전부 종료 / members·auth_identities 유지 (2026-09-28)
- [ ] 다음 Kakao/Naver 로그인에서 기존 회원이 회원정보 완료 화면을 다시 타고 provider 제공 필드가 자동입력+잠금되는지 확인
- [ ] 로그인 전체화면 / 팝업 CSS / 모바일 확인
- [ ] 최신 배포에서 handoff fallback이 정상 이동 중 체감상 보이지 않는지 사용자 최종 확인
- [ ] Kakao/Naver 이름/휴대전화/이메일 추가 정보 동의항목 신청/승인
- [ ] 승인 후 실제 반환값 확인 / 신규 가입 시 반환 필드는 자동입력+잠금, 미반환 필드만 직접입력
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
- [ ] /portal/mypage 푸터의 블로그/카페/유튜브/개인정보처리방침/이용약관 링크가 브라우저 기본 파란색으로 보이는 스타일 불일치 수정 (Frontend/UI cleanup 때 함께 처리)
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

- [x] Kakao 비즈니스 앱 승인 완료 (사용자 확인 / 2026-09-28)
- [ ] Naver production review/승인 상태 실제 콘솔 확인
- [ ] 공개 terms/privacy 최신 정본 통합
- [ ] member-info-v1 시행일/문구/기능 일치
- [ ] 개인정보 파기/탈퇴 운영 절차 최종 확인
- [ ] 광고수신동의 문자/이메일 실제 발송 기능은 별도

## 작업 순서

1. 최신 handoff UX 실브라우저 최종 확인
2. Kakao/Naver 추가 정보 동의항목 신청/승인
3. 기존 프로필 미완료 상태에서 provider 자동입력/잠금 검증
4. 남은 계정 연결/해제/재가입 lifecycle 검증
5. Frontend/UI foundation cleanup + 누락된 멘토/푸터/성능 작업 회수
6. course DB + admin
7. 수강생 관리
8. 내 강의
9. 결제

## 주의

- 추정으로 운영 수정하지 않는다.
- 코드 병합 / Cloud Run candidate / Worker / public homepage 배포를 각각 구분한다.
- 사용자 승인과 구현 완료를 구분한다.
- 새 결정/완료/차단사항이 생기면 이 문서를 먼저 갱신한다.
