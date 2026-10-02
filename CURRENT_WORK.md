# CURRENT WORK / 리치온아카데미

- 기준일: 2026-09-29
- 용도: 승인된 결정 / 현재 장애 / 다음 순서를 잊지 않기 위한 단일 작업 체크리스트
- 원칙: 대화 기억이나 PR 제목만 믿지 않고, 이 문서 + 최신 PR 체크포인트 + 실제 배포 상태를 함께 확인한다.

## 0. 최우선 / 로그인 안정화

Kakao 개인정보 동의항목 1차 심사 반려 (2026-09-28):
- 회원가입 링크/화면에서 전체 회원가입 절차와 수집 항목·필수/선택 조건이 확인되지 않는다는 사유
- CI는 실제 자체 본인인증을 수행하는 서비스에 한해 검토되며, 현재 소셜 로그인만으로는 승인 근거 부족
- CI를 유지하려면 별도 본인확인 절차 도입 여부를 사용자와 결정 후 재신청
- CI를 제외할 경우 현재 provider identity + 명시적 계정 연결 정책 유지


현재 확정 상태:
- /portal/mypage 비로그인 gate → 간편 로그인 팝업 노출 정상
- 로그인 시 만14세 체크는 제거 / 신규 회원정보 완료(/auth/signup)에서만 필수
- OAuth form POST 뒤 cross-origin redirect의 Chromium CSP 문제는 same-origin handoff 방식으로 해결
- handoff fallback 문구/링크는 정상 자동이동 중 즉시 보이지 않도록 기본 숨김
- provider 이동이 2초 이상 지연되거나 JS 자동이동에 문제가 있을 때만 "이동이 안 되면 계속" fallback 노출
- 최신 protected candidate: richon-portal-handoff-36389551578-1
- 기존 유일 회원은 member/auth identity 유지 / member_profiles 0 / 세션 0 상태로 의도적으로 대기
- Kakao 개인정보 동의항목 1차 신청 반려: 회원가입 절차 확인자료 부족 / 당시 CI 실제 미수집
- 사용자 결정 변경: CI를 동일인 중복가입 방지 및 기존 회원 비교 식별 목적으로 실제 사용
- 반려 대응: 공개 signup-guide / privacy / terms를 CI 필수(카카오), 이름·전화번호 필수, 성별·연령대 선택 구조로 정합
- CI는 raw 저장하지 않고 SHA-256 digest만 저장 / provider subject는 계속 로그인 주 식별자 / CI는 본인인증 대체 아님
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
- [x] 로그인 세션 정책 7일 절대 만료 / 24시간 미사용 만료 확정
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
- [x] PR #63 Kakao CI 중복가입 방지 코드 병합
- [x] DB014 provider_ci_digest/member_ci_claims + 최소권한 적용/readback PASS
- [x] PR #63 protected candidate richon-portal-handoff-36389551578-1 배포 / default 100% unchanged
- [x] PR #64 signup-guide/privacy/terms를 CI 중복가입 방지 목적과 정합
- [x] PR #68 카카오 CI 심사용 가입 화면 표시 보강 / feat/backend-portal-deploy 병합
- [ ] Kakao 재신청: 이름·전화번호·CI 필수 / 성별·연령대 선택 + 회원가입 경로/전체 절차 화면 첨부
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

현재 UI closeout 경계:
- fork main 공개 홈페이지/강의 신청 UI closeout은 PR #69 범위
- 기존 `fix/member-shared-ui-closeout` 브랜치는 최신 backend 기준 고유 변경 0 / stale 상태이므로 작업 기준에서 제외
- 원본 marururu00/richon-academy 반영 전에는 실제 공개 홈페이지 완료로 간주하지 않음


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
- [x] PR #69 공개 신청 UI 복구 / 모집상태별 CTA / shared chrome·JS 계약 강화 (fork main)

