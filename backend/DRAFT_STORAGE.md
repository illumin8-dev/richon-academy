# 보관용 초안 — 병합·배포 금지

2026-09-22 사용자가 기존 로컬 초안을 GitHub에 보관하고 PR을 만들도록 요청했습니다.
기준: PR #9 병합 커밋 6dac44608785c535f6170dcf0999183228da3c7c.

## 현재 원격에 보관한 범위

이 커밋은 이전 작업에서 GitHub 객체 생성에 성공한 아래 다섯 파일을 작업 브랜치에 연결합니다.
- backend/pricing.py: 리치온 1/2/6개월 99,000/176,000/495,000원 요금표와 할인 계산.
- backend/pricing_notes_migrate.py
- backend/migrations/006_pricing_notes.sql
- backend/oauth_migrate.py
- backend/migrations/007_oauth_handoff.sql

화면과 서버 연결을 끝낸 PR이 아닙니다. 새 마이그레이션을 실행하지 마세요.
월별·수동 등록 API에는 아직 이전 기간 규칙이 남아 있으며 이 파일들만으로 운영하면 안 됩니다.

## 저장되지 않은 범위

로컬 richon-pricing-notes-oauth-draft.zip에는 가격 선택 UI, 고객 메모 API/UI, OAuth 제공자·HTTP·저장소 모듈과 테스트가 함께 있습니다.
이번 시도에서도 OAuth 모듈이 포함된 파일 반영 요청은 도구의 보안 상태 확인 단계에서 차단됐습니다.
차단된 OAuth 코드를 다른 파일명·인코딩·워크플로로 우회 반영하지 않았습니다.
PR은 일부 코드만 보관한 Draft이며 전체 로컬 초안의 백업이 아닙니다.

## 검증 경계

이전 로컬 초안 검사: 288 passed / PostgreSQL 필요 92 skipped. 이는 이 부분 커밋의 통합 검증 결과가 아닙니다.
실제 OAuth 앱, Neon, Cloud Run, PG, 고객 데이터를 사용한 검증은 하지 않았습니다.
운영 사이트·main·배포 설정·IAM·비밀키·고객 데이터는 변경하지 않습니다.
