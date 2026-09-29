# ADMIN / MYPAGE NEXT HANDOFF

- 기준일: 2026-09-30
- 선행 조건: 로그인/회원가입 회귀 수정 PR #88 배포 및 확인 후 진행

## 사용자 확인 이슈

1. 관리자 UI 정합
- 강의/수강권 화면과 기존 월별 수강관리/수강생 관리 화면 사이에 구버전/신버전 UI가 섞여 보임.
- 공통 admin visual family와 navigation 구조를 다시 맞춘다.

2. 404 경로
- 관리자 사이드바의 `월별 수강관리`, `수강생 수동 등록/수정` 클릭 시 `{"detail":"Not Found"}` 발생.
- frontend href / Worker allowlist / portal_entry route / router install feature flag / candidate 이미지 source를 각각 비교한다.
- 코드 미배포, route 누락, old-new 혼합 중 무엇인지 추정하지 말고 실제 경계를 확인한다.

3. 마이페이지 내 정보 UX
- 현재 정보가 눈에 잘 안 들어오고 공간 낭비가 큼.
- 불필요한 설명/TMI 축소.
- 라벨/값 폭과 정렬 통일.
- 가입일/광고수신 같은 보조정보는 위계를 낮춘다.
- 휴대전화는 DB canonical 숫자-only 값을 유지하되 화면은 `010-1234-5678`로 표시한다.

4. 로그인 연결 UX
- `연결된 로그인`과 하단 `로그인 연결 관리`가 떨어져 있어 연관성이 약함.
- 연결된 로그인 행 자체에 관리 affordance를 붙이는 방향으로 통합한다.

5. 회원 count
- 관리자 `전체 회원`에 withdrawn/탈퇴 회원을 포함하지 않는 방향.
- active + disabled를 전체 회원으로 볼지 active만 볼지는 status 의미와 운영 목적을 확인해서 결정.
- 탈퇴회원은 필요하면 별도 지표로 분리한다.

6. 회원 상세
- 회원 관리에서 이름/행 클릭 시 상세 확인 가능하도록 검토 및 구현.
- 최소 후보 정보:
  - 기본 회원정보
  - 연결 로그인
  - 현재/과거 수강권
  - 수강 강의/기수
  - 신청/주문 이력
- 상세 패널 또는 상세 페이지 중 현재 admin 구조에 맞는 방식을 선택한다.

7. 실제 데이터 경계
- synthetic placeholder와 production DB 실제 데이터를 구분한다.
- 빈 화면이 데이터 미연결 때문인지 실제 0건인지 API/readback으로 확인한다.

## 우선순위

1. 404 경로 원인 확정/수정
2. admin UI family 정합
3. 회원 count 정의 수정
4. 회원 상세
5. 마이페이지 정보 밀도/연결 로그인 UX


## 로그인 재현 상태 / 2026-09-30

- 로그인/회원가입 UI 회귀 수정 PR #88 병합 및 protected candidate 배포 완료.
- 현재 candidate: `richon-portal-handoff-36597611986-1`.
- 첫 비로그인 마이페이지 진입 시 간편 로그인 modal 자동 오픈.
- standalone auth/signup UI 현대화, provider-locked field, phone display formatting 적용.
- 현재 사용자 재현에서 Kakao 로그인/회원가입이 다시 완료되지 않음.
- 운영 read-only 진단 결과:
  - 현재 candidate `/auth/start` POST 3건 모두 HTTP 200.
  - `/auth/kakao/callback` current-candidate 요청 0건.
  - `oauth_callback_failed stage=...` 이벤트 0건.
  - 따라서 현재 증거로는 callback 내부 / CI / signup DB 저장 실패가 아니라 provider 이동 후 richon callback 도착 전 구간 문제.
- 실제 Kakao/Naver E2E 성공 기록은 PR #49에 있고, 해당 handoff 구현은 PR #46.
- PR #46 성공 시점과 현재 `provider_handoff` / `HANDOFF_JS` 핵심 이동 방식은 동일함.
- 다음 확인은 실제 브라우저에서 Kakao 버튼 클릭 후:
  1. Kakao 도메인 화면이 실제 나타나는지
  2. 나타난다면 인증/동의 뒤 어느 URL로 이동하는지
  3. Kakao 화면 자체에서 오류가 나는지
  를 사용자 개인정보/코드 없이 관찰하고, 필요 시 provider console redirect URI/consent 상태와 대조.
