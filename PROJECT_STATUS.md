# 리치온아카데미 / 작업·배포 지도

최신 재개 확인: **2026-09-24 / CHECKPOINT-049 / PR24**.
이 문서 → 해당 PR의 최신 체크포인트 → 실제 ref·CI·운영 상태 순서로 확인한다. 활동 카드의 '구현 완료'만으로 커밋·검증·배포를 단정하지 않는다.

## 지금 어디까지 완료됐나

**PR24의 가입정보·동의 처리, 마이페이지 정보 표시와 약관·개인정보 문서 개정안은 원격에 저장되어 있고, 정확한 head의 자동검사 4개가 모두 성공했다. 다시 작성하지 않는다. 아직 PR 병합, 운영 DB009 적용, 추가 수집 활성화, 새 서버 배포, 공개 방침 교체는 하지 않았다.**

- 작업 PR: https://github.com/illumin8-dev/richon-academy/pull/24
- 작업 branch: `feat/signup-consent-policy`
- 검증 완료 head: **`9ae550a9bc53fed5e0e785f3a9fb21b274730cc5`**
- base: `feat/backend-portal-deploy` / `cefbbcf41678ff02bfe0facec077bfc0b17774fd`
- PR 상태 재조회: open / draft=false / merged=false. 코드 검토 가능 상태와 실제 출시 가능 상태는 다르다.
- 세부 기록: 해당 head의 `backend/SIGNUP_POLICY_RELEASE.md`, `backend/policy_drafts/member-info-v1/README.md`, PR24 CP045~049.

생각 실패 보고 후 재조회에서 위 코드와 CI가 이미 저장된 것을 확인했다. 기존 main의 이 지도만 CP034에 머물러 있어 최신 상태로 갱신했다. 플랫폼의 실패 원인을 진단하거나 고쳤다는 뜻은 아니다.

## 사용자가 확정한 기준 / 다시 묻거나 임의 변경하지 않음

| 항목 | 결정 |
|---|---|
| 가입 연령 | 간편로그인 시작 전 만14세 이상 자기확인. 실제 나이·실명 본인인증이 아님 |
| 필수 가입정보 | 이름(닉네임 아님), 휴대전화번호, 이메일. 가입 직후 필요 |
| 선택 상담정보 | 연령대·성별 / 상담 내용 준비 및 상담 진행. 미동의 시 서버에 저장하지 않음 |
| 계정 식별 | 제공자·앱·이용자 식별자. 이름·전화·이메일 일치로 자동 통합하지 않음 |
| 로그인 안내 | '회원 관리와 상담에 필요한 정보를 수집합니다.' 및 상세 안내. 과도한 긴 본문 노출 지양 |
| 약관 | 주식회사 표기 제외, 간편로그인 방식, 전용 비밀번호 수집 없음 |
| 결제 | 카드번호·카드 비밀번호 등 결제 인증정보는 PG 처리, 리치온 직접 저장 없음. 거래기록과 구분 |
| 문의 | 032-236-8944. 공식 이메일은 사용자 추후 제공, 임의 주소 삽입 금지 |
| 공개 화면 | 메인 로그인·마이페이지 버튼은 계속 비노출. 히어로·강의 신청 유지 |
| 우선순위 | 기능 우선, UX/UI 미화는 후속. PR10·명단 이관·결제 보류 |

## PR24에 저장된 구현

