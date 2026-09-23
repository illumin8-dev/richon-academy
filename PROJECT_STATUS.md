# 리치온아카데미 / 작업·배포 지도

마지막 실제 확인: 2026-09-24. 앞으로는 이 문서 → 해당 GitHub 실행 결과 → 실제 환경 순으로 확인한다. **코드 병합과 실제 사이트/서버 배포를 구분한다.** 오래된 PR의 당시 상태를 현재 상태로 간주하지 않는다.

## 지금 상태

| 항목 | 실제 결과 |
|---|---|
| 최신 v7 히어로 → index | 구현·7개 브라우저 검사 완료 / 작업 저장소 main에 PR #18 병합 |
| 실제 홈페이지 원본 반영 | **미완료.** marururu00 저장소의 PR 생성·branch 생성 모두 연결 앱403으로 거부 |
| PR #4 주문 테스트 | 최신 백엔드 검증 후 병합 완료 |
| PR #10 가격·고객 메모 | 사용자 지시로 보류 / source·가격·SQL 변경 없음 |
| 브랜치 정리 | **실제 삭제 완료. 5개만 남음.** 삭제한23개(이번 임시2개 포함)는 모두 archive 태그로 보존 |
| 새 로그인 서버 배포 | 미완료. DB008/Access 확인 및 네이버 runtime연결이 남음. 이번 작업에서 Cloud Run을 변경하지 않음 |

## 어디에서 작업하나

공개 홈페이지 원본은 `marururu00/richon-academy/main`이다. 현재 원본은03f4da08cefa15ec4dfab882788fc52983c8d084이며 이번 히어로 업데이트를 받지 못했다. 작업용 fork의 main과 동일하다고 말하지 않는다.

작업 저장소 `illumin8-dev/richon-academy`에는 아래5개 branch만 남겼다.

| 역할 | 브랜치 | 사용 방법 |
|---|---|---|
| 홈페이지 소스 | `main` | 검증된 새 히어로와 이 문서. 원본 권한 복구 후 원본 main에 PR |
| 로그인·관리 서버 | `feat/backend-portal-deploy` | **백엔드 후속 작업의 단일 통합 기준** |
| Cloudflare 연결 | `feat/backend-social-login` | Worker Git 배포 경로. 필요할 때 edge 파일만 정합 반영 |
| 기존 주문 서버 | `feat/backend-gcp-deploy` | 기존 WIF 배포 호환 경로. 변경할 일이 없으면 그대로 둠 |
| 보류 | `feat/backend-pricing-notes-oauth` | #10을 재개할 때만 사용. 단독 SQL 적용 금지 |

WIF/Cloudflare에 연결된 branch명을 이번에 바꾸지 않았다. 이름만 바꾸면 외부 설정이 깨질 수 있다. 새 기능은 해당 기준에서 짧은 branch를 만들고 검증·통합 후 정리한다. 단계별 branch를 다시 계속 쌓지 않는다.

## 완료된 히어로 작업

