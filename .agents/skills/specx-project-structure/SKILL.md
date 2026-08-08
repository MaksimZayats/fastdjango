---
name: specx-project-structure
description: Create or reshape a Python FastAPI service repo into the specx clean core/delivery architecture using packaged scoped foundation bases. Use when starting an API backend, adding the first src package, or establishing `AGENTS.md`, `core/`, optional local `foundation/`, `delivery/`, infrastructure, `ioc/`, migrations, and tests.
---

# specx Project Structure

Use this skill to create the repo shell and first runnable vertical slice. For
details, read `references/blueprint.md`.

## Workflow

1. For a fresh framework-neutral repo, start with `specx init <path>`. It creates
   packaging, strict tooling, root `AGENTS.md`, a small `core/health` use case
   and pure service, `ioc/container.py`, and mirrored unit tests. It
   intentionally omits delivery and infrastructure; add those packages only
   with real technology-specific behavior.
2. Preserve an existing import package declared by the repo. For a new repo,
   derive a lowercase underscore name, normalize every non-identifier
   character, and verify `name.isidentifier()` and
   `not keyword.iskeyword(name)`; distribution names and import packages need
   not be identical. If normalization still yields a keyword or leading digit,
   choose an explicit valid package name rather than emitting it unchanged.
3. Create `src/<package>/` and `tests/` packages with empty `__init__.py` files only.
4. Add `specx` as a runtime dependency and import base classes from
   `specx.core.foundation`, `specx.delivery.foundation`, or
   `specx.infrastructure.foundation`.
5. Use `core/<scope>/` as the main boundary. Put application packages at the
   scope root: `capabilities/`, `dtos/`, `entities/`, `exceptions/`,
   `gateways/`, `repositories/`, `services/`, and `use_cases/`. Put
   scope-owned technical adapters under `infrastructure/` only when real IO
   exists.
6. Add top-level `delivery/` for runnable framework apps, lifecycles,
   controllers, request/response schemas, and delivery-only services.
7. Add top-level `infrastructure/` for shared technical resources such as
   SQLAlchemy session factories, logging, telemetry, and external client
   factories. App-owned pooled clients live here even when only one scope
   currently consumes them; bounded short-lived clients may stay with the
   scope adapter.
8. Add `infrastructure/logging/` with a stdlib `LoggingConfigurator` and
   `LoggingSettings` for every new API repo.
9. Add `ioc/` for `diwire.Container` creation and explicit bindings.
10. Add `shared/` only for stable cross-scope application primitives such as
   unit-of-work contracts, clocks, ids, or errors.
11. Add `migrations/` with Alembic when SQLAlchemy models exist.
12. Build the first user-requested business vertical slice. The initializer's
   process-health slice is a framework-neutral composition example, not a
   readiness check. With a delivery framework, map or replace it deliberately:
   keep simple liveness at delivery, and use `core/health` for `/readyz` when
   readiness checks a required dependency or policy is shared across deliveries.
13. Create root `AGENTS.md` for every new repo. Include runnable project
   commands from `$specx-project-tooling` and specx boundaries from
   `$specx-component-architecture`.
14. Do not create an empty local `foundation/` package. Create
   `src/<package>/foundation/` only for a real project-local base category or a
   stateful framework base that must not be shared globally, such as a
   SQLAlchemy declarative base.
15. Add tests only where there is real code to test. Do not create empty folders
   just to satisfy the diagram.
16. Use `specx project component list --output-format json` and
   `specx project use-case list --output-format json` to
   inspect the resulting structure. When a typed application-action scaffold is
   useful, preview it with
   `specx project use-case create <scope>/<action> --kind <command|query> --dry-run --output-format json`, then create it and
   replace its explicit `NotImplementedError` test with behavior tests.

## Non-Negotiable Boundaries

- Keep all source and test `__init__.py` files empty. Do not add empty local
  foundation, source, test, or helper packages.
- Every non-foundation source class inherits an explicit packaged or local
  scoped base and uses the suffix implied by that ancestry. Every source class,
  including local bases, has a scoped docstring with a real `Example:`.
- Keep core inner packages free of delivery, IOC, SQLAlchemy, Redis, HTTP
  clients, and framework imports. Put concrete IO adapters under
  `core/<scope>/infrastructure/<technology>/`.
- Capabilities are narrow `BaseCapability` collaborators; gateways are
  business-language `BaseGateway` ports; core services choose
  `BasePureService`, `BaseReadService`, or `BaseEffectService`.
- Same-file `BaseCommand` or `BaseQuery` inputs enter use cases, and result DTOs
  leave them. Persistence use cases inject a `UnitOfWorkManager`; services do
  not open or finish transactions.
- Keep one use case in each module so static management commands can address it
  as `<scope>/<module>` without importing project code.
- Prefer frozen, keyword-only, slotted dataclasses for core data and
  `BaseStrEnum` for reusable closed value sets. Keep Pydantic at delivery and
  settings edges.
- Keep infrastructure technical and schema evolution in Alembic. Never call
  `metadata.create_all` or `drop_all` in application or test code.
- Configure stdlib logging once before composing the FastAPI app. Use FastAPI
  lifespan for resource cleanup, then close the container; do not run schema
  changes or business workflows in lifespan.
- Business routes use full `/api/v1/...` paths. Keep `/healthz` independent of
  external systems; use `/readyz` and `core/health` for any required external
  dependency, with bounded checks and minimal responses.
- Mirror real source behavior with flat tests. Unit tests resolve targets from
  a native pytest `container` fixture; integration tests use the real internal
  graph and replace only external boundaries. Read the blueprint before adding
  shared doubles or support helpers.
- Keep root `AGENTS.md` commands aligned with the Makefile and include only
  guidance that matches files and features present in the project.
- This skill targets FastAPI and must enable the opt-in `fastapi` rule family
  in `[tool.specx]`. Framework-neutral specx rules remain the default for
  workers, CLIs, and other delivery technologies.

## References

- `references/blueprint.md` - target tree, starter files, and creation checklist.
