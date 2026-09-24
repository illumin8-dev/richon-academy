# 리치온아카데미 / 작업·배포 지도

최신 배포 확인: **2026-09-24 / CHECKPOINT-052 / PR24**. 이 문서 → PR 최신 체크포인트 → 실제 ref·CI·서비스 순서로 확인한다. 활동 카드의 '구현 완료'만으로 저장·검증·배포·수집 개시를 혼동하지 않는다.

## 현재 결론

**PR24는 병합됐고 새 코드가 실제 로그인 주소에 연결됐다. 다만 새 가입정보 수집 버전 member-info-v1은 아직 활성화하지 않았다. 운영 DB009 확인·적용, 최종 공개 약관·방침 교체는 남아 있다.** 코드 배포와 가입정책 전체 적용을 구분한다.

- PR24 검증 head: `9ae550a9bc53fed5e0e785f3a9fb21b274730cc5` / merge: `9c63f75fb0237c8d43cccf1b370e1af696b06186`.
- 실제 배포 source: **`61183057f5392e7af177e10e0c42ccf955b8cafb`**.
- 실제 배포 run **35980631252**, portal job **107571728832**: completed/success. 완료 로그09:24:33 UTC 직접 확인.
- 새 live revision **`richon-portal-gh-35980631252-1`**, image digest **`sha256:85ff67c6539f730245c319b1cc7449b6f48be91f67872ac48c490690393cfbfc`**.
- 기존 `portal-candidate` 태그가 새 revision을 가리킨다. Worker 코드·upstream URL은 변경하지 않았다.
- `collection_activated:false`, 두 정책버전 `internal-test-v1` 유지, `database_009:not_checked`.
- 추가 입력칸·연령 gate가 실제로 켜졌다고 안내하지 않는다. 이름·전화·이메일·선택 상담정보 수집 개시와 공개 문서 반영은 별도 미완료다.

후검사: inspector의 고정 candidate/source만 새 관측값으로 수정했고, backend 현재 source **`8e04b56e39dc032666cfb712dc2a16a2d21e2dec`**에서 `inspect-edge` 요청을 보냈다. 결과는 PR24의 다음 체크포인트를 확인한다. 이 후속은 읽기전용이며 재배포 요청이 아니다.

## 사용자 확정 기준 / 반복 질문·임의 변경 금지

| 항목 | 결정 |
|---|---|
| 가입 연령 | 간편로그인 전 만14세 이상 자기확인. 생년월일 수집·실명 본인인증 아님 |
| 필수 가입정보 | 이름(닉네임 아님) / 휴대전화 / 이메일. 가입 직후 필요 |
| 선택 상담정보 | 연령대 / 성별. 상담 내용 준비 및 상담 진행. 미동의면 서버에 저장하지 않음 |
| 회원 식별 | 제공자·앱·이용자 식별자. 이름·전화·이메일 일치로 계정/주문 자동 병합 금지 |
| 로그인 안내 | '회원 관리와 상담에 필요한 정보를 수집합니다.'와 펼쳐 보는 상세 안내 |
| 약관 | 주식회사 표기 제외 / 간편로그인 / 전용 비밀번호 수집 설명 제외 |
| 결제 | 카드번호·카드 비밀번호 등 결제 인증정보는 PG가 처리. 리치온 직접 저장 없음. 거래기록과 구분 |
| 문의 | 전화032-236-8944. 공식 이메일 사용자 추후 제공. 임의 주소 금지 |
| 메인 | 로그인·마이페이지 메뉴 비노출 유지. 히어로·강의 신청 보존 |
| 후속 | 기능 우선 / UX·UI 미화 나중 / PR10·명단 이관·결제 보류 |

## 배포된 코드와 아직 미활성인 기능

PR24의 member_profile.py / member_profile_store.py / signup_views.py / oauth_http.py에 입력 검증·필수/선택 동의·연령 gate·원자적 저장 코드가 있다. 새 흐름은 두 정책버전을 member-info-v1로 명시한 경우에만 활성화한다. 현재 배포에서는 구버전 경로를 유지한다.

