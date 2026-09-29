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
- The new course-domain runtime is feature-gated by `RICHON_COURSE_DOMAIN_ENABLED` and remains OFF by default.
- Production DB 015/016 application is not claimed here; code/CI must pass first and production migration is a separate explicit step.
- Payment remains outside this implementation. Manual ADMIN grants are the first entitlement creation path.