남은 항목 / 경계:
- [ ] 강의별 주차 담당 강사는 course 데이터/상세 화면 구현 시 강의 안에서 표시
- [x] 프로그램 카드 3×2 구조 유지 / 5개 강의 + 6번째는 작은 `COMING SOON` + `새로운 과정 준비 중`만 표시 / 설명문·버튼 없음 (2026-09-29 재확정)
- [x] 모집중은 신청하기만 / 대기는 대기 신청만 / 모집예정은 모집 예정 + 해당 apply.html 소개 링크로 확정 (2026-09-29)
- [x] 대표 멘토 소개는 3문장으로 구성하고 문장마다 별도 줄로 표시
- [x] 실전 멘토 카드는 이름 / 분야 / 짧은 실전 소개를 함께 표시
- [x] 멘토 영역은 `리치온 멘토진` 하나의 섹션 아래 대표 멘토 1명 + 실전 멘토 6명 / 총 7명 구조로 통일하고, 대표 멘토도 같은 카드 패밀리의 가로 카드로 표시 (2026-09-29)
- [ ] 외부화한 본문 JPEG의 WebP 변환은 후속 성능 최적화 항목
- [x] fork main apply.html은 기존 승인 신청/결제 UI를 복구하고 현재 5개 과정/모집상태에 맞게 정합
- [x] apply.html은 과정별 기존 강의 소개를 유지하고 운영 설명/공통 안내 문구/`신청 흐름` 섹션은 제거 (2026-09-29 재확정)
- [x] 원본 marururu00/richon-academy main에 공개 UI/apply.html 반영 및 GitHub Pages 배포 확인 (PR #11 / 2026-09-29)
- [ ] admin은 공개/회원과 다른 운영 UI family이므로 동일 header 강제 대신 course/admin 구현 단계에서 brand token·간격·타이포 정합
- [ ] OAuth HTML/CSS embedded refactor는 다음 UI closeout PR에서 shared token/asset 기준으로 분리
- [x] 원본 marururu00/richon-academy에 public UI foundation + signup-guide/policy 반영 완료 (PR #11 / 2026-09-29)
- [ ] 원본 public 배포 전 {{구글폼URL}} / {{결제링크URL}} / {{입금계좌}} 등 launch placeholder 재점검

현재 public 배포 경계:
- fork main 최신 공개 UI 반영
- 원본 marururu00/richon-academy main은 PR #11까지 반영
- GitHub Pages build/deployment 성공 확인 (merge 11e81b2e2ce91baa7b189a13fd5df9352c7c3520)

## 2. 강의 데이터 / 관리자

정리팩 확정:
- [x] 관리자 사이드바에서 신형 강의/수강권을 운영 정본으로 배치 / 월별·수동등록은 기존 기록 영역으로 분리
- [x] 관리자 홈 강의 통계를 legacy courses가 아니라 course_programs / course_runs 기준으로 전환
- [ ] 관리자 회차/영상/자료 관리 UI
- [ ] 수강권 취소 후 복구/재개 흐름
- [ ] 공개 캘린더 60초 edge cache + rollout probe


사용자 결정:
- course data = DB + admin page
- 결제보다 내 강의 / 수강생 관리 우선
- Pre리치온 = 2개월 고정 수강권
- 리치온 스터디 = 기간제 수강권
- 재개발 / 인테리어 / 청약 = 기수별로 기간이 달라질 수 있음
- 관리자가 신청/결제 없이도 수동으로 수강권 생성 가능
- 내 강의는 영상/자료 링크 필드를 포함하되 초기에는 비워둘 수 있음
- 로그인 외부 승인/E2E는 일단 보류하고 public 원본 반영 후 강의/수강생/내 강의로 진행

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

## 3-1. 중앙 캘린더 / 2026-10-02 10월 캘린더 UX 기준

확정:
- [x] 관리자 캘린더는 course_programs / course_runs / course_sessions와 독립
- [x] 일반 일정 입력: 날짜 / 색상 / 과정 자유 텍스트 / 내용 자유 텍스트
- [x] 내용은 공란 허용
- [x] 색상은 2026년 10월 캘린더 팔레트 6종으로 통일
- [x] 빈 날짜 클릭 → 날짜가 채워진 편집창
- [x] 기존 일정 클릭 → 수정 / 임의 날짜 복사 / 삭제
- [x] 연휴 / 강조 문구: 시작일 / 종료일 / 문구 / 색상
- [x] 연휴 Proposal B 확정: 큰 음영/날짜 박스 제거 / 날짜는 색상 텍스트만 / 주차별 얇은 리본
- [x] 연휴 문구는 리본 안에서 1회만 / 다음 주 리본은 문구 없이 연속성만 표시
- [x] 연휴 리본은 실제 기간 밖 날짜를 포함하지 않는 exact range
- [x] 문구 리본 위치는 연휴 날짜가 가장 많이 포함된 주 / 동률이면 시작 주
- [x] +7일 고정 복사 / 반복 규칙 없음
- [x] 10월 owner 제공 캘린더를 단일 시각 기준으로 사용
- [x] 제목은 레전드와 독립적으로 캘린더 전체 폭 정중앙 고정
- [x] 상단 심볼은 owner 제공 10월 캘린더 원본 로고를 SVG로 벡터화해 사용 / PNG 출력도 동일 형상
- [x] 세로 격자 대신 주차 점선 / 컬러 날짜 블록 / 색상점+과정+선택 내용
- [x] 월별 동적 범례: 현재 월 일반 일정의 실제 과정 문구 + 실제 지정 색상 조합을 표시 / 동일 조합 중복 제거 / 연휴는 제외
- [x] 2026년 6~10월 owner 제공 이미지는 추후 과거 일정 입력 기준 자료
- [ ] visual-editor PR CI
- [ ] visual-editor candidate rollout
- [ ] banner용 ends_at 최소 쓰기권한 최종 적용
- [ ] 실제 관리자 E2E / 디자인 owner 확인
- [ ] 2026년 6~10월 owner 제공 이미지 기준 76개 역사 일정 insert-only seed 적용
- [ ] 랜딩 캘린더 공개 API + 정규 프로그램 아래 / 멘토진 위 노출
- [ ] 1번 완료 후 Backend / DBA / Frontend / 관리자 / 고객 관점 통합 점검 회의
- [ ] 통합 점검에서 보완 범위를 확정한 뒤에만 내 강의/수강권 실제 E2E(3번)로 이동

현재 운영:
- [x] DB018 적용
- [x] DB019 자유형 필드 적용
- [x] DB019 final free-form grants 적용
- [x] PR #118 자유형 캘린더 병합
- [x] PR #119 DB019 rollout 호환성 수정 병합
- [x] PR #120 10월 visual editor 병합
- [x] protected candidate richon-portal-handoff-36899480371-1 rollout PASS
- [x] visual banner ends_at 최소 쓰기권한 적용 / RUNTIME_READBACK PASS
- [x] deploy request hold
- [x] 랜딩 footer 하단 74px gap 제거 확인

랜딩 2단계 확정안:
- 정규 프로그램 아래 / 멘토진 위
- 관리자와 같은 10월 캘린더 시각 체계
- 현재 달 기본 표시
- 바로 이전/다음 달 데이터가 있을 때만 해당 방향 화살표
- 공개 화면 시간 숨김
- Edge cache 60초 / browser max-age 0
- 1200×1200 PNG 클립보드 복사 / 미지원 브라우저 파일 저장 fallback

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
