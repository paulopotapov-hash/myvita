# Phase F1 frontend audit

Audit performed against commit `f5eb6c0` on 2026-09-24. The source of truth was the FastAPI routers and Pydantic schemas currently present on `main`, not roadmap documentation.

## WORKING

- React 19, Vite, TypeScript, Tailwind and TanStack Query are already configured.
- Cookie-based authentication uses `POST /api/v1/auth/login`, `GET /api/v1/auth/me` and `POST /api/v1/auth/logout` without storing JWTs in browser storage.
- The shared API client sends credentials, echoes the signed CSRF cookie on unsafe methods, parses FastAPI validation errors and preserves request IDs.
- Protected and role-aware routes, responsive application shell, loading/error/empty components and Portuguese API error messages exist.
- Clinic onboarding, patient registration, staff creation/listing, patient directory listing and appointment listing/creation are wired to real endpoints.
- Role-specific dashboards show only values derivable from the existing clinic, patient, staff and appointment APIs.
- Vitest coverage exists for the API client, login, route guards and application layout.
- F1 now adds deterministic operational-401 handling, redirect restoration, cache isolation across
  identities, patient-detail navigation, appointment detail/duration, and the staff/admin B5 consent UI
  using the existing architecture.

## BROKEN

- Before F1, the appointment page called the staff-only patient-directory endpoint for patient sessions.
- Before F1, `LoginPage` understood `state.from`, but `ProtectedRoute` never supplied it.
- Before F1, an operational 401 could leave private cached data active.
- These three defects are fixed by this branch and covered by tests.

## PARTIALLY WORKING

- Patient detail is composed safely from the clinic patient list and appointment list because no patient-detail endpoint exists.
- Appointment detail is presented from list data; mutations beyond creation cannot be offered.
- Role dashboards use real API values, but notifications and clinical-module summaries are unavailable.
- The current backend exposes a single `staff` user role plus `Staff.staff_role` (`doctor`, `nurse`, `admin`). The session response does not include `staff_role`, so the frontend cannot reliably distinguish doctor, nurse and administrative staff for route decisions without an additional lookup/mapping.

## MISSING

- Medical-record, medication and notification application workflows.
- Appointment update and cancellation actions.
- Patient self-service consent navigation, because the authenticated patient cannot discover their patient UUID.

## BACKEND EXISTS / FRONTEND MISSING

- None among the routes present in this checkout: the previously missing B5 consent routes are integrated by this branch.

## BLOCKED BY BACKEND

The current backend does **not** contain the advanced APIs described in the phase context. Its routers expose only authentication, clinics, patients, staff, appointments and consents.

- No patient-detail endpoint. `GET /api/v1/patients` returns only `id`, `clinic_id`, `full_name`, `birth_date` and `phone`; it has no national health number or active state.
- No patient list pagination or search/filter contract.
- No appointment detail, update or cancellation endpoint; only list and create exist.
- No medical-record endpoints or revision/version schemas.
- No medication endpoints.
- No notification endpoints or unread count/read action.
- No endpoint returning the authenticated staff profile/`staff_role`.
- No way for an authenticated patient to resolve their own `Patient.id`; `/auth/me` returns only `User.id`.

F1 can safely complete authentication behavior, dashboard improvements, the available patient directory/detail shell, appointment list/create/detail presentation, and full consent management. Update/cancel, medical records, medication, notifications, and fine-grained doctor/nurse/administrative UI cannot be implemented end-to-end without backend contracts and must remain clearly unavailable rather than mocked.