- 원본 main03f4da08과 승인된 v7 index-test blob b24ad4cb1b573b51264bc74f1665b690e30c7c13을 대조했다.
- OFF→ON 전환·모바일 이미지·마지막 문구 배치를 index.html에 이관했다. 새 이미지 생성은 없다.
- 실제 후기/과정/강사/푸터/하단 신청 CTA의 HTML은 기존 원본과 byte-identical로 보존했다. preview 더미·인터랙션 비활성화 코드를 이관하지 않았다.
- 추가 파일: assets/hero/home-hero.css, home-hero.js, richon-hero-desktop.webp. 기존 모바일 WebP 그대로 사용.
- JS-off/reduced-motion과 모바일 메뉴 상태/앵커/신청 경로를 확인했다.
- [검증 run35894740143](https://github.com/illumin8-dev/richon-academy/actions/runs/35894740143): Chromium320/390/768/900/1440px + reduced-motion + JS-off **7개 시나리오 성공**. 원본 본문 보존·이미지·overflow·JS 오류·메뉴·신청 이동 검사.
- 검증 source d2bd7308ea716572cda8b603300a3935715d5975 / 최종 생성 source6edd629621ee58dd31d8da267c71f9f881755126 / 작업 저장소 병합 [PR #18](https://github.com/illumin8-dev/richon-academy/pull/18), a6700a7f800b87507daa259a77525d02cd439d9d.
- index blob8802d344cd484b13367e8852f50ada63d54be93e / CSS2076eef18f53556dee413e2004239368986e53e9 / JSdfa25abfefcb9c67754ba8a0eafa859c0984e94c / desktop e3051bec26ce4ca2160ab8a96fd7169dd382683e.

**원본 반영 차단의 실제 응답:** `403 Resource not accessible by integration`. 원본 repo metadata의 사용자 push:true와 연결 앱의 실제 쓰기 요청 결과는 다르다. 원본 계정/저장소의 앱 설치·저장소 허용 범위를 확인해야 한다. 내부 설정은 조회하지 못했으므로 어느 체크박스가 잘못됐다고 확정하지 않는다. 다른 계정이나 토큰으로 우회하지 않는다. 작업 fork에서는 코드 생성·병합·정리가 실제 성공했다.

원본 쓰기 권한 확인 후 최신 원본main을 다시 읽고 작업 forkmain의 히어로5파일 변경만 PR/검증/Pages 배포한다. 코드·이미지·디자인을 다시 만들 필요 없다. 전체 backend를 원본main에 합치지 않는다.

## 완료된 PR #4 / 보류한 #10

#4를 최신 backend로 retarget하고 원본240줄 테스트만 추가한 head bd339ca919e7dc4e7f6f4b3df4c46ed45bcb3296을 검증했다. Backend/PostgreSQL/Docker35893635153, Login35893634834, Edge35893634316 모두 성공. 실제 병합 a0ef6fc4108bf9ffa3e20901aabbf2e925a71982. runtime·운영 주문·DB·배포요청 파일 변경은 없다.

#10은 **나중에 진행**한다. source2498c38743a4655a36e89331a45b99c570b7f3ee를 그대로 보존했다. 과거 base branch를 정리하기 위해 PR 비교 대상만 현재 backend로 변경했고 Draft를 유지했다. 완성된 기능이 아니며 이전 OAuth 파일을 현재 파일 위에 그대로 덮어쓰면 안 된다. 가격1/2/6개월 및 고객 메모는 폐기가 아니라 보류다.

## 실제 브랜치 정리 결과

[정리 run35895921493](https://github.com/illumin8-dev/richon-academy/actions/runs/35895921493) success 후 GitHub branches를 다시 조회해5개만 남고 유지 대상 커밋이 변하지 않은 것을 확인했다.

- 각 대상의 정확한 tip을 `archive/2026-09-24/<이전 branch명>`으로 먼저 저장하고 읽어 대조했다.
- 열려 있는 PR의 head/base 의존성과 보호 상태를 검사했다.
- 삭제 직전 목록을 재검사하고 **exact-SHA lease와 atomic push**로23개 branch를 한 번에 삭제했다. 보호 규칙을 끄거나 보존 branch 이력을 덮어쓰지 않았다.
- 임시 검증/정리 branch도 archive 후 제거했다. 태그는 복구점이며 활성 개발 branch가 아니다.
- 복원은 필요한 archive 태그의 commit에서 새 branch를 만드는 방식이다. 고객 데이터나 클라우드 자원을 삭제한 것이 아니다.
- #4/#18은 실제 병합. #11/#13은 배포 branch와 코드를 보존한 채 누적 기록 PR만 종료했다. 앞으로 열린 PR 목록에서 운영 기록을 미완성 기능으로 착각하지 않는다. 열린 작업은 보류#10뿐이다.

첫 정리 실행은 metadata용 빈 경로를 과도하게 거부한 코드 오류로 쓰기 전에 멈췄다. 고정 repo metadata 읽기만 허용하도록 수정한 후 위 최종 실행을 완료했다. 원본 저장소403을 해결했다고 주장하지 않는다.

## 다음 작업 순서

1. **원본 홈페이지 권한·배포:** marururu00/richon-academy에 연결 앱 접근을 확인 → 이미 검증한 히어로 변경 원본main 반영 → Pages와 실제 URL 확인.
2. **카카오 테스트 서버 반영:** 운영 DB008 상태 확인·필요한 변경 / Access 확인 / 최신 backend와 Worker 정합 배포. 본인 이메일 제한 유지.
3. **네이버 실제 연결:** 이미 만든 Secret의 활성 숫자 버전/IAM/env 바인딩 검증·연결. 앱 재등록이나 키 재발급을 반복하지 않는다.
4. **실계정 동선 검사:** 신규/기존 로그인, 동의 거부·취소, 로그아웃, 이전 페이지 복귀, 일반회원의 관리자 접근 차단.
5. **정식 개인정보 처리·회원 생명주기:** 실제 수집항목/목적/연락처/보유기간/위탁·국외이전 확정 → 약관·방침·가입 동의 일치 → 탈퇴·연결해제·외부 통지·세션 회수·파기 구현/검증.
6. **검수·제한 공개:** 실제 가입 동선과 정보 활용 화면으로 제출 자료를 만들고 필요한 제공자 검수 진행. 공개 접근 변경은 별도 승인.
7. **보류 기능·결제:** 재개 지시 후 #10 가격·고객 메모와 관리자 운영/기존 명단 이관. PortOne 준비 후 결제 확인·웹훅·환불·수강 권한·영수증을 별도 검증.

마지막 실제 Cloud Run 관측(run35887959276)은 revision richon-portal-gh-35810692921-1, 원본 키 없음/오류403 edge_required, Naver runtime binding 없음, Access inconclusive였다. 이번 작업에서 재배포/DB 변경/새 GCP 조회를 하지 않았다. DB008은 Neon 도구의 project_id 입력 스키마 문제로 상태 확인 전이다. 이 과거 관측과 최신 운영 사실을 혼동하지 않는다.

## 재개 원칙

커밋/검사/배포/오류 단위로 완료·미완료·다음 시작점과 SHA를 남긴다. 최신 refs와 실행 결과를 재조회한 뒤 이어간다. 운영 DB 변경/배포를 기록만 보고 반복하지 않는다. 모의 OAuth/CI DB 성공을 실사용자 로그인 성공으로 표현하지 않는다. 실제 이메일·계약·보유기간은 추측하지 않는다. 키·쿠키·인가코드·고객정보를 Git/로그/artifact에 저장하지 않는다. TinyFish 유료 자동화는 별도 승인 없이 사용하지 않는다.

과거 기록은 [PR #13](https://github.com/illumin8-dev/richon-academy/pull/13), [PR #17](https://github.com/illumin8-dev/richon-academy/pull/17), 이번 결과는 [PR #18](https://github.com/illumin8-dev/richon-academy/pull/18)에서 확인한다. 모두 과거 실행의 증빙이며 새 작업의 승인 자체를 대신하지 않는다.
