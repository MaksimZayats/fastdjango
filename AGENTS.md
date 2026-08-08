# Agent Instructions

## Repository Purpose

This repo is the specx skill catalog and Python guardrail package. It publishes
reusable agent skills and a typed `specx` package for creating Python backend
services with packaged scoped foundation bases, rule-based architecture tests,
and clean `core` / `delivery` / `infrastructure` / `ioc` boundaries.

## Repo Map

- `skills/<skill-name>/SKILL.md` defines the skill trigger and workflow.
- `skills/<skill-name>/references/*.md` contains detailed implementation
  patterns and examples.
- `skills/<skill-name>/agents/openai.yaml` contains OpenAI skill UI metadata.
- `.agents/skills/` is the tracked local-discovery mirror of canonical
  `skills/`; update it with `make sync-skills` rather than editing it directly.
- `docs/` is the self-contained Storybook documentation package; its MDX pages
  live under `docs/pages/`.
- `src/specx/core/foundation/` contains reusable core foundation bases.
- `src/specx/delivery/foundation/` contains delivery foundation bases.
- `src/specx/infrastructure/foundation/` contains infrastructure foundation bases.
- `src/specx/testing/` contains the public rule-based architecture test API.
- `src/specx/_internal/` contains package internals that are not public API.
- `src/specx/_internal/project_management/` implements static discovery,
  deterministic scaffolding, runtime execution, and terminal presentation.
- `tests/` validates the `specx` package and skill helper scripts.
- `scripts/validate_skills.py` validates the skill catalog.

## Root Commands

- Validate everything in the catalog and package: `make check`
- Format package code: `make format`
- Lint and format-check package code: `make lint`
- Type-check package code: `make type`
- Run package tests: `make test`
- Build package distributions: `make build`
- Install the Storybook documentation dependencies: `npm --prefix docs ci`
- Run the Storybook documentation locally: `make docs`
- Build the static Storybook documentation: `make docs-build`
- Verify installed package typing: `make verifytypes`
- Validate skill metadata only: `make validate-skills`
- Synchronize the local skill mirror: `make sync-skills`
- List local installable skills: `make list-skills`
- Inspect local skills manually: `npx skills add . --list --full-depth`
- Inspect project components: `uv run specx project component list`
- Inspect project use cases: `uv run specx project use-case list`
- Prefer `--output-format json` for agent inspection and scaffold dry runs; use
  `specx project --error-format json ...` when failures must also be parsed.
- Run `uv run specx project use-case show COMPONENT/NAME --output-format json` before constructing
  runner input; unknown keys are rejected.
- Install from GitHub: `npx skills add maksimzayats/specx --skill '*' --agent codex -y`

## Skill Authoring Rules

- Keep skill directories lowercase kebab-case.
- Each skill needs `SKILL.md` with YAML frontmatter containing only `name` and
  `description`.
- `name` must match the directory name.
- `description` must be trigger-oriented, non-empty, and avoid angle brackets.
- Do not leave `TODO` placeholders.
- Keep `SKILL.md` concise; put detailed patterns in `references/*.md`.
- Keep `SKILL.md` at or below 500 lines and add a linked `## Contents` section
  to Markdown references over 100 lines.
- Edit canonical `skills/`, run `make sync-skills`, and let validation reject
  drift in the tracked `.agents/skills/` mirror.
- If `agents/openai.yaml` exists, `default_prompt` must mention
  `$<skill-name>` and `short_description` must be 25-64 characters.
- When changing generated-project commands or architecture, update the relevant
  skill references and the generated-project `AGENTS.md` guidance together.

## specx Service Rules To Preserve

- Every project class inherits an explicit packaged scoped foundation base or a
  justified project-local foundation extension.
- Use cases accept exactly one same-file `Command` or `Query` and return DTOs.
- Keep one use case per module so management IDs remain `<component>/<module>`.
- Commands, queries, DTOs, entities, and other core data classes use
  `@dataclass(frozen=True, kw_only=True, slots=True)` unless the user asks for
  another model type. Keep Pydantic at delivery schemas and settings edges.
- Small injectable collaborators inherit `BaseCapability`, live under
  `core/<scope>/capabilities/`, and do not pretend to be services,
  repositories, gateways, helpers, managers, or generic dependencies.
- Direct concrete subclasses of `BaseCapability` end with `Capability`; narrower
  foundation families such as `BaseClock` or `BaseGenerator` use their narrower
  suffix.
- Gateway ports inherit `BaseGateway`, live under `core/<scope>/gateways/`,
  declare external effects, use business language, and do not return entities.
- Concrete gateway implementations live under
  `core/<scope>/infrastructure/<tech>/`.
- Core services inherit `BasePureService`, `BaseReadService`, or
  `BaseEffectService`, keep the `Service` suffix, and do not open unit-of-work
  scopes.
- Do not copy packaged foundation bases into generated projects or create an
  empty local `foundation/` package. Use `specx.core.foundation`,
  `specx.delivery.foundation`, and `specx.infrastructure.foundation` as the
  scoped default boundaries. Add
  `src/<package>/foundation/` only for a real project-local base category or a
  stateful framework base that must not be shared globally, such as the project
  SQLAlchemy declarative base.
- Do not add `base_` prefixes to project-local foundation module filenames;
  class names stay prefixed, for example `clock.py` defines `BaseClock`.
- Persistence use cases inject a `UnitOfWorkManager`, not repositories, active
  UoWs, providers, SQLAlchemy sessions/engines/session factories, or concrete
  infrastructure adapters.
- Delivery schemas live under the delivery layer, usually
  `delivery/<framework>/schemas/`; use-case DTOs live in `core/<scope>/dtos/`.
- SQLAlchemy projects use Alembic migrations, not `metadata.create_all`.
- Runtime logging is configured once in top-level
  `infrastructure/logging/LoggingConfigurator` with Python stdlib logging.
- FastAPI app lifespan lives in `delivery/fastapi/lifecycle.py`, inherits
  `BaseLifecycle[FastAPI]`, closes app-owned infrastructure resources, and then
  calls `container.aclose()` on shutdown.
- Do not inject loggers or register `logging.Logger` in the DI container.
  Classes that actually log create a private class logger in `__post_init__`
  using the full module plus class name, and must not log secrets, tokens, full
  external URLs, credentials, request bodies, or infrastructure topology.
- `diwire.Container` belongs in `ioc`, top-level delivery
  `__main__.py`/factory/lifecycle modules, and tests only. `Injected[Container]`
  is allowed only in `FastAPILifecycle`.
- Core service/use-case/capability tests mirror source module paths with flat
  `test_<module>.py` files. Do not create per-target test folders.
- Unit tests receive the native pytest `container` fixture, register local
  doubles or inline mocks before resolution, and resolve project classes with
  `container.resolve(Target)`.
- One-off class-based test doubles live in the `test_*.py` module that uses
  them. Reused unit-test doubles live in mirrored
  `tests/unit/core/<scope>/{capabilities,gateways,repositories}/fake_<source_module>.py`
  modules.
- Inline `MagicMock` or `AsyncMock` in the test function for one-off behavior.
- Do not create `harness.py`, target factories, target harnesses,
  `tests/_support/fakes`, `tests/**/_fakes.py`, fake modules outside those
  mirrored unit port/capability packages, generic `_scenarios.py`, or double
  classes in `conftest.py`.

## Working Rules For Agents

- For catalog changes, run root `make check`.
- Do not add empty future-facing folders or placeholder skills.
- Do not duplicate full reference docs in this file; keep stable repo rules here
  and detailed generation rules inside `skills/*/references/`.