- `member_profile.py`, `member_profile_store.py`, `signup_views.py`, `oauth_http.py`: 입력 검증, 연령 자기확인, 필수/선택 동의, 등록정보 저장. 양쪽 정책 버전을 `member-info-v1`으로 명시할 때만 새 수집 흐름 활성화.
- `migrations/009_member_profiles.sql`, `member_profile_migrate.py`: 최소 추가 스키마와 명시적 적용 도구. 운영 실행은 하지 않음. 가입 ticket 소모와 프로필·동의 저장을 하나의 트랜잭션으로 처리. 기존 회원 ID 보존.
- `portal.py`, `portal_store.py`, `portal_static/mypage.html`, `portal_static/portal.js`: 본인의 이름·전화·이메일·연령대·성별·선택동의·등록시점 표시. 구 버전 응답에 없는 개인정보를 만들어 표시하지 않음. 인증상실·로그아웃·pagehide 시 비우고 늦은 응답의 재표시도 검사.
- 입력한 연락처는 소유 인증된 정보라고 표시하지 않음. 제공자 콘솔·scope 확대 및 연락처 자동채움은 이 PR에서 변경하지 않았다. 이름이 없으면 직접 입력하며 닉네임으로 대체하지 않음.
- `backend/policy_drafts/member-info-v1/terms.html`: 승인된 가입 관련 조항의 교체안. 전체 약관 대체본이나 환불 조건의 최종 승인이 아님.
- 같은 폴더의 `privacy.html`: 필수/선택 수집·목적·기간·거부권, 운영 구조와 미확정 사항을 구분한 시행 전 개정안.
- 같은 폴더의 `README.md`: 기존 문구와 수정안의 대조 및 출시 전 확인 목록. 문서 draft는 런타임 이미지·라우트에 포함하지 않음.

## 마지막 CI / 정확한 head 9ae550a9

2026-09-24 CP049에서 아래 네 workflow의 completed/success를 다시 조회했다. 재실행한 것이 아니며 실제 이용자 DB·OAuth 계정 시험도 아니다.

| 검사 | run | 결과 |
|---|---|---|
| Backend / 폐기용 PostgreSQL / Gcloud 업로드 목록 / Docker | 35975741193 | success |
| 로그인·공식 버튼·새 가입폼 Chromium 및 backend 회귀 | 35975741580 | success |
| Edge / 포털 이미지 | 35975741215 | success |
| 마이페이지·관리자 UI / 새 등록정보·개인정보 비우기 | 35975741244 | success |

이전 head의 파일 포함 목록 실패·제한 DB 권한 문제·문구 검사 실패는 이 최신 성공 결과와 구분한다. 과거 실패 로그를 읽고 동일한 수정을 반복하지 않는다. 구체적인 시험 개수는 로그에서 확인하지 않고 새로 합산하지 않는다.

## 실제 서비스 상태 / 새 가입정책과 구분

기존 카카오·네이버 로그인 기본 흐름과 리치온 로그아웃은 사용자가 성공을 확인했고 마이페이지 화면도 공유했다(PR23 CP035~039). 모든 취소·권한·세션 시나리오의 독립 검증을 의미하지 않는다. 이를 다시 처음부터 시험하거나 키·DB008·BIC를 재설정하지 않는다.

아래는 **마지막 배포 확인 CP034의 기준**이다. CP049에서 Cloud Run·DB·Cloudflare를 다시 조회하거나 변경하지 않았다. 실제 전환 전에 살아 있는 태그와 설정을 재확인한다.

| 구분 | 마지막 확인 값 |
|---|---|
| 사용자 로그인 URL | https://richonacademy.com/auth/login |
| 마이페이지 URL | https://richonacademy.com/portal/mypage |
| Worker branch / ref | feat/backend-social-login / b7f4b6d3a37c15d37b59917d73f49b1e23640e5f |
| Worker | richon-account-router / Version c01d6cd7-4e2c-4c53-8b51-94b2bd9a31bb |
| Worker upstream | https://portal-candidate---richon-portal-amjmgyepbq-as.a.run.app |
| 실제 연결 후보 | richon-portal-gh-35946050229-1 / source d0b2c7389b2394de9c6bfd110c3e7933a90d38f5 |
| 후보 image digest | sha256:b5db98ff97299c81ff36aac7ec5e0364e5f1bf1da54af80dc38efd5783aa3495 |
| 네이버 Secret 참조 | richon-naver-client-id:1 / richon-naver-client-secret:1 |
| 기본 Cloud Run URL | https://richon-portal-amjmgyepbq-as.a.run.app |
| 기본 URL 롤백 revision | richon-portal-gh-35810692921-1 / 기본 URL 트래픽100% |
| 기존 정책 버전 | internal-test-v1 / 새 member-info-v1은 미활성화 |

