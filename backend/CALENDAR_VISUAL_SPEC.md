# Richon Calendar Visual / Interaction Spec

Status: owner-approved / 2026-10-02

## Canonical visual
The owner-provided October 2026 Richon calendar is the visual reference.

- white poster-like canvas
- the navy/gold mark is the original Richon calendar logo traced from the owner-provided October reference, served as a reusable SVG asset
- title: `YYYY년 M월 / 리치온 캘린더`, always centered on the full calendar canvas regardless of legend width or presence
- upper-right legend is independently positioned and dynamic: it uses each normal event's actual course label and selected color for the viewed month; holiday/emphasis entries do not create legend items
- weekday row uses Su..Sa
- Sunday red / Saturday blue / ordinary dates light gray
- event dates use rounded colored date blocks with white numbers
- event copy appears below the date with a same-color dot, course label, then optional content
- no spreadsheet-style vertical cell borders
- week separation uses horizontal dotted rules
- holiday/emphasis uses Proposal B: no date boxes and no large range background
- covered holiday dates use the selected holiday color as text only
- every covered week row gets one thin ribbon spanning exactly the covered dates in that row
- the holiday label appears inside the ribbon only once, on the row containing the most covered dates; ties use the earlier row
- later/other covered rows show the same thin ribbon with no repeated label
- holiday ribbons never expand into an adjacent date
- mobile may use an agenda representation while preserving the same palette/content hierarchy

## Canonical October palette / dynamic legend
- #3978F6 / 재개발중급반
- #FF9F26 / 리치온 인테리어
- #D8BD78 / 무료 브리핑
- #FF5757 / 리치온 스터디
- #00B622 / Pre리치온
- #C000DB / 스터디 전체

These six values are the only operator-selectable calendar colors. The viewed month legend is built from the actual normal-event course-label/color pairs present in that month, deduplicating identical pairs. It does not substitute the palette's canonical sample label for the event's real course text. Holiday/emphasis entries are excluded from legend presence. Historical screenshots from June–September may show older shades/categories; future rendering and later historical import normalize to the October palette.

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
