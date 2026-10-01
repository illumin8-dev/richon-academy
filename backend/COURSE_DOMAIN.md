# Course domain decisions / 2026-09-28

## Confirmed product decisions
- Program → run/cohort → session → enrollment.
- Pre Richon uses a fixed 2-month access model.
- Richon Study uses a date-range access model.
- Redevelopment / Interior / Subscription duration is configured per run and may differ by cohort.
- Each session stores its date/time, title, mentor and future content link.
- Recruitment states: OPEN / WAITLIST / UPCOMING / CLOSED.
- Enrollment states: SCHEDULED / ACTIVE / COMPLETED / CANCELLED / SUSPENDED.
- Enrollment state and payment state stay separate.
- Existing learner records are never auto-linked to a member only because name/phone match.
  Candidate matches may be suggested, but an administrator must approve the link.
- Administrators can grant or cancel entitlements manually without an application or payment.
- My Courses shows program, run/cohort, access period and sessions.
- Sessions can hold optional video/material links; empty links stay hidden until content is ready.
- Admin navigation target: dashboard / courses / learners / members / applications-orders / mypage.
- Payment/PG work is deferred until the above learning-management flow is complete.

## Migration boundary
Migration 015 adds the canonical domain alongside the existing courses/monthly/manual tables.
It does not seed real programs, members or enrollments, and it does not rewrite or delete legacy records.

## Current implementation boundary / 2026-09-29
- Migration 015 remains immutable as the existing canonical foundation.
- Migration 016 extends 015 with audit/version fields, run price, and optional video/material links.
- Production preparation confirmed DB004 / DB005 were previously absent from the migration ledger and schema, then applied DB004 → DB005 → DB015 → DB016 in one reviewed owner transaction.
- Exact `richon_portal_login` runtime privileges and restricted-runtime readback passed after migration.
- `RICHON_COURSE_DOMAIN_ENABLED=true` is enabled only on the protected `portal-candidate` path.
- Protected candidate: `richon-portal-course-36581021392-1`.
- Final `inspect-course-enabled` passed with Cloudflare Access / edge gate / default 100% Cloud Run traffic / IAM / Secret boundaries unchanged.
- Default 100% Cloud Run serving revision remains `richon-portal-gh-35810692921-1`; course enablement did not promote default traffic.
- Payment remains outside this implementation. Manual ADMIN grants are the first entitlement creation path.
- Real program/run/session data entry and authenticated owner-browser E2E remain operational follow-up, not schema implementation work.


## Central calendar decisions / 2026-10-02
- The admin calendar remains independent from `course_programs`, `course_runs`, and `course_sessions`.
- The owner-provided October 2026 calendar is the canonical visual standard; see `CALENDAR_VISUAL_SPEC.md`.
- Normal event fields are date / canonical palette color / free-text course label / optional free-text content.
- Holiday/emphasis entries use an inclusive start/end date range, canonical palette color, and free-text banner label.
- The six October palette values are server-validated; historical June–September colors normalize to this palette when imported later.
- Copy uses the dates currently chosen by the operator; there is no fixed +7-day or recurrence rule.
- The existing DB018/019 physical table remains in use. Holiday ranges reuse existing `ends_at`; no new calendar table or course relation is introduced.
- Runtime DELETE stays unavailable; admin delete remains soft delete.
- Rollout order for banner writes: new code can start on the existing DB019 free-form grant profile, then the owner applies the final reviewed visual profile that adds only `ends_at` write access.
- The public landing calendar remains deferred until the owner approves the real admin UX.
- No payment, OAuth provider, member identity, enrollment, or course-session semantics are changed by this visual-calendar work.