가입 ticket 소모와 프로필·동의 저장을 한 트랜잭션으로 처리하며 기존 회원ID를 보존한다. 연락처는 공통 직접 입력이고 소유 인증됐다고 표시하지 않는다. 제공자 콘솔·scope/연락처 자동채움을 임의 변경하지 않았다. 이름이 없다고 닉네임으로 대체하지 않는다.

portal.py / portal_store.py / portal_static/mypage.html / portal.js의 새 정보 표시·인증상실/로그아웃/pagehide 비우기 코드는 배포됐다. 구 응답에 없는 개인정보는 표시하지 않는다. 마이페이지의 오래된 로그인 연결 전 안내 문구는 고쳤다.

009_member_profiles.sql / member_profile_migrate.py는 코드와 별도 적용 도구다. **이번에 운영 DB에서 실행하거나 권한을 수정하지 않았다.** Neon describe_project는 도구 스키마에 없는 project_id를 요구해 -32602로 실패했다. 실패를 미적용/적용 어느 쪽의 증거로도 취급하지 않는다. DB008·기존 제한계정·Naver refs 준비는 이전 성공 상태를 유지한다.

## 실제 연결 / 롤백 경계

| 구분 | 값 |
|---|---|
| 로그인 / 마이페이지 | https://richonacademy.com/auth/login / https://richonacademy.com/portal/mypage |
| 실제 Worker branch/ref | feat/backend-social-login / b7f4b6d3a37c15d37b59917d73f49b1e23640e5f |
| Worker | richon-account-router / Version c01d6cd7-4e2c-4c53-8b51-94b2bd9a31bb |
| Worker upstream | https://portal-candidate---richon-portal-amjmgyepbq-as.a.run.app |
| 현재 태그 연결 | richon-portal-gh-35980631252-1 / source61183057f5392e7af177e10e0c42ccf955b8cafb |
| 직전 태그 revision | richon-portal-gh-35946050229-1 / 보존, 현재 연결은 아님 |
| 기본 Cloud Run URL | https://richon-portal-amjmgyepbq-as.a.run.app |
| 기본 URL 트래픽 | richon-portal-gh-35810692921-1 /100% 보존 |
| 네이버 참조 | richon-naver-client-id:1 / richon-naver-client-secret:1 |
| 정책 env | internal-test-v1 / 기존 terms.html·privacy.html URL 유지 |

태그0%는 미연결이 아니다. 실제 Worker 사용자 요청은 태그를 통해 새 revision으로 간다. 현재 태그를 stage 명령으로 무심코 옮기지 않는다. 임시 검증태그 portal-code-check는 성공 전환 후 제거됐다. DB·IAM·Secret·Access·기본 URL100%·Worker코드·공개메인 변경 없음.

롤백은 실제 상태 확인 및 승인 범위에서 태그를 이전 revision으로 복원하거나 Worker upstream을 보존한 기본 URL로 바꾸는 작업이다. DB/IAM 자동 역변경이나 새 public 권한 추가 금지. CloudRun 원본은 edge key 없으면403이며 사용자 시험 링크로 주지 않는다.

## 검증 증거

PR24 head9ae550a9의 CI4개: Backend35975741193 / Login35975741580 / Edge35975741215 / PortalUI35975741244 성공. 폐기용 DB/모의 제공자·브라우저 검증을 실제 회원 시험으로 확대하지 않는다.

이번 실행:
- 실제 사전조회35978846866 / portal107565949577 성공.
- 코드-only 실제 배포35980631252 / portal107571728832 성공.
- 같은 배포 run의 전체 Python·폐기용PostgreSQL·Gcloud 업로드목록·Docker,120자동화/15Worker,포털 이미지synthetic smoke 성공. 클라우드 인증 전에 수행.
- 별도 check태그 Ready/immutable spec/image/자원/env/IAM/desired-observed traffic 검증 → 없는·틀린키403 확인 → 기존 live태그 전환 → 보호설정·재조회불변·Access 검사 성공.
- 보호경로4개(auth/login,kakao/callback,naver/callback,portal/mypage)는Access302, 메인/apply200. 인증 후 실제 브라우저 화면·OAuth가 이번 버전에서도 성공했다고 독립 확인한 것은 아님.
- inspector의 새 revision/source 두 상수 보완 후 로컬120자동화검사 성공. 원격 후검사 결과는 최신 PR 댓글 참조.

