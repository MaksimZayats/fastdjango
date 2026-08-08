from __future__ import annotations

# Authored diagnostic prose is intentionally kept as one searchable sentence per field.
# ruff: noqa: E501
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BuiltinRuleGuidance:
    """Authored remediation and static detection scope for one built-in rule."""

    remediation: str
    detection_boundary: str


def _guidance(remediation: str, detection_boundary: str) -> BuiltinRuleGuidance:
    return BuiltinRuleGuidance(
        remediation=remediation,
        detection_boundary=detection_boundary,
    )


BUILTIN_RULE_GUIDANCE = {
    "core.inner-packages-no-outer-layers-or-io-libraries": _guidance(
        "Move framework and IO dependencies behind a core port and import that port from inner core.",
        "Scans imports in core entities, DTOs, exceptions, capabilities, services, and use cases; dynamic imports are not resolved.",
    ),
    "core.scope-infrastructure-does-not-import-delivery": _guidance(
        "Move delivery translation out of the scope adapter or introduce a core-facing contract.",
        "Scans static imports below core scope infrastructure packages.",
    ),
    "delivery.controllers-do-not-import-infrastructure": _guidance(
        "Inject a use case or delivery service instead of importing scope infrastructure from delivery.",
        "Scans delivery imports for scope infrastructure and common persistence implementation modules.",
    ),
    "core.no-scope-delivery-packages": _guidance(
        "Move the delivery package to the project's top-level delivery directory.",
        "Checks source package paths; it does not infer delivery responsibility from arbitrary names.",
    ),
    "foundation.imports-use-scoped-packages": _guidance(
        "Replace legacy specx.foundation imports with the matching scoped foundation package.",
        "Checks static import statements for the removed legacy namespace.",
    ),
    "use-cases.no-entity-imports-or-returns": _guidance(
        "Map entities to a DTO inside the use case and return the DTO contract.",
        "Inspects use-case imports and return annotations; runtime return values are not executed.",
    ),
    "use-cases.return-dtos": _guidance(
        "Declare and return a BaseDTO subclass from each concrete use-case method.",
        "Follows project inheritance and statically inspects use-case return annotations.",
    ),
    "dtos.result-dtos-live-under-dtos": _guidance(
        "Move the result DTO module under core/<scope>/dtos and update its imports.",
        "Checks project DTO class inheritance and source paths.",
    ),
    "use-cases.inputs-are-local-commands-or-queries": _guidance(
        "Define one same-file BaseCommand or BaseQuery and accept it as the only use-case input.",
        "Inspects concrete use-case signatures and same-module class definitions.",
    ),
    "use-cases.orchestrate-through-collaborators": _guidance(
        "Move behavior behind an injected collaborator, construct a project type, or approve an exact qualified function.",
        "Checks inherited project methods, merges reachable lexical aliases conservatively, and resolves constructors, typed collaborators, manager-owned UoWs, and callable type aliases.",
    ),
    "core.behavior-no-ambient-runtime-access": _guidance(
        "Inject a capability or gateway for time, randomness, IDs, environment, filesystem, process, or network access.",
        "Checks inherited project methods and recognizes documented standard-library/client effects, ambient values, reachable aliases, and typed pathlib values.",
    ),
    "core.contracts-use-immutable-dataclasses": _guidance(
        "Decorate the contract with @dataclass(frozen=True, kw_only=True, slots=True).",
        "Follows path-qualified project inheritance from command, query, DTO, and entity bases and checks literal decorator flags.",
    ),
    "core.no-runtime-configuration-or-pydantic": _guidance(
        "Move runtime settings and Pydantic models to an edge and pass typed values or collaborators into core.",
        "Scans every core module for runtime references to exact Pydantic/settings ancestry, including project wrappers, plus direct environment access.",
    ),
    "use-cases.commands-and-queries-live-local": _guidance(
        "Move the command or query class into the use-case module that consumes it.",
        "Compares use-case input annotations with classes declared in the same module.",
    ),
    "capabilities.placement-and-suffix": _guidance(
        "Move the capability under core/<scope>/capabilities and use its required capability-family suffix.",
        "Follows project capability inheritance and checks source paths and class names.",
    ),
    "capabilities.no-workflows-or-port-roles": _guidance(
        "Model workflows as use cases and external or persistence boundaries as gateways or repositories.",
        "Checks capability names and public methods for documented workflow and port-role markers.",
    ),
    "gateways.ports-and-implementations-placement": _guidance(
        "Keep the gateway port under core/<scope>/gateways and its implementation under scope infrastructure.",
        "Uses gateway inheritance, abstract markers, and project paths to distinguish ports from implementations.",
    ),
    "gateways.external-effects-and-no-entity-returns": _guidance(
        "Document the external effect in the gateway docstring and return a DTO or value contract instead of an entity.",
        "Inspects gateway docstrings and method return annotations.",
    ),
    "use-cases.queries-do-not-mutate": _guidance(
        "Remove repository mutation from the query or model the operation as a command use case.",
        "Recognizes repository mutator call names in query use-case methods through static attribute chains.",
    ),
    "classes.require-explicit-bases": _guidance(
        "Inherit a packaged scoped foundation base or a justified project-local foundation extension.",
        "Checks non-foundation project class definitions for explicit bases.",
    ),
    "classes.require-example-docstrings": _guidance(
        "Add a scoped class docstring with a concrete Example: section that contains real code or usage.",
        "Checks project class docstrings syntactically; it does not evaluate example code.",
    ),
    "services.require-service-suffix": _guidance(
        "Rename the class with a Service suffix or move it out of the services package.",
        "Checks class names in core service package paths.",
    ),
    "services.require-effect-specific-bases": _guidance(
        "Choose BasePureService, BaseReadService, or BaseEffectService to state the service's effect category.",
        "Follows project service inheritance and checks concrete classes in service packages.",
    ),
    "services.no-generic-base-service": _guidance(
        "Replace BaseService with the pure, read, or effect service base matching the behavior.",
        "Checks class base expressions and imports for the generic BaseService name.",
    ),
    "services.methods-use-keyword-only-arguments": _guidance(
        "Insert * after self or cls so every public service input is keyword-only.",
        "Follows effective project service inheritance and rejects positional parameters and variadic positional arguments after self or cls.",
    ),
    "services.pure-no-io-or-runtime-state": _guidance(
        "Move IO or runtime-state behavior to an effect boundary and keep the pure service deterministic.",
        "Checks pure-service imports, injected fields, and known runtime or IO dependencies.",
    ),
    "services.read-no-writes-or-transactions": _guidance(
        "Remove writes and transaction ownership from the read service; let a use case own the UoW.",
        "Checks read-service dependencies, context managers, and known mutation call names.",
    ),
    "services.effect-no-owned-transactions-or-delivery": _guidance(
        "Pass an active use-case-owned UoW when needed and keep delivery types outside the effect service.",
        "Checks effect-service imports, injected dependencies, and UoW scope-opening syntax.",
    ),
    "classes.suffix-from-foundation-category": _guidance(
        "Rename the class to use the suffix implied by its nearest foundation category.",
        "Follows project inheritance and compares class names with known foundation suffix mappings.",
    ),
    "classes.no-raw-common-bases": _guidance(
        "Wrap the raw framework base in a justified local foundation class, then inherit that project base.",
        "Checks non-foundation class bases for known raw framework and common base classes.",
    ),
    "diwire.container-import-boundary": _guidance(
        "Move container access to IOC, an allowed delivery entrypoint or lifecycle, or tests.",
        "Scans static Container imports, annotations, and construction in project source paths.",
    ),
    "diwire.no-function-injection": _guidance(
        "Use Injected fields on classes; tests should accept ordinary fixtures and resolve the target from container.",
        "Resolves definition-time DIWire decorator aliases, Injected aliases, and Annotated injection markers on functions and methods.",
    ),
    "logging.no-injected-loggers": _guidance(
        "Create a private class logger from the full module and class name instead of injecting or registering Logger.",
        "Checks injected field annotations and IOC registrations for logging.Logger aliases.",
    ),
    "delivery.routes-use-full-api-v1-paths": _guidance(
        "Register the full /api/v1/... business route path at the controller boundary.",
        "Inspects literal route decorator and registration paths; documented health endpoints are exempt.",
    ),
    "sqlalchemy.no-schema-bootstrap-calls": _guidance(
        "Remove create_all or drop_all and manage schema changes through Alembic migrations.",
        "Scans source and tests for static SQLAlchemy metadata bootstrap call chains.",
    ),
    "sqlalchemy.models-live-under-scope-infrastructure": _guidance(
        "Move each concrete model under core/<scope>/infrastructure/<technology>; keep only an abstract/base model in foundation.",
        "Follows exact BaseSQLAlchemyModel ancestry; explicit table mappings remain concrete even when a foundation-path class starts with Base.",
    ),
    "sqlalchemy.models-require-alembic": _guidance(
        "Add meaningful Alembic config, env and revision files, migration commands, and an upgrade-and-drift integration test.",
        "Validates Alembic-qualified executable calls, invoked migration entrypoints, operational revisions, same-test upgrade/drift evidence, and parsed Make recipes.",
    ),
    "delivery.foundation-classes-live-under-delivery": _guidance(
        "Move every controller, delivery service, schema, or lifecycle under top-level delivery/.",
        "Follows path-qualified delivery foundation inheritance for concrete and abstract project classes.",
    ),
    "agents-md.documents-project-commands": _guidance(
        "Document the real source path and executable project commands, including JSON architecture diagnostics.",
        "Checks AGENTS.md fragments against the existing source directory and actual Makefile targets.",
    ),
    "fastapi.agents-md-documents-entrypoint": _guidance(
        "Document the exact package.delivery.fastapi.__main__:app entrypoint and ensure that module exposes app.",
        "Runs only for selected FastAPI projects and statically checks the entrypoint module and AGENTS.md.",
    ),
    "tests.mirror-source-structure": _guidance(
        "Move the test to the mirrored unit or integration module path and keep a flat test_<module>.py layout.",
        "Maps known project source categories to test paths and checks discovered Python test files.",
    ),
    "tests.core-behavior-resolves-from-container": _guidance(
        "Use the native tests/unit/conftest.py container fixture and resolve every exact concrete behavior class in the mirrored test body.",
        "Requires a directly returned native container, rejects nearer fixtures/reassignment/dead code, requires awaited aresolve, skips inherited abstract classes, and matches exact targets.",
    ),
    "tests.fixtures-do-not-bundle-mocks": _guidance(
        "Keep one-off mocks in the test and replace grouped mock fixtures with focused fixtures or mirrored fakes.",
        "Inspects pytest fixture bodies and return values for bundled mock objects.",
    ),
    "tests.integration-does-not-mock-internal-collaborators": _guidance(
        "Resolve the real internal graph in integration tests and replace only external IO boundaries.",
        "Scans integration-test patch and mock targets for project-internal use cases and services.",
    ),
    "uow.services-do-not-open-scopes": _guidance(
        "Move UoW manager scope ownership to the use case and pass the active UoW into the service when needed.",
        "Inspects service injected fields and with/async-with context expressions.",
    ),
    "uow.use-cases-open-at-most-one-scope": _guidance(
        "Open one manager-owned UoW scope per execution and coordinate all persistence through it.",
        "Counts statically recognized manager-owned context scopes in each use-case method.",
    ),
    "uow.use-cases-inject-managers": _guidance(
        "Inject a UnitOfWorkManager instead of an active UoW or callable provider.",
        "Checks use-case Injected field annotations and project UoW inheritance.",
    ),
    "uow.use-cases-no-direct-repositories-or-infrastructure": _guidance(
        "Reach repositories through the manager-owned active UoW and remove direct infrastructure dependencies.",
        "Checks use-case imports, injected fields, and repository call roots through static data flow.",
    ),
    "uow.ioc-does-not-register-active-uow": _guidance(
        "Register the UoW manager or factory in IOC, not an active UnitOfWork instance.",
        "Inspects IOC container registration calls and registered dependency annotations.",
    ),
    "packages.init-files-are-empty": _guidance(
        "Move declarations and re-exports out of __init__.py and leave the package marker empty.",
        "Checks every project __init__.py for executable statements, imports, and declarations.",
    ),
    "use-cases.one-per-module": _guidance(
        "Split the module so each managed file defines one concrete use case with one stable ID.",
        "Counts concrete use-case classes per source module through project inheritance.",
    ),
}
