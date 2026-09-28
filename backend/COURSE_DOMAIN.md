# Course domain decisions / 2026-09-28

## Confirmed product decisions
- Program → run/cohort → session → enrollment.
- Pre Richon uses a fixed 2-month access model.
- Richon Study uses a date-range access model.
- Each session stores its date/time, title, mentor and future content link.
- Recruitment states: OPEN / WAITLIST / UPCOMING / CLOSED.
- Enrollment states: SCHEDULED / ACTIVE / COMPLETED / CANCELLED / SUSPENDED.
- Enrollment state and payment state stay separate.
- Existing learner records are never auto-linked to a member only because name/phone match.
  Candidate matches may be suggested, but an administrator must approve the link.
- My Courses shows program, run/cohort and sessions.
- Admin navigation target: dashboard / courses / learners / members / applications-orders / mypage.
- Payment/PG work is deferred until the above learning-management flow is complete.

## Migration boundary
Migration 015 adds the canonical domain alongside the existing courses/monthly/manual tables.
It does not seed real programs, members or enrollments, and it does not rewrite or delete legacy records.
