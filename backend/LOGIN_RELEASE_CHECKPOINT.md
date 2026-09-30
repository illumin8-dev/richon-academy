# 카카오·네이버 내부 시험 / 배포 선행 조건

2026-09-24 / 사용자 승인: 히어로 완료 확인 후 카카오 최신 서버와 네이버 연결을 진행한다. 개인정보·운영방침 문구와 PR #10은 나중에 진행한다. 검수 승인서나 일반 공개 완료 보고서가 아니다.

## 실제 상태 / 체크포인트014

원본 홈페이지 PR8 / Pages35897836106 성공 및 사용자 화면 확인 완료. backend a0ef6fc4108bf9ffa3e20901aabbf2e925a71982에는 PR4/14/16/17이 포함돼 있다.

읽기 전용 GCP run35899190553 / portal job107311068568: 제공 revision richon-portal-gh-35810692921-1, Naver runtime binding absent, 키 없음/오류403 edge_required, Access gateway inconclusive. Neon describe_project와 고정 branch SELECT 모두 project_id 누락 입력검사 오류. SQL은 실행되지 않았다. 이번 변경을 실제 DB008 적용·Naver 연결·서버 배포 완료로 표시하지 않는다.

## 소유자 준비 절차

GitHub 배포 계정에는 DB 소유자·Secret IAM 변경 권한을 부여하지 않았다. Owner/Editor나 직접 Secret Accessor를 추가해 이를 우회하지 않는다.

검증한 고정 커밋의 깨끗한 checkout에서 `bash ops/prepare_login_release.sh`는 읽기만 수행한다. `--apply`로 실행하고 `PREPARE LOGIN`을 입력해야 다음 두 변경이 가능하다.

1. 고정 project/service/endpoint/db/role, 선행001/002/007 체크섬, 기존007의 정확한 반환 경로와 제한 runtime을 확인한 후008 forward migration만 적용. 이미 올바르면 재적용하지 않는다. 두 return_to CHECK에 메인·신청 페이지를 허용하고 migration 이력을 기록한다. 회원·주문 데이터 변경 없음.
2. 기존 Naver Secret 두 개에 포털 runtime 한 계정의 읽기 권한만 추가. 기존 grant/다른 정책을 보존. Naver 값은 조회하지 않음. 이미 연결된 활성 숫자 버전은 유지하고, 미연결이면 활성 숫자 버전을 확인해 보고.

소유자와 runtime DB DSN은 기존 Secret Manager에서 실행 프로세스 메모리로만 읽는다. Git·콘솔·파일·명령 인자에 저장/출력하지 않고 TLS verify-full을 유지한다. GitHub Actions에서 이 소유자 helper를 실행하면 거부한다. 새 secret/비밀번호/DB 역할/프로젝트 권한/WIF를 만들지 않는다.

DB·IAM은 분산 트랜잭션이 아니다. 중간 실패는 적용 시도/확인 결과를 별도로 보고하고 자동 역변경하지 않는다. DB 단일 트랜잭션 후 제한 계정의 실제 접속·권한·constraint를 재검사하고 Secret grant는 각각 readback한다. 동시 외부 변경 탐지 시 중단한다. 출력은 secret 이름/숫자버전/상태뿐이다.

**이 helper는 이미지·트래픽·Worker·Access·키 값·정책 문구를 변경하지 않는다.** 성공 문구 `LOGIN PREREQUISITES READY`는 배포 완료가 아니다.

## 코드와 테스트

- `portal_readiness.py`: OAuth 활성 신규 앱은 pg_constraint의 정확하고 검증된 return_to CHECK만 인정.007 상태의 로그인 OFF bootstrap 유지. runtime DDL/마이그레이션 원장 SELECT 권한 추가 없음.
- `login_return_migrate.py`: 검증된 DSN을 메모리에서 전달하는 keyword 인자. 기존 CLI·체크섬·advisory lock·트랜잭션 유지.
- `.github/portal/common.py`: edge 모드에만 Naver 두 Secret의 고정 이름/짝지어진 숫자 버전 허용. plain/latest/단일 키/다른 Secret 거부. private/IAM/자원 가드 유지.
- `edge_ops.py`: 실제 Naver 참조 존재 상태 보고. 기존 stage-edge는 이미지의0% 후보만 만들며 승격하지 않음.
- 테스트: 실제 CI PostgreSQL catalog/제한 role, 비정상 CHECK 거부, 소유자 기본 읽기·취소·중단·부분 적용, Secret 범위/버전, 기존 private/edge 가드. CI 완료 결과는 PR에 추가 기록한다.

