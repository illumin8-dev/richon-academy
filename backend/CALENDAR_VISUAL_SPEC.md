# Richon Calendar Visual / Interaction Spec

Status: owner-approved / 2026-10-02

## Canonical visual
The owner-provided October 2026 Richon calendar is the visual reference.

- white poster-like canvas
- Richon geometric navy/gold mark above the month title
- title: `YYYY년 M월 / 리치온 캘린더`
- fixed legend at upper-right
- weekday row uses Su..Sa
- Sunday red / Saturday blue / ordinary dates light gray
- event dates use rounded colored date blocks with white numbers
- event copy appears below the date with a same-color dot, course label, then optional content
- no spreadsheet-style vertical cell borders
- week separation uses horizontal dotted rules
- holiday/emphasis ranges tint exactly the covered dates and never expand into an adjacent date for label width
- consecutive covered dates in the same week form one connected soft background segment
- the label ribbon sits inside that connected segment and is rendered only once
- if a holiday crosses week rows, the label is placed on the row containing the most covered dates; ties use the earlier row
- the label is never split or repeated across week rows; later rows keep only their connected range tint
- mobile may use an agenda representation while preserving the same palette/content hierarchy

## Canonical October palette / legend
- #3978F6 / 재개발중급반
- #FF9F26 / 리치온 인테리어
- #D8BD78 / 무료 브리핑
- #FF5757 / 리치온 스터디
- #00B622 / Pre리치온
- #C000DB / 스터디 전체

These six values are the only operator-selectable calendar colors. Historical screenshots from June–September may show older shades/categories; future rendering and later historical import normalize to the October palette.

## Admin interaction
Calendar is independent from course_programs / course_runs / course_sessions.

Normal event fields:
- date
- color
- course label: free text
- content: free text and optional

Holiday / emphasis fields:
- start date
- end date, inclusive
- color
- banner text

Interaction:
- clicking an empty date opens the editor with that date prefilled
- clicking an event/banner opens edit mode
- event duplication uses the dates currently chosen by the operator; no +7-day or recurrence rule
- duplicated items remain independently editable
- the editor labels this action as `일정 복제` so it cannot be confused with image copying
- `PNG 복사` renders the current month as a standalone 1200×1200 PNG without admin chrome and writes it to the image clipboard
- successful clipboard copy changes the button itself to `✓ 복사 완료` briefly so success is unmistakable
- if image clipboard writing is unavailable, PNG file save is the fallback and the button shows `✓ PNG 저장`
- delete is soft delete
- course label suggestions are convenience only and never constrain free text

## Historical source
The owner supplied calendar screenshots for 2026-06 through 2026-10 as the source for a later historical data import. This visual-editor PR does not seed or rewrite production calendar rows.

## Public landing
Still deferred. After admin UX approval, landing should render from the same calendar data and visual hierarchy rather than inventing a second calendar design.
