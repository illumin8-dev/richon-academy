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


## Central calendar decisions / 2026-10-01
- Calendar work remains ahead of login-provider lifecycle and payment.
- The admin calendar is intentionally independent from `course_programs`, `course_runs`, and `course_sessions`.
- `course_sessions` remains available for future My Courses/video/material semantics, but `/portal/calendar` does not read or write it.
- Admin calendar input is exactly four operator-facing values: date / color / course label / content text.
- Course label and content are free text. Adding a new course never requires calendar schema/code integration.
- Color is selected from the UI dropdown and stored as a validated hex value; the database is not tied to a fixed course-to-color mapping.
- Copy behavior has no recurrence rule: select an existing entry, choose any target date, then copy. The source entry remains unchanged.
- Copying the fresh copy again to another arbitrary date is supported.
- Delete is soft-delete through `cancelled_at`; destructive table DELETE remains unavailable to the runtime role.
- DB018 remains the physical `calendar_events` table. DB019 adds free-form display columns without dropping tables/columns or linking course tables.
- Phase 1 stays admin-only. Public landing calendar remains deferred until the owner approves real admin-calendar UX.
- Approved Phase 2 behavior is preserved but not implemented here: Programs→Calendar→Mentors placement / current Seoul month / adjacent arrows only when data exists / public clock time hidden / 60-second edge cache / 1200×1200 PNG clipboard copy with download fallback.
- No payment, OAuth provider, member identity, enrollment, or course-session semantics are changed by this free-form calendar work.
