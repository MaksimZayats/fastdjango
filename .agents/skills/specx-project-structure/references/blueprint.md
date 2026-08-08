# specx Project Blueprint

Use this reference to create a new FastAPI backend repo from scratch. Packaged
framework-neutral guardrails run by default; this blueprint additionally
enables the opt-in `fastapi` rule family. Use `$specx-component-architecture`
for workers, CLIs, or other delivery frameworks.

For a completely new repository, `specx init <path>` creates the canonical
framework-neutral baseline first. It contains project metadata, strict tooling,
root `AGENTS.md`, a small `core/health` service and use case,
`ioc/container.py`, and mirrored unit tests. It does not create delivery,
infrastructure, or foundation packages.

## Contents

- [Target Package Shape](#target-package-shape)
- [Root AGENTS.md](#root-agentsmd)
- [SQLAlchemy And Alembic Additions](#sqlalchemy-and-alembic-additions)
- [Operational Probe Additions](#operational-probe-additions)
- [First Runnable Slice](#first-runnable-slice)

## Target Package Shape

The neutral initializer can be run directly:

```bash
specx init order-service
cd order-service
make check
```

It runs `uv add specx diwire` and `uv add --dev mypy pytest ruff` by default so uv
records every selected dependency release, creates the lockfile, and
synchronizes the environment. Use `--no-sync` only when the caller needs an
offline or render-only workflow, then run both commands before the generated
locked commands.

Inspect the initialized project through the structural management interface:

```bash
specx project component list --output-format json
specx project use-case show health/check-health --output-format json
specx project use-case run health/check-health
```

New actions can start from a deterministic typed scaffold. Preview the complete file manifest first:

```bash
specx project use-case create orders/create-order \
  --kind command \
  --input-field customer_id:str \
  --result-field order_id:int \
  --dry-run \
  --output-format json
```

The generator creates one use case per module, a result DTO, and a temporary
green test for the explicit `NotImplementedError`. Replace that stub and test
with real behavior before treating the action as complete.

Preserve an existing import package. For a new project named `order-service`,
`order_service` is a suitable import package; normalize punctuation and spaces,
then verify that the result satisfies `str.isidentifier()` and is not a Python
keyword. Choose an explicit valid name if normalization leaves a keyword or
leading digit. Do not assume the distribution name and import package must
match.

The neutral initializer renders this complete starter slice:

```text
src/order_service/
  core/health/
    dtos/health_status_dto.py
    enums/health_status_enum.py
    services/health_status_service.py
    use_cases/check_health.py
  ioc/container.py
tests/
  unit/
    conftest.py
    core/health/
      services/test_health_status_service.py
      use_cases/test_check_health.py
```

Every shown Python directory also gets an empty `__init__.py`. The health slice
is deliberately pure and framework-neutral; it demonstrates service/use-case
composition without creating a delivery or infrastructure layer.

If no business slice was requested, the smallest FastAPI baseline contains only
files with current behavior:

```text
AGENTS.md
src/order_service/
  __init__.py
  delivery/
    fastapi/
      __main__.py
      factory.py
      lifecycle.py
      controllers/liveness.py
      schemas/liveness_schema.py
  infrastructure/
    logging/
      configurator.py
      settings.py
  ioc/
    container.py
tests/
  __init__.py
  integration/
    delivery/fastapi/controllers/test_liveness.py
```

Every shown Python directory also gets an empty `__init__.py`; the diagram
omits nested initializers for readability. Do not add empty controllers,
schemas, suites, or helper directories simply because the diagram names a
category.

Add the first user-requested core scope as a real vertical slice. A typical
scope adds only the inner packages used by that feature, plus mirrored tests:

```text
src/order_service/core/<scope>/
  dtos/<result>_dto.py
  services/<behavior>_service.py       # only when reusable behavior exists
  use_cases/<action>.py
tests/unit/core/<scope>/
  services/test_<behavior>_service.py  # only when the source service exists
  use_cases/test_<action>.py
```

Import default bases from the matching scoped specx foundation package. Do not
create an empty local `foundation/` package. Create
`src/<package>/foundation/` only when current code needs a real project-local
base category or a stateful framework base that must not be shared globally,
such as a SQLAlchemy declarative base.

Add `tests/_support/` only when tests need generic clients, DB helpers, or
shared integration resources. One-off project-specific test doubles stay in the
`test_*.py` file that uses them. Reused unit-test doubles live in mirrored
`tests/unit/core/<scope>/{capabilities,gateways,repositories}/fake_<source_module>.py`
modules. Add `tests/integration/core/...` for use cases that inject a UoW
manager so persistence-facing behavior is proven against the real
transactional database.

Every created test directory gets an empty `__init__.py`; do not add test
package re-exports or setup behavior there. Add `tests/unit/conftest.py` or
`tests/integration/conftest.py` only when that suite has a real fixture.

When stable cross-scope application primitives exist, add `shared/`. When
SQLAlchemy exists, add `foundation/sqlalchemy_model.py`, top-level
`infrastructure/sqlalchemy/`, `alembic.ini`, and `migrations/` with
`$specx-sqlalchemy-migrations`; none belongs in the unconditional baseline.

## Root AGENTS.md

Create root `AGENTS.md` for every generated repo. Keep it concise, practical,
and aligned with the actual Makefile targets. Include only commands that exist
for that project.

Recommended content follows. It is a superset: remove commands, fixture notes,
and whole feature rules that do not match files in the generated project. Keep
the canonical wording for each applicable boundary rule because the packaged
guardrail verifies those explicit project-contract phrases while detecting
whether the corresponding class category exists.

```markdown
# Agent Instructions

## Project Shape

- Package lives under `src/order_service`.
- FastAPI entrypoint: `order_service.delivery.fastapi.__main__:app`.
- Core behavior lives in `src/order_service/core/<scope>/`.
- Delivery lives in `src/order_service/delivery`.
- Shared technical infrastructure lives in `src/order_service/infrastructure`.
- Runtime logging is configured by
  `src/order_service/infrastructure/logging/configurator.py`.
- FastAPI lifespan is owned by
  `src/order_service/delivery/fastapi/lifecycle.py`.
- Scope-owned adapters live under `core/<scope>/infrastructure`.
- DI composition lives in `src/order_service/ioc/container.py`.
- Foundation bases come from `specx.core.foundation`,
  `specx.delivery.foundation`, or `specx.infrastructure.foundation`.
- Add `src/order_service/foundation/` only for project-local base categories or
  stateful framework bases that must not be shared globally, such as the
  project SQLAlchemy declarative base. Do not create an empty local
  `foundation/` package.

## Commands

- Install: `uv sync --locked --all-groups`
- Dev server: `make dev`
- Full check: `make check`
- Lint/type/format/architecture check: `make lint`
- Format/fix: `make format`
- Tests: `make test`
- Targeted unit tests: `uv run --locked pytest tests/unit`
- Targeted integration tests: `uv run --locked pytest tests/integration`

## Architecture Rules

- Business controllers call injected use cases and never import
  infrastructure. A delivery-only `/healthz` controller may return its tiny
  process-liveness response directly.
- Non-foundation source classes inherit explicit packaged or local scoped
  bases. Local foundation bases explicitly inherit the packaged or framework
  base they extend.
- Public business FastAPI routes use full `/api/v1/...` paths in controllers.
- Operational probes, when present, are the only unversioned route exception.
- Runtime logging is configured once by `LoggingConfigurator` in top-level
  `infrastructure/logging` using Python stdlib `logging.config.dictConfig`.
- The FastAPI runtime entrypoint resolves `LoggingConfigurator` and calls
  `configure()` before resolving `FastAPIFactory`.
- The FastAPI app factory injects `FastAPILifecycle` and passes it to
  `FastAPI(lifespan=...)`.
- `FastAPILifecycle` inherits `BaseLifecycle[FastAPI]`, closes app-owned
  resources such as SQLAlchemy session factories, then calls
  `container.aclose()` on shutdown.
- Do not run migrations, schema creation, or business workflows in FastAPI
  lifespan.
- Do not inject loggers, register `logging.Logger` in the DI container, or
  pass loggers through constructors. Classes that actually log create a private
  class logger in `__post_init__` with
  `logging.getLogger(f"{self.__class__.__module__}.{self.__class__.__qualname__}")`.
- Log important application events and failures, but never secrets, tokens,
  full external URLs, credentials, request bodies, or detailed infrastructure
  topology.
- Use cases expose exactly one `execute(*, command=...)` or
  `execute(*, query=...)`.
- Command/query classes live in the same use-case module and inherit
  `BaseCommand` or `BaseQuery`, not `BaseDTO`.
- Use cases return DTOs, not entities or raw repository results.
- DTOs live in `core/<scope>/dtos`.
- Capabilities live in `core/<scope>/capabilities`, subclass `BaseCapability`,
  do one narrow injectable thing, and do not act as services, repositories, or
  gateways.
- Gateway ports live in `core/<scope>/gateways`, subclass `BaseGateway`, use
  business language, declare external effects, and do not return entities.
- Concrete gateway implementations live under
  `core/<scope>/infrastructure/<tech>`.
- Core services inherit `BasePureService`, `BaseReadService`, or
  `BaseEffectService`, end with `Service`, and do not open UoW scopes.
- Query use cases must not call repository mutators.
- Use cases that touch persistence inject `UnitOfWorkManager`.
- They must not inject repositories, active UoWs, providers, or concrete
  infrastructure adapters.
- They must not inject SQLAlchemy sessions/engines/session factories.
- Only `ioc`, top-level delivery `__main__.py`/factory/lifecycle code, and
  tests may use `diwire.Container`. `Injected[Container]` is allowed only in
  `FastAPILifecycle` for shutdown cleanup.
- Every project source class needs a scoped docstring with a concrete
  `Example:` block. Non-foundation classes also need explicit packaged or local
  bases and matching suffixes.
- Prefer `@dataclass(frozen=True, kw_only=True, slots=True)` for commands,
  queries, DTOs, entities, and other core data classes unless the user asks for
  another model type.
- Use `BaseStrEnum` for limited known application value sets instead of plain
  `str` or `Literal[...]`.
- Keep all `__init__.py` files empty.

## Tests

- Tests mirror source module paths under `tests/unit` or `tests/integration`
  with flat `test_<module>.py` files.
- When needed, `tests/unit/conftest.py` owns the fresh real-app unit `container`
  fixture returned by `get_container()` and any project-wide test overrides.
- When persistence integration exists, `tests/integration/conftest.py` owns the
  transactional DB-backed integration `container` fixture.
- Private test helpers live under `tests/_support`; this is not a test suite.
- Run architecture policy with `make lint`. Add a wrapper under
  `tests/guardrails` only when programmatic custom rules are required.
- Every test directory has an empty `__init__.py`.
- Required generated tests are currently scoped to core services, use cases,
  and capabilities.
- Unit tests register local test doubles or inline mocks before resolving the
  target with `container.resolve(Target)`.
- One-off class-based doubles live in the `test_*.py` module that uses them.
- Reused unit-test doubles live in mirrored
  `tests/unit/core/<scope>/{capabilities,gateways,repositories}/fake_<source_module>.py`
  modules.
- Integration tests use the real internal app graph and override only external
  systems or the transactional test session factory.
- Core use-case integration tests live under `tests/integration/core/...` and
  call resolved use cases directly against the transactional DB.
- Delivery integration tests live under `tests/integration/delivery/...` and
  own HTTP route/status/schema/error mapping.
- Unit-test `LoggingConfigurator` by overriding `LoggingSettings`,
  monkeypatching `logging.config.dictConfig`, and asserting the generated
  readable stdlib config. Use `caplog` only when a log record is meaningful
  project behavior.
- Unit-test `FastAPILifecycle` by overriding closeable infrastructure resources
  and asserting shutdown order. FastAPI route integration helpers must run ASGI
  lifespan before opening `AsyncClient`.
- Do not create per-target test folders, `harness.py`, target factories,
  target harnesses, `tests/_support/fakes`, `tests/**/_fakes.py`, fake modules
  outside those mirrored unit port/capability packages, generic
  `_scenarios.py`, or double classes in `conftest.py`.
- Do not hand-build application graphs in tests.
- Before adding a test, sanity-check that it would fail for a plausible bug and
  that its assertion protects behavior, a boundary, or a contract.
- Do not add tests just to have mirrored files. Cover real project behavior,
  not upstream library behavior.
- Do not mock internal use cases, services, or capabilities in integration
  tests.
- Do not add tests that only assert `container.resolve(...)` returns an
  instance.
- FastAPI route tests compare response status codes with `fastapi.status`
  constants, not raw integer literals.
- Do not enable `diwire.integrations.pytest_plugin` or use `Injected[...]`
  parameters in tests; keep test injection explicit with native pytest
  fixtures.
```

Replace `order_service` with the real package name and entrypoint.

## SQLAlchemy And Alembic Additions

When SQLAlchemy/Alembic exists, add the migration shape, commands, and rules:

```markdown
## Project Shape

- Alembic migrations live in `migrations`.

## Commands

- Create migration: `make makemigrations message="describe change"`
- Apply migrations: `make migrate`
- Check migration drift: `make migration-check`

## Migrations

- Do not use `create_all()` or `drop_all()` in source or tests.
- Add new SQLAlchemy model modules to Alembic's model loader.
- Generate revisions with `make makemigrations`, review them, then run
  `make migration-check`.
```

The `%(constraint_name)s` naming convention used by the specx SQLAlchemy base
requires explicit names for `CheckConstraint` objects and schema types that
emit checks on the target database. Document and enforce that model rule, or
choose another reviewed convention before the first migration.

## Operational Probe Additions

Keep a simple `/healthz` liveness response in delivery. Add `core/health` and
`/readyz` when readiness checks any required external dependency or probe
policy is reused by multiple deliveries. If that condition is met, add only
the needed packages:

```text
src/order_service/core/health/
  dtos/health_probe_dto.py
  gateways/readiness_check_gateway.py
  services/readiness_probe_service.py
  use_cases/check_readiness.py
src/order_service/core/health/infrastructure/<technology>/
  readiness_check_gateway.py
tests/unit/core/health/
  services/test_readiness_probe_service.py
  use_cases/test_check_readiness.py
tests/integration/core/health/use_cases/
  test_check_readiness.py
tests/integration/delivery/fastapi/controllers/
  test_probes.py
```

Add these concise rules to the generated `AGENTS.md` only when the project has
the corresponding endpoints and core slice:

```markdown
## Operational Probes

- `/healthz` is a lightweight process-liveness endpoint and must not query
  databases, queues, caches, network services, or external SDKs.
- `/readyz` reports whether the instance can receive traffic and returns `503`
  when a required dependency is unavailable.
- Bound each readiness dependency call with a short application-side timeout;
  for SQLAlchemy use a cheap `SELECT 1` through a readiness gateway adapter.
- Required-dependency readiness and cross-delivery probe policy live under
  `core/health`; delivery owns route paths, status codes, headers, schemas, and
  OpenAPI inclusion.
- Probe responses are small, unauthenticated at the app layer, omit secrets,
  topology, and stack traces, and send `Cache-Control: no-store`.
- Probe integration tests cover liveness, readiness success and failure,
  `Cache-Control: no-store`, and exclusion from OpenAPI when intended.
```

## First Runnable Slice

Build the first user-requested business slice through core, delivery, IOC, and
tests. If no domain feature is specified, use the small delivery `/healthz`
endpoint shown in the baseline to prove that app composition and lifespan work;
do not manufacture a core health workflow for that simple response.

Create top-level `infrastructure/logging` as part of the first runnable slice.
Use `LoggingSettings(BaseRuntimeSettings)` with a `LogLevelEnum(BaseStrEnum)`,
and a `LoggingConfigurator(BaseConfigurator)` that calls
`logging.config.dictConfig` with `disable_existing_loggers=False`, a readable
console formatter, and root level/handler settings. Keep loggers local to
classes that emit logs; do not make loggers DI dependencies.

Create `delivery/fastapi/lifecycle.py` as part of the first runnable slice.
`FastAPILifecycle(BaseLifecycle[FastAPI])` owns app lifespan cleanup: close
long-lived infrastructure resources, then call `container.aclose()` in a
nested `finally`. Register the container instance in `ioc/container.py` for
this lifecycle dependency only.

Use `$specx-add-core-use-case`, `$specx-add-core-service`,
`$specx-add-delivery-controller`, `$specx-diwire-composition`, and
`$specx-tests` for the concrete implementation details.
