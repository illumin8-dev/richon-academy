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
- 최신 protected candidate: richon-portal-handoff-36381388633-1
- 기존 유일 회원은 member/auth identity 유지 / member_profiles 0 / 세션 0 상태로 의도적으로 대기
- Kakao 개인정보 동의항목 1차 신청 반려: 회원가입 절차 확인자료 부족 / CI 실제 미수집
- 반려 대응: 공개 signup-guide 추가 / 필수·선택 수집조건 명시 / privacy·terms 실제 소셜 가입 방식으로 정합 / CI·DI 미수집 명시
- Kakao 재신청 시 CI 제외 / 이름·전화번호 필수, 성별·연령대 선택 / 이메일은 일반 카카오 로그인 동의항목에서 별도 설정
- Naver API 제공정보는 이름·이메일·휴대전화 필수 / 성별·연령대 추가로 설정
- Naver 개인정보 국외이전 2건 등록 완료 / 사전 검수 승인 요청 제출 완료
- 운영 DB 현재 확인: active member 0 / auth identity 0 / profile 0 / session 0 / withdrawn member 2
- 따라서 다음 Naver 로그인은 기존 회원 보완이 아니라 신규 회원가입 흐름으로 진행되며, 검수용 provider 자동입력 확인에 적합
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
- [x] 로그인 전체화면 / 팝업 / 회원 모바일 UI synthetic 회귀검증
- [x] 최신 배포에서 handoff fallback이 정상 이동 중 체감상 보이지 않는지 사용자 최종 확인
- [x] PR #53 소셜 이름/전화/이메일/연령대/성별 자동반영 코드 병합
- [x] DB013 oauth_signups provider_age_range/provider_gender + 최소 INSERT grant 적용/readback PASS
- [x] PR #53 protected candidate 배포 / default 100% traffic unchanged
- [x] Naver 국외이전 정보 2건 등록
- [x] Kakao 1차 반려 사유 분석 / 회원가입 안내·정책 정합 수정 (fork main PR #60)
- [ ] Kakao 재신청: CI 제외 + 회원가입 경로/전체 절차 화면 첨부
- [ ] Kakao 개인정보 추가 기능 심사 승인 + 이메일 동의항목 설정
- [ ] Naver 사전 검수 승인 (승인 요청 제출 완료)
- [ ] Naver 테스트 로그인으로 신규가입 진행 / 이름·휴대전화·이메일·연령대·성별 실제 반환 확인
- [ ] 회원정보 완료 후 마이페이지 5개 정보 + 활용목적 문구 캡처 / Naver 제공정보 활용처 자료로 제출
- [ ] Kakao 승인 후 동일 자동입력/잠금 검증
- [ ] E2E 완료 후에만 공개 홈페이지 로그인 버튼 노출

현재 운영 경계:
- Worker upstream은 portal-candidate Cloud Run tag
- default Cloud Run 100% revision은 로그인 후보 시험 중 변경하지 않음
- ACCOUNT=true / MARKETING=true 유지
- IAM / Access 경계 유지
- 진단용 추가 권한: richon-portal-deploy@richon-academy.iam.gserviceaccount.com 에 roles/logging.viewer만 추가

## 1. Frontend / UI foundation cleanup

완료:
- [x] 리치온 초이 큰 대표 이미지 제거
- [x] 직함을 '리치온 아카데미 대표 멘토'로 정리
- [x] 별도 인사말 생략하는 B안 반영
- [x] 핵심 소개 설명 유지 / 간결화
- [x] 하단을 '실전 멘토' 구성으로 변경
- [x] 실전 멘토는 개인 강의 링크 없이 간단 소개
- [x] index 본문 base64 JPEG 6개를 assets/images 외부 파일로 분리
- [x] 기존 loading=lazy 유지 + decoding=async 적용
- [x] public/member 공통 header/footer/site.css/site.js 정본화
- [x] public/member 모바일 메뉴 full-screen overlay 방향 통일
- [x] /portal/mypage 푸터 링크 기본 파란색 제거 / 공통 푸터 톤 적용
- [x] landing 중복 header/footer JS 제거 / hero CSS에서 공통 header 기본 스타일 분리
- [x] index.html 약 550KB → 약 34KB 축소
- [x] public UI 정적 계약 CI 추가
- [x] PR #56 회원 공통 shell 마감 병합 + protected candidate 배포
- [x] PR #61 회원 푸터 링크/모바일 메뉴 공통화 후 protected candidate richon-portal-handoff-36387697145-1 배포
- [x] PR #57 public UI foundation 병합 (fork main)

남은 항목 / 경계:
- [ ] 강의별 주차 담당 강사는 course 데이터/상세 화면 구현 시 강의 안에서 표시
- [ ] 외부화한 본문 JPEG의 WebP 변환은 후속 성능 최적화 항목
- [ ] apply.html은 fork/original 모두 현재 0 byte / 신청 페이지 요구사항 확정 후 재구성 필요
- [ ] admin은 공개/회원과 다른 운영 UI family이므로 동일 header 강제 대신 course/admin 구현 단계에서 brand token·간격·타이포 정합
- [ ] OAuth HTML/CSS embedded refactor는 인증 provider 승인/실 E2E 종료 후 별도
- [ ] 원본 marururu00/richon-academy에 public UI foundation + Kakao signup-guide/policy 반영: repo metadata는 push=true로 보이지만 branch/PR API는 여전히 403 Resource not accessible by integration
- [ ] 원본 public 배포 전 {{구글폼URL}} / {{결제링크URL}} / {{입금계좌}} 등 launch placeholder 재점검

현재 public 배포 경계:
- fork main에는 PR #57 반영 완료
- 원본 marururu00/richon-academy main은 아직 기존 v7 landing 상태
- 원본 write/PR 생성은 현재 연결 앱에서 403 Resource not accessible by integration

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
- [x] fork main 공개 terms/privacy를 현재 passwordless 소셜 회원가입 방식에 맞게 정합
- [ ] member-info-v1 시행일/문구/기능 일치
- [ ] 개인정보 파기/탈퇴 운영 절차 최종 확인
- [ ] 광고수신동의 문자/이메일 실제 발송 기능은 별도

## 작업 순서

1. Kakao/Naver provider 심사 승인 대기 / 승인 후 실제 5개 필드 자동입력·잠금 검증
2. 원본 GitHub write 권한이 확보되는 즉시 PR #57 public UI foundation을 원본에 반영
3. 남은 계정 연결/해제/재가입 실 provider lifecycle 검증
4. course DB + admin 요구사항/옵션 검토 후 구현
5. 수강생 관리
6. 내 강의
7. 결제

## 주의

- 추정으로 운영 수정하지 않는다.
- 코드 병합 / Cloud Run candidate / Worker / public homepage 배포를 각각 구분한다.
- 사용자 승인과 구현 완료를 구분한다.
- 새 결정/완료/차단사항이 생기면 이 문서를 먼저 갱신한다.
