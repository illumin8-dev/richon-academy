# 리치온아카데미 / 작업·배포 지도

마지막 정리: 2026-09-24. **새 작업은 이 문서 → 해당 GitHub 실행 결과 → 실제 환경 순으로 확인한다.** 코드 병합과 실제 배포를 구분하며, 오래된 PR 본문의 당시 상태를 현재 상태로 간주하지 않는다.

## 어디에서 작업하나

| 역할 | 저장소 / 브랜치 | 용도 |
|---|---|---|
| 공개 홈페이지 | `marururu00/richon-academy` / `main` | 실제 `index.html`, `apply.html`, 약관·방침 |
| 홈페이지 작업 복사본 | `illumin8-dev/richon-academy` / `main` | 원본 main과 동기화할 기준. 새 UI는 여기서 짧은 작업 branch → 원본 main PR |
| 로그인·관리 서버 | `illumin8-dev/richon-academy` / `feat/backend-portal-deploy` | 백엔드 통합 기준 / GitHub–GCP 포털 배포 |
| 로그인 경로 연결 | `illumin8-dev/richon-academy` / `feat/backend-social-login` | 실제 Cloudflare Worker Git 배포 기준 |
| 기존 주문 서버 | `illumin8-dev/richon-academy` / `feat/backend-gcp-deploy` | 기존 주문 전용 자동화 / 그대로 유지 |
| 보류 작업 | `illumin8-dev/richon-academy` / `feat/backend-pricing-notes-oauth` | PR #10 가격·고객 메모 초안. 사용자 요청으로 보류 |

`feat/backend-*` 3개 운영 branch의 이름은 외부 WIF/Cloudflare 설정에 연결되어 있다. 이름을 짧게 바꾸거나 없애려면 연결 설정까지 같이 검증해야 하므로 임의 변경하지 않는다. 이전 v1~v7 및 완료된 기능 branch는 활성 개발 기준이 아니다.

브랜치 정리 기준: 각 삭제 대상의 정확한 마지막 커밋을 `archive/2026-09-24/<기존 branch명>` 태그로 보존한 뒤 삭제한다. 태그와 커밋이 일치하지 않거나 열려 있는 PR이 사용 중이면 중단한다. 보호 규칙을 끄거나 강제로 이력을 덮어쓰지 않는다. 실행 결과는 아래 진행 기록을 확인한다.

## 이번에 한 작업

### 메인 히어로

