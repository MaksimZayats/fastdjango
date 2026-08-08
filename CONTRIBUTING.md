# Contributing

specx is a typed Python guardrail package with one optional navigation skill.
Executable checks and public rule pages own architecture policy; the skill only
helps an agent find those interfaces.

## Repository Layout

```text
skills/specx/                   # optional navigation skill
.agents/skills/                 # tracked local-discovery mirror
src/specx/                      # reusable architecture guardrail package
tests/                          # package and skill-helper tests
scripts/validate_skills.py      # skill metadata validator
docs/rules/                     # authoritative built-in rule pages
AGENTS.md                       # instructions for agents editing this repo
README.md                       # user-facing catalog overview
```

## Prerequisites

- Node.js with `npx`, for `skills add`.
- `uv`, for Python validation commands.
- Python available through `uv`.

## Root Commands

Validate the Python package, optional skill, and installable skill list:

```sh
make check
```

Run package checks individually:

```sh
make lint
make type
make test
make build
```

Validate skill metadata only:

```sh
make validate-skills
```

Synchronize the tracked local-discovery mirror after editing canonical skills:

```sh
make sync-skills
```

List local skills:

```sh
make list-skills
```

## Skill Authoring

The single optional skill has:

- `SKILL.md` with YAML frontmatter containing only `name` and `description`.
- Optional `agents/openai.yaml` metadata when the skill is meant to surface in
  skill UI lists.

Keep `SKILL.md` concise and navigation-oriented. Put reusable patterns,
examples, rationale, and static-analysis limits in public documentation rather
than skill references. Edit only canonical `skills/specx/`, then run
`make sync-skills`; `make validate-skills` rejects mirror drift.

When changing a rule:

1. Update the package rule and focused positive, negative, aliasing, inheritance,
   and false-positive tests.
2. Update the authoritative page under `docs/rules/`, including remediation and
   static detection limits.
3. Update generated project guidance only when project commands or entrypoints change.
4. Run root `make check` and forward-test substantial generation changes in a
   disposable project when practical.

## Architecture Contract

Generated services should preserve these boundaries:

- Scoped specx foundation packages define the default reusable base classes for
  generated services: `specx.core.foundation`, `specx.delivery.foundation`,
  and `specx.infrastructure.foundation`.
- `foundation/`, when present in a generated service, contains only
  project-local base classes missing from the scoped foundation packages.
- `core/<scope>/` contains framework-free application behavior.
- `delivery/` contains framework adapters, controllers, schemas, app lifecycle
  managers, and delivery-only helpers.
- `core/<scope>/infrastructure/` contains scope-owned technical adapters.
- top-level `infrastructure/` contains app-wide technical resources, including
  process-wide logging configuration.
- `ioc/` owns `diwire.Container` composition.
- FastAPI lifecycle code closes app-owned infrastructure resources and is the
  only generated class allowed to inject `diwire.Container`.
- `shared/` is optional and only for stable cross-scope primitives.

Project-local foundation module filenames are intentionally unprefixed:

```text
foundation/clock.py
foundation/generator.py
```

Foundation class names stay prefixed:

```python
class BaseClock: ...
class BaseGenerator: ...
```

## Use Cases, Services, And UoW

Use cases are externally meaningful actions. Each `execute(...)` method accepts
exactly one same-file input:

- `Command` for side-effecting operations.
- `Query` for read-only operations.

Use cases return DTOs, not entities or raw repository results.
Commands, queries, DTOs, entities, and other core data classes should use
`@dataclass(frozen=True, kw_only=True, slots=True)` unless a user explicitly
asks for another model type. Keep Pydantic at delivery schemas and settings
edges.

Persistence use cases inject a `UnitOfWorkManager` and open the active
`UnitOfWork` inside `execute(...)`. Services may accept that active UoW as a
method argument, but services must not open UoW scopes or own commit/rollback.

Core services use one of:

- `BasePureService` for deterministic helpers with no IO or runtime state.
- `BaseReadService` for read-only orchestration.
- `BaseEffectService` for side-effecting helpers that operate inside a use-case
  owned UoW or call effect gateways.

Do not add a generic `BaseService`.

## Repositories, Gateways, And Capabilities

Use repositories for owned persistence. Repositories may return entities inside
core boundaries.

Use top-level logging configurators for runtime logging setup. Do not inject
`logging.Logger` or register loggers in the container; classes that actually
log create private stdlib class loggers.

Use gateways for outbound business capabilities provided by external systems:
OpenAI, payments, email, queues, external HTTP APIs, and similar dependencies.
Gateway ports inherit `BaseGateway`, live under `core/<scope>/gateways/`,
declare external effects in docstrings, and do not return entities.

Use capabilities for small injectable collaborators that are narrower than
services. Direct subclasses of `BaseCapability` end with `Capability`. If a
capability family becomes common or needs stronger checks, introduce a narrower
project-local foundation base such as `BaseClock` or `BaseGenerator`.

## Architecture Guardrails

Rule-based guardrails live in the `specx` Python package. Each built-in
architecture check is a concrete `*Rule` subclass with a stable
`SpecxRuleId` and a useful docstring explaining the rule.

Generated projects run `specx check`, normally through `make lint` and
`make check`. Agents should prefer `specx check --output-format json`, follow
each diagnostic's hint and documentation URL, and use the public Python API only
for project-specific custom rules. When changing built-in guardrail behavior,
update the package rule, focused tests, rule metadata, and its public rule page.

## Migrations

SQLAlchemy projects use Alembic migrations. Do not introduce source or test
code that calls `metadata.create_all()` or `drop_all()`.

Model discovery should load every SQLAlchemy model under
`core/*/infrastructure/sqlalchemy/models` so Alembic drift checks compare
against complete metadata.

## Pull Request Checklist

- Root `make check` passes.
- Substantial generated-project changes were forward-tested when practical.
- Public rule pages and package guardrails agree on architecture rules.
- Skill discovery finds exactly the one optional `specx` navigation skill.
- No placeholder folders, local copies of packaged bases, or speculative
  foundation bases were added.
- No unrelated generated caches or local environment files were committed.
