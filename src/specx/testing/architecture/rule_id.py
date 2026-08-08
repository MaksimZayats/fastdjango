from __future__ import annotations

from enum import StrEnum


class SpecxRuleId(StrEnum):
    """Stable identifiers for built-in specx architecture rules."""

    CORE_INNER_PACKAGES_DO_NOT_IMPORT_OUTER_LAYERS_OR_IO_LIBRARIES = (
        "core.inner-packages-no-outer-layers-or-io-libraries"
    )
    SCOPE_INFRASTRUCTURE_DOES_NOT_IMPORT_DELIVERY = (
        "core.scope-infrastructure-does-not-import-delivery"
    )
    DELIVERY_CONTROLLERS_DO_NOT_IMPORT_INFRASTRUCTURE = (
        "delivery.controllers-do-not-import-infrastructure"
    )
    CORE_DOES_NOT_CONTAIN_DELIVERY_PACKAGES = "core.no-scope-delivery-packages"
    FOUNDATION_IMPORTS_USE_SCOPED_PACKAGES = "foundation.imports-use-scoped-packages"
    USE_CASES_DO_NOT_IMPORT_OR_RETURN_ENTITIES = "use-cases.no-entity-imports-or-returns"
    USE_CASES_RETURN_DTOS = "use-cases.return-dtos"
    RESULT_DTO_CLASSES_LIVE_UNDER_SCOPE_DTOS_PACKAGE = "dtos.result-dtos-live-under-dtos"
    USE_CASE_INPUTS_ARE_LOCAL_COMMANDS_OR_QUERIES = "use-cases.inputs-are-local-commands-or-queries"
    USE_CASE_MODULES_DEFINE_ONE_USE_CASE = "use-cases.one-per-module"
    USE_CASES_ORCHESTRATE_THROUGH_COLLABORATORS = "use-cases.orchestrate-through-collaborators"
    CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS = "core.behavior-no-ambient-runtime-access"
    CORE_CONTRACTS_USE_IMMUTABLE_DATACLASSES = "core.contracts-use-immutable-dataclasses"
    CORE_NO_RUNTIME_CONFIGURATION_OR_PYDANTIC = "core.no-runtime-configuration-or-pydantic"
    COMMAND_AND_QUERY_CLASSES_LIVE_WITH_USE_CASES = "use-cases.commands-and-queries-live-local"
    CAPABILITIES_LIVE_IN_EXPECTED_PACKAGES_AND_USE_EXPECTED_SUFFIXES = (
        "capabilities.placement-and-suffix"
    )
    CAPABILITIES_DO_NOT_OWN_WORKFLOWS_OR_OTHER_PORT_ROLES = (
        "capabilities.no-workflows-or-port-roles"
    )
    GATEWAY_PORTS_AND_IMPLEMENTATIONS_LIVE_IN_EXPECTED_PACKAGES = (
        "gateways.ports-and-implementations-placement"
    )
    GATEWAYS_DECLARE_EXTERNAL_EFFECTS_AND_DO_NOT_RETURN_ENTITIES = (
        "gateways.external-effects-and-no-entity-returns"
    )
    QUERY_USE_CASES_DO_NOT_CALL_REPOSITORY_MUTATORS = "use-cases.queries-do-not-mutate"
    NON_FOUNDATION_SOURCE_CLASSES_HAVE_EXPLICIT_BASE_CLASSES = "classes.require-explicit-bases"
    CLASSES_REQUIRE_EXAMPLE_DOCSTRINGS = "classes.require-example-docstrings"
    SERVICE_CLASSES_USE_SERVICE_SUFFIX = "services.require-service-suffix"
    CORE_SERVICES_USE_EFFECT_SPECIFIC_SERVICE_BASES = "services.require-effect-specific-bases"
    GENERIC_BASE_SERVICE_IS_NOT_USED = "services.no-generic-base-service"
    SERVICE_METHODS_USE_KEYWORD_ONLY_ARGUMENTS = "services.methods-use-keyword-only-arguments"
    PURE_SERVICES_DO_NOT_DEPEND_ON_IO_OR_RUNTIME_STATE = "services.pure-no-io-or-runtime-state"
    READ_SERVICES_DO_NOT_PERFORM_WRITES_OR_OWN_TRANSACTIONS = (
        "services.read-no-writes-or-transactions"
    )
    EFFECT_SERVICES_DO_NOT_OWN_TRANSACTIONS_OR_IMPORT_DELIVERY = (
        "services.effect-no-owned-transactions-or-delivery"
    )
    CLASSES_USE_SUFFIX_FROM_MOST_SPECIFIC_FOUNDATION_CATEGORY = (
        "classes.suffix-from-foundation-category"
    )
    NON_FOUNDATION_CLASSES_DO_NOT_USE_RAW_COMMON_BASES = "classes.no-raw-common-bases"
    ONLY_IOC_DELIVERY_APP_AND_TESTS_IMPORT_CONTAINER = "diwire.container-import-boundary"
    DIWIRE_NO_FUNCTION_INJECTION = "diwire.no-function-injection"
    LOGGING_DOES_NOT_INJECT_LOGGERS = "logging.no-injected-loggers"
    PUBLIC_ROUTES_USE_FULL_API_V1_PATHS = "delivery.routes-use-full-api-v1-paths"
    NO_SCHEMA_BOOTSTRAP_CALLS_IN_SOURCE_OR_TESTS = "sqlalchemy.no-schema-bootstrap-calls"
    ROOT_AGENTS_MD_DOCUMENTS_PROJECT_COMMANDS = "agents-md.documents-project-commands"
    FASTAPI_ROOT_AGENTS_MD_DOCUMENTS_ENTRYPOINT = "fastapi.agents-md-documents-entrypoint"
    DELIVERY_FOUNDATION_CLASSES_LIVE_UNDER_DELIVERY = (
        "delivery.foundation-classes-live-under-delivery"
    )
    TESTS_MIRROR_SOURCE_STRUCTURE = "tests.mirror-source-structure"
    TESTS_CORE_BEHAVIOR_RESOLVES_FROM_CONTAINER = "tests.core-behavior-resolves-from-container"
    TEST_FIXTURES_DO_NOT_BUNDLE_MOCKS = "tests.fixtures-do-not-bundle-mocks"
    INTEGRATION_TESTS_DO_NOT_MOCK_INTERNAL_COLLABORATORS = (
        "tests.integration-does-not-mock-internal-collaborators"
    )
    SERVICES_DO_NOT_OPEN_UNIT_OF_WORK_SCOPES = "uow.services-do-not-open-scopes"
    USE_CASES_OPEN_AT_MOST_ONE_UNIT_OF_WORK_SCOPE = "uow.use-cases-open-at-most-one-scope"
    USE_CASES_INJECT_UNIT_OF_WORK_MANAGERS = "uow.use-cases-inject-managers"
    USE_CASES_DO_NOT_INJECT_REPOSITORIES_OR_INFRASTRUCTURE = (
        "uow.use-cases-no-direct-repositories-or-infrastructure"
    )
    IOC_CONTAINER_DOES_NOT_REGISTER_ACTIVE_UNIT_OF_WORK = "uow.ioc-does-not-register-active-uow"
    SQLALCHEMY_MODELS_LIVE_UNDER_SCOPE_INFRASTRUCTURE = (
        "sqlalchemy.models-live-under-scope-infrastructure"
    )
    SQLALCHEMY_MODELS_REQUIRE_ALEMBIC = "sqlalchemy.models-require-alembic"
    INIT_FILES_ARE_EMPTY = "packages.init-files-are-empty"