카카오·네이버 기본로그인/마이페이지/로그아웃의 이전 사용자 성공 보고는 PR23 CP035~039다. 기존 Naver키·BIC 규칙·DB008을 다시 설정하라고 하지 않는다. BIC 진단 UA는 인증수단이 아니며 기존 좁은 예외 범위를 확대하지 않는다.

## 공개 약관·방침 / 미완료

`backend/policy_drafts/member-info-v1/terms.html`은 승인된 가입 관련 조항의 교체안이며 전체 약관 대체본/환불조건 승인이 아니다. `privacy.html`은 시행 전 개정안, README.md는 대조·출시 확인표다. 이 폴더를 컨테이너/서비스로 노출하거나 공개root문서로 덮어쓰지 않았다.

공식메일·계약상 수탁자 법인·국가/국외처리·로그/백업 보유기간·권리행사/탈퇴·선택동의철회·연결해제·파기 절차·시행일이 남아 있다. 알려주지 않은 값이나 아직없는 기능을 있다고 게시하지 않는다. GCP/Neon 외 Cloudflare 및 실제 호스팅/외부리소스 처리도 누락하지 않는다.

첨부 네이버 가이드의 STEP3(6쪽 항목·목적·기간·권리),STEP4(7쪽 필수/선택·사전열람),5쪽 response.id 식별을 기준으로 대조했으며 STEP6 탈퇴·파기는 별도 미완료다. 문서 예시의 로그3개월·검수기간 등을 검증 없이 운영 사실로 적용하지 않는다.

## 다음 할 일

1. 실제 DB009/최소권한 상태 확인·필요 시 명시적 적용. 현재 Neon 스키마 장애와 배포계정의 제한 권한을 구분한다. 비밀값을 대화에 복사하거나 불필요한 관리자권한을 주지 않는다.
2. 최종 문서·운영정보·철회/파기 절차 확정. 승인된 조항만 공개원본에 통합하고 정책URL/버전/시행일 일치 확인.
3. member-info-v1 후보와 DB009를 함께 검증한 뒤 현재 live태그를 고려해 명시적으로 활성화. 필수입력/선택미동의/기존회원보완/마이페이지/로그아웃 실제시험.
4. 일반 공개·메인 메뉴 노출·검수 제출은 별도. PR10/결제는 후속.

## 저장소·이력

원본 공개 홈페이지는 marururu00/richon-academy/main, 작업fork main과 구분한다. 원본PR8·Pages·사용자 화면 확인으로 히어로완료.

| 역할 | 작업 branch |
|---|---|
| 상태지도 / 홈페이지 작업 | main |
| 로그인·관리서버/GCP | feat/backend-portal-deploy |
| Worker Git배포 | feat/backend-social-login |
| 기존 주문서버WIF | feat/backend-gcp-deploy |
| 병합된PR24 구현이력 | feat/signup-consent-policy |
| PR10보류 | feat/backend-pricing-notes-oauth |

WIF/Cloudflare 연결 branch 이름 삭제·변경 금지. fix/login-release-prerequisites는 옛 단기작업선, 새 작업 기준 아님. 이번에 새 branch/PR 생성 없음.

- [PR24 / CP041~052](https://github.com/illumin8-dev/richon-academy/pull/24)
- [코드 배포 완료 CP052](https://github.com/illumin8-dev/richon-academy/pull/24#issuecomment-5811515427)
- [이전 상세지도 CP049 보존본](https://github.com/illumin8-dev/richon-academy/blob/32b5ef1f595760337ee845e1713e714b72ff689b/PROJECT_STATUS.md)
- [PR23 / 이전 배포·사용자 정책 확정](https://github.com/illumin8-dev/richon-academy/pull/23)
- [GitHub 쓰기 복구](GITHUB_WRITE_RECOVERY.md): 함수노출/계정권한/플랫폼안전거절 구분. 최신blob확인→승인쓰기→원격재조회. 권한거절우회 금지.