- 사용자가 선택한 최신 v7의 OFF→ON 스크롤 전환, 모바일 이미지와 텍스트 위치를 `index.html`로 이관한다.
- `index-test.html` 전체를 덮어쓰지 않는다. 실제 메인의 후기/과정/강사/푸터/하단 신청 영역은 원본 그대로 보존한다.
- CSS/JS/데스크톱 이미지는 `assets/hero/home-hero.css`, `home-hero.js`, `richon-hero-desktop.webp`로 분리한다. 기존 모바일 WebP는 그대로 사용한다.
- 원본 이미지 생성/재생성 없음. 메뉴·앵커·신청 링크는 실제 메인 흐름에 연결한다. JS 비활성/동작 줄이기에서도 내용과 신청 링크를 표시한다.
- 검증 source: `d2bd7308ea716572cda8b603300a3935715d5975` / [GitHub 실행 35894740143](https://github.com/illumin8-dev/richon-academy/actions/runs/35894740143).
- Chromium 320/390/768/900/1440px, reduced-motion, JS-off 총7개 시나리오. 메뉴 열기·닫기/앵커/신청 이동/이미지·overflow/JS 오류 검사. 본문·푸터·하단 신청 영역 byte-identical 검사.
- 이 변경의 source 병합과 Pages 실제 배포 결과는 원본 저장소의 해당 PR 및 Actions에서 별도로 확인한다.

### PR #4

- 원본 테스트를 최신 백엔드에 맞춰 통합 검증했다. 기준 head `bd339ca919e7dc4e7f6f4b3df4c46ed45bcb3296`.
- Backend/PostgreSQL/Docker run35893635153, Login35893634834, Edge35893634316 모두 성공.
- 실제 병합: `a0ef6fc4108bf9ffa3e20901aabbf2e925a71982`.
- 변경은 `backend/tests/test_orders_http_postgres.py` 240줄 추가뿐. 실제 주문·PG·DB·서버 설정은 바꾸지 않았다.

### PR #10

**사용자 요청으로 나중에 진행.** 가격 1/2/6개월과 고객 메모가 폐기된 것은 아니다. 일부 파일만 저장된 초안이므로 SQL만 단독 적용하거나 완성된 기능으로 표시하지 않는다. 현재 공개 요금/고객 메모 동작을 이 초안에 맞춰 변경하지 않는다.

## 로그인 서버 / 마지막 확인과 남은 일

- 공식 카카오·네이버 버튼 코드 PR #16 및 로그인 복귀 코드 PR #14는 백엔드 작업선에 통합되어 있다.
- 현재 접근 방식은 승인된 `public invoke + 앱 edge-key 검사 + Cloudflare Access`다. 과거의 IAM-private/Worker OFF 기록을 현재 상태로 읽지 않는다.
- 마지막 실제 Cloud Run 조회(run35887959276): 제공 revision `richon-portal-gh-35810692921-1`, 원본의 키 없음/오류 요청 모두403 edge_required. 네이버 runtime 바인딩 없음. Access 자동 확인은 inconclusive.
- 이 문서 작성 단계에서 Cloud Run을 새로 배포하거나 운영 DB를 바꾸지 않았다. 마지막 측정치를 최신 라이브 조회라고 표현하지 않는다.
- 운영 DB008 복귀경로 적용 여부 미확인. Neon 도구의 project_id 입력 스키마 문제를 해결하거나 정상 지원되는 읽기 경로를 확보해야 한다.
- Secret Manager에 네이버 리소스가 있다는 것과 Cloud Run의 실제 바인딩/IAM/활성 버전 연결은 다르다.
- 실제 카카오·네이버 신규가입/재로그인 성공은 아직 확인 전이다. 모의 OAuth 및 CI PostgreSQL 성공과 구분한다.

## 남은 작업 순서

1. **카카오 실제 테스트 배포 완료:** DB008 상태 확인·필요한 변경, Access 확인, 백엔드/Worker 버전 정합 배포. 본인 이메일 제한을 유지한다.
2. **네이버 실제 연결:** 등록된 앱과 기존 Secret 리소스의 숫자 버전/IAM/env 바인딩을 검증·연결한다. 키 재발급·앱 재등록을 반복하지 않는다.
3. **실계정 동선 확인:** 신규/기존 로그인, 동의 거절·취소, 로그아웃, 이전 페이지 복귀, 일반회원의 관리자 접근 차단. 실제 인증은 사용자 브라우저에서 확인한다.
4. **정식 운영 개인정보 정책·회원 생명주기:** 실제 수집항목·사용처·연락처·보유기간·위탁/국외이전 확정 → 가입 동의/약관/방침 일치 → 탈퇴·제공자 연결해제·외부 통지·세션 회수·파기 구현/검증.
5. **검수 자료와 제한 공개:** 실제 동선/정보 활용 화면을 캡처하고 필요한 제공자 검수를 신청. 승인/운영 점검 후 공개 접근 변경을 별도로 승인받는다.
6. **보류 기능 재개:** 사용자가 재개를 지시하면 PR #10 가격·고객 메모, 관리자 수강 운영 검증, 기존 명단 일괄 이관을 진행한다.
7. **결제 연결:** PortOne 계정 준비 후 서버 결제 확인·웹훅·취소/환불·수강 권한/영수증 흐름을 별도 검증한다. 로그인 검수 완료와 결제 완료를 혼동하지 않는다.

가격·메모·결제는 로그인 오류 해결과 한꺼번에 바꾸지 않는다. 공개 문서의 실제 이메일/보유기간/계약 정보를 추측해서 기재하지 않는다.

## 기록과 재개

- 기존 체크포인트: [백엔드 작업 기록 PR #13](https://github.com/illumin8-dev/richon-academy/pull/13), [배포 검사 기록 PR #17](https://github.com/illumin8-dev/richon-academy/pull/17).
- 새 진행은 커밋/검사/배포·오류 단위로 기록한다. 완료됨/미완료/다음 시작점과 실제 Git SHA를 남긴다.
- 작업이 끊기면 최신 branch/ref와 실행 결과부터 재조회한다. 완료한 DB 변경/배포를 기록만 보고 반복하지 않는다.
- 실제 키·쿠키·인가코드·고객정보를 PR/로그/문서/artifact에 저장하지 않는다. TinyFish 유료 자동화는 별도 승인 없이 사용하지 않는다.
