# UI decision audit / 2026-09-28

이 문서는 "완료" 표기와 실제 화면이 어긋나는 문제를 막기 위한 UI 결정 검증 기록이다.

## 공개 홈페이지 / 멘토 섹션

작업용 공개 소스 `illumin8-dev/richon-academy/main`의 실제 `index.html`을 기준으로 재검증했다.

- PASS / 리치온 초이 큰 대표 이미지 제거
- PASS / 상단 표기 "대표 멘토"
- PASS / 직함 "리치온 아카데미 대표 멘토"
- PASS / 별도 인사말 블록 없음
- PASS / 대표 설명은 시장 흐름 / 지역 분석 / 물건 검증 / 실행 판단 중심의 간결 문구
- PASS / 하단은 "실전 멘토" 6명 간단 소개
- PASS / 실전 멘토 개인 강의 링크 없음
- DEFERRED / 강의별 주차 담당 강사는 course 데이터/상세 화면 구현 시 강의 안에서 표시

중요: 위 PASS는 working copy 기준이다. 원본 공개 저장소 `marururu00/richon-academy` 반영 여부와 실제 배포는 별도 확인하며, working copy PASS를 production 완료로 표현하지 않는다.

## UX/UI family 경계

- Public + member: `frontend/shared/header.html`, `footer.html`, `site.css`, `site.js`를 정본으로 사용한다.
- Auth standalone: 공용 chrome + `auth.css`를 사용한다. 별도 인라인 색상/폼 CSS를 정본으로 두지 않는다.
- Admin/operations: public header를 강제하지 않는다. `ops.css`에서 브랜드 색/타이포/기본 focus/token만 공유하고, admin/enrollments/manual의 정보밀도와 레이아웃은 각 화면 목적에 맞게 유지한다.

## 완료 판정 규칙

1. 문서 체크박스만으로 완료 판정하지 않는다.
2. 정본 source와 생성/배포 파일의 실제 byte/contract 검사를 함께 본다.
3. working copy / backend candidate / original public repository / production deployment를 구분한다.
4. 미구현 기능은 UI에서 동작 가능한 것처럼 표시하지 않는다.