## 첨부 PDF / 공식 문서 대조

첨부 `네이버 로그인(네아로) 연동 완전 가이드`, 2026-04-28 수정19쪽을 체크리스트로 사용한다. Next.js 예제를 복사해 현재 FastAPI 구조를 바꾸지 않는다. PDF 요구, 공식 정책, 구현 선택을 구분한다.

| 근거 | 요구 | 현재 구현 / 남은 것 |
|---|---|---|
| PDF3쪽STEP1 | Secret 외부 노출 금지 | Secret Manager→서버만. 이번 숫자버전/짝 검증 추가. 운영 Naver 바인딩은 아직 없음 |
| PDF5쪽2-3 /11쪽 | response.id로 식별, email 금지 | provider+app+subject 사용. 이메일·전화·이름 자동 회원 병합 없음 |
| PDF8~9쪽STEP5 | state, 서버 교환·프로필 조회 | 기존 일회성 만료 state/브라우저 결합/서버 교환 유지. 모의 제공자·CI DB 검사와 실인증은 별개 |
| PDF11쪽 /17쪽S-1~S-5 | HTTPS, 서버 토큰, 안전 쿠키 | 고정HTTPS callback, Secret POST, Secure/HttpOnly/SameSite=Lax 세션, no-store, 코드·토큰 로그 금지 유지 |
| PDF11쪽토큰 저장·갱신 | 저장한다면 서버 암호화/갱신 | 현재 제공자 토큰은 교환 중에만 사용하고 영구 보관하지 않는 구현 선택. 내부 세션과 다름. 토큰 보관·갱신 예제를 구현 완료로 표시하지 않음 |
| PDF7쪽STEP4 /공식BI | 공식 버튼/동의전 문서열람 | PR16 공식PNG·동일48px·모바일 검사 완료. 운영 새 서버 배포 전. 최종 필수/선택 동의 안내는 후속 |
| PDF12~13쪽STEP7 | 실제 전체 가입동선/활용처/방침 증빙 | 실제 계정 검증 후 마스킹 캡처. CI를 운영검수 성공으로 표시하지 않음 |
| PDF11~12쪽STEP6 /17쪽D-1~D-4 | 탈퇴/revoke/파기/세션삭제 | 아직 미구현. 로그아웃≠탈퇴. 보유정책·실패재시도·재인증을 정해 별도 구현 |
| Kakao common연결해제 | 탈퇴 unlink/외부해제 반영 | 미구현. 웹훅과 브라우저 callback 구분, 전체Access 해제 금지 |
| PDF6~7쪽 /5쪽2-4 /13쪽 | 방침/scope/국외이전/사업자정보 | 사용자 지시로 문구 후속. 실제 이메일·계약·국가·기간·scope를 추측하지 않음 |

공식 확인2026-09-24:
- https://developers.naver.com/docs/login/api/api.md
- https://developers.naver.com/docs/login/bi/bi.md
- https://developers.kakao.com/docs/ko/kakaologin/common
- https://developers.kakao.com/docs/ko/kakaologin/design-guide

PDF의 버튼문구 고정 설명과 현 Naver BI의 목적별 문구변경 허용은 다르므로 이번에는 공식 원본을 그대로 사용한다. PDF의 mobile 권장용도와 FAQ14도 구분하며 소셜 로그인을 법적 본인확인으로 취급하지 않는다. 법률·기간·신고면제 숫자를 배포 코드/운영 방침에 그대로 확정하지 않는다.

## 다음 재개

소유자 준비 결과 →008/숫자버전/IAM readback →Naver env를 포함한 명시적 후보 배포 경로 검증 →후보 DB/쿠키/edge gate →owner-only Access 확인 →server/Worker 정합 반영 →실제 카카오·네이버 인증.

현재 stage-edge는 Naver 설정 갱신이나 edge 후보 승격 기능이 없다. 실제 준비 결과를 기준으로 명시적인 설정변경·검증 절차를 추가한다. 가드를 끄거나 임의 gcloud로 우회하지 않는다. Access inconclusive를 성공 처리하지 않는다. 이번 PR 병합만으로 배포가 완료되는 것은 아니다.

단계마다 PR/문서에 결과를 남긴다. 히어로/#4는 완료. #10·문구 수정·TinyFish 사용은 하지 않는다.