Worker는 태그 URL을 통해 후보에 연결되어 있으므로 기본 URL의 후보0%를 미연결로 해석하지 않는다. **현재 쓰는 portal-candidate 태그를 새 stage로 무심코 옮기지 않는다.** 롤백은 승인 범위에서 Worker upstream을 기본 URL로 복원하는 방식이며 DB/IAM을 자동 역변경하지 않는다. 본인 이메일 Access 제한은 유지한다. 비노출 메뉴를 접근통제 대체수단으로 취급하지 않는다.

## 다음 작업 / 실제 적용 전 남은 것

1. **미확정 운영정보 확정**: 공식 이메일, 실제 계약 수탁자 법인·국가·연락처, 로그·백업 보유기간, 권리행사 채널. GCP/Neon뿐 아니라 Cloudflare 및 공개 호스팅·외부 리소스의 실제 처리 범위를 대조한다. 답을 추측하지 않는다.
2. **탈퇴·선택동의 철회·연결해제·파기 절차**: 아직 미완료. 처리 방법·보존 대상·실패 시 처리부터 사용자와 확정한 뒤 별도 구현한다. 가입정책 수정 승인을 개인정보 일괄 삭제 승인으로 확대하지 않는다.
3. **최종 문서와 버전 정합성**: 승인된 조항을 기존 root 약관에 통합하고 개인정보처리방침과 실제 동작·URL·시행일을 일치시킨다. 미검토 환불·가격·수강권 조항을 임의로 재작성하지 않는다.
4. **DB009·최소권한·후보 배포**: 준비 상태와 롤백을 확인해 별도로 적용·검증한다. 추가 수집 버전에서 기존회원 정보 보완, 선택 미동의 가입, 마이페이지, 로그아웃을 실제 시험한다. 일반 공개·메인 메뉴 노출은 별도 승인이다.

공식 이메일은 추후 제공하기로 한 미확정 항목이다. 미확정 값을 채워 넣거나 이미 구현한 부분을 다시 설명·승인 요청하는 것으로 작업을 반복하지 않는다.

## 저장소·브랜치 역할

공개 홈페이지 원본은 **marururu00/richon-academy/main**이다. 작업용 fork main과 혼동하지 않는다. 원본 PR8·Pages 배포·사용자 화면 확인으로 히어로는 완료됐다.

| 역할 | illumin8-dev/richon-academy branch |
|---|---|
| 홈페이지 작업 / 이 상태 지도 | main |
| 로그인·관리서버 통합 / GCP | feat/backend-portal-deploy |
| 실제 Worker Git 배포 | feat/backend-social-login |
| 기존 주문서버 WIF 호환 | feat/backend-gcp-deploy |
| 이번 승인된 가입정책 PR24 | feat/signup-consent-policy |
| PR10 보류 초안 | feat/backend-pricing-notes-oauth |

fix/login-release-prerequisites는 PR23에서 사용한 단기 branch다. 이 표는 역할 안내이며 전체 branch 목록의 재조회 결과가 아니다. WIF/Cloudflare가 연결한 branch 이름을 임의 변경·삭제하지 않는다. 새 PR/branch를 만들지 말고 PR24에서 이어간다.

## 복구 및 근거

- GitHub 쓰기: [GITHUB_WRITE_RECOVERY.md](GITHUB_WRITE_RECOVERY.md). 정확한 함수 조회 → 계정·대상·최신 blob 확인 → 승인된 쓰기 → commit 재조회. 도구 노출과 API 권한/안전 거절을 구분하고 거절을 우회하지 않는다.
- [PR24 / CP041~049](https://github.com/illumin8-dev/richon-academy/pull/24): 이번 코드·CI·문서와 미배포 범위.
- [PR23 / CP034~040](https://github.com/illumin8-dev/richon-academy/pull/23): 실제 로그인 연결, 사용자 성공 확인, 메뉴 비노출 및 가입정보 확정.
- [갱신 전 배포 지도 원본](https://github.com/illumin8-dev/richon-academy/blob/77a9ff60fc4387fc548cf027795c9906f64120a9/PROJECT_STATUS.md): CP034 상세 사전/사후 검사, 회귀 수정, 과거 branch 보존 이력.

CP049의 변경은 이 진행 문서와 PR 기록뿐이다. 앱 코드, 배포 request, 운영 DB/IAM/Secret/CloudRun/Worker/Access/공개 홈페이지는 바꾸지 않았다. TinyFish 미사용.
