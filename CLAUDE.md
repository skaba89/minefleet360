# MINEFLEET 360 — Project Rules

MINEFLEET 360 is a multi-tenant, multi-site mining transport and fleet operations platform intended initially for Guinea. French is the default UI and documentation language; English technical identifiers are acceptable.

## Non-negotiable instructions
- Inspect repository and current implementation before modifying anything. Never claim tests have passed unless run.
- Prioritize data isolation, security, traceability and correctness over speed. Every tenant-owned read/write must be tenant-scoped and authorized; test against IDOR and cross-tenant access.
- Do not hard-code secrets, tokens, passwords or sample real personal information. Do not use real employee tracking data for demos.
- Do not add speculative modules or unnecessary dependencies; use a modular monolith first.
- No production deploy, paid service provisioning, DB destructive operation or irreversible migration without explicit approval.
- Before substantial changes: state plan, files to modify, acceptance criteria and verification approach. Use small vertical slices and tests.
- Give agents bounded missions; run security and QA reviews after each business feature.
- Maintain migration discipline (Alembic), API contracts (OpenAPI), structured logs, audit events, UTC storage and explicit display timezone.
- GPS is not proof of payload tonnage: require weighbridge or approved data source for measured loads. Geofencing needs valid coordinates, poor-connectivity offline sync and clock skew tolerance.
- Respect lawful monitoring practices, worker privacy, retention policies and access controls. Validate Guinea-specific compliance requirements with local legal counsel before production.

## Target stack (adapt if existing repository differs)
- Backend: Python / FastAPI, SQLAlchemy, Alembic, Pydantic.
- Database: PostgreSQL with PostGIS; Redis and object storage if justified.
- Frontend: React, TypeScript; responsive UI; mobile/PWA with offline mode for field users.
- Tests: pytest (API), Vitest and Playwright (web), integration/tenant-isolation tests.
- CI: lint, types, tests, migration verification, dependency scanning.

## Delivery process
1. Read docs/PRODUCT_VISION.md and docs/ROADMAP.md.
2. Clarify only true blockers; otherwise record assumptions.
3. Define acceptance criteria and data authorization matrix.
4. Implement feature + migration + tests + documentation.
5. Run available checks, identify what was not executed.
6. Summarize diff, risks, remaining tasks and recommended next slice.
