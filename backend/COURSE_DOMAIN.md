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
- Calendar is the next product work; login-provider lifecycle and payment remain deferred.
- Real class meetings continue to use canonical `course_sessions`; they are not duplicated into a second schedule table.
- Non-course schedules use `calendar_events` with types BRIEFING / STUDY_ALL / SPECIAL / FIELD_TRIP / OTHER.
- Admin management surface: `/portal/calendar`.
- Admin stores exact Seoul date/time. Public landing calendar intentionally omits clock time.
- "다음 주로 복제" creates a new draft from the selected event with date +7 days; course sessions also propose the next sequence number.
- Landing placement is between Programs and Mentors.
- Landing defaults to the current Seoul month. Previous/next arrows are exposed only when the directly adjacent month contains public calendar data.
- Public calendar reads are same-origin through `/portal/api/public/calendar`, strip auth cookies at the Worker, and use a 60-second edge cache. Browser max-age remains zero.
- Public calendar PNG export renders a fixed 1200×1200 image and copies it to the clipboard where supported, with file download fallback.
- DB018 `calendar_events` and exact runtime grants must be prepared before rolling out the new portal image.
- No payment, OAuth provider, member identity, or entitlement semantics are changed by the calendar work.
