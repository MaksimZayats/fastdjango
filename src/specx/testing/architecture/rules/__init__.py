from __future__ import annotations

from ._shared import ArchitectureRuleBase
from .agents_md_documents_project_commands import (
    RootAgentsMDDocumentsProjectCommandsRule,
)
from .capabilities_no_workflows_or_port_roles import (
    CapabilitiesDoNotOwnWorkflowsOrOtherPortRolesRule,
)
from .capabilities_placement_and_suffix import (
    CapabilitiesLiveInExpectedPackagesAndUseExpectedSuffixesRule,
)
from .classes_no_raw_common_bases import (
    NonFoundationClassesDoNotUseRawCommonBasesRule,
)
from .classes_require_example_docstrings import (
    ClassesRequireExampleDocstringsRule,
)
from .classes_require_explicit_bases import (
    NonFoundationSourceClassesHaveExplicitBaseClassesRule,
)
from .classes_suffix_from_foundation_category import (
    ClassesUseSuffixFromMostSpecificFoundationCategoryRule,
)
from .core_behavior_no_ambient_runtime_access import (
    CoreBehaviorNoAmbientRuntimeAccessRule,
)
from .core_contracts_use_immutable_dataclasses import (
    CoreContractsUseImmutableDataclassesRule,
)
from .core_inner_packages_no_outer_layers_or_io_libraries import (
    CoreInnerPackagesDoNotImportOuterLayersOrIOLibrariesRule,
)
from .core_no_runtime_configuration_or_pydantic import (
    CoreNoRuntimeConfigurationOrPydanticRule,
)
from .core_no_scope_delivery_packages import (
    CoreDoesNotContainDeliveryPackagesRule,
)
from .core_scope_infrastructure_does_not_import_delivery import (
    ScopeInfrastructureDoesNotImportDeliveryRule,
)
from .delivery_controllers_do_not_import_infrastructure import (
    DeliveryControllersDoNotImportInfrastructureRule,
)
from .delivery_foundation_classes_live_under_delivery import (
    DeliveryFoundationClassesLiveUnderDeliveryRule,
)
from .delivery_routes_use_full_api_v1_paths import (
    PublicRoutesUseFullAPIV1PathsRule,
)
from .diwire_container_import_boundary import (
    OnlyIOCDeliveryAppAndTestsImportContainerRule,
)
from .diwire_no_function_injection import DIWireNoFunctionInjectionRule
from .dtos_result_dtos_live_under_dtos import (
    ResultDTOClassesLiveUnderScopeDTOsPackageRule,
)
from .fastapi_agents_md_documents_entrypoint import (
    FastAPIRootAgentsMDDocumentsEntrypointRule,
)
from .foundation_imports_use_scoped_packages import (
    FoundationImportsUseScopedPackagesRule,
)
from .gateways_external_effects_and_no_entity_returns import (
    GatewaysDeclareExternalEffectsAndDoNotReturnEntitiesRule,
)
from .gateways_ports_and_implementations_placement import (
    GatewayPortsAndImplementationsLiveInExpectedPackagesRule,
)
from .logging_no_injected_loggers import (
    LoggingDoesNotInjectLoggersRule,
)
from .packages_init_files_are_empty import (
    InitFilesAreEmptyRule,
)
from .services_effect_no_owned_transactions_or_delivery import (
    EffectServicesDoNotOwnTransactionsOrImportDeliveryRule,
)
from .services_methods_use_keyword_only_arguments import (
    ServiceMethodsUseKeywordOnlyArgumentsRule,
)
from .services_no_generic_base_service import (
    GenericBaseServiceIsNotUsedRule,
)
from .services_pure_no_io_or_runtime_state import (
    PureServicesDoNotDependOnIOOrRuntimeStateRule,
)
from .services_read_no_writes_or_transactions import (
    ReadServicesDoNotPerformWritesOrOwnTransactionsRule,
)
from .services_require_effect_specific_bases import (
    CoreServicesUseEffectSpecificServiceBasesRule,
)
from .services_require_service_suffix import (
    ServiceClassesUseServiceSuffixRule,
)
from .sqlalchemy_models_live_under_scope_infrastructure import (
    SQLAlchemyModelsLiveUnderScopeInfrastructureRule,
)
from .sqlalchemy_models_require_alembic import SQLAlchemyModelsRequireAlembicRule
from .sqlalchemy_no_schema_bootstrap_calls import (
    NoSchemaBootstrapCallsInSourceOrTestsRule,
)
from .tests_core_behavior_resolves_from_container import (
    TestsCoreBehaviorResolvesFromContainerRule,
)
from .tests_fixtures_do_not_bundle_mocks import (
    TestFixturesDoNotBundleMocksRule,
)
from .tests_integration_does_not_mock_internal_collaborators import (
    IntegrationTestsDoNotMockInternalCollaboratorsRule,
)
from .tests_mirror_source_structure import (
    TestsMirrorSourceStructureRule,
)
from .uow_ioc_does_not_register_active_uow import (
    IOCContainerDoesNotRegisterActiveUnitOfWorkRule,
)
from .uow_services_do_not_open_scopes import (
    ServicesDoNotOpenUnitOfWorkScopesRule,
)
from .uow_use_cases_inject_managers import (
    UseCasesInjectUnitOfWorkManagersRule,
)
from .uow_use_cases_no_direct_repositories_or_infrastructure import (
    UseCasesDoNotInjectRepositoriesOrInfrastructureRule,
)
from .uow_use_cases_open_at_most_one_scope import (
    UseCasesOpenAtMostOneUnitOfWorkScopeRule,
)
from .use_cases_commands_and_queries_live_local import (
    CommandAndQueryClassesLiveWithUseCasesRule,
)
from .use_cases_inputs_are_local_commands_or_queries import (
    UseCaseInputsAreLocalCommandsOrQueriesRule,
)
from .use_cases_no_entity_imports_or_returns import (
    UseCasesDoNotImportOrReturnEntitiesRule,
)
from .use_cases_one_per_module import (
    UseCaseModulesDefineOneUseCaseRule,
)
from .use_cases_orchestrate_through_collaborators import (
    UseCasesOrchestrateThroughCollaboratorsRule,
)
from .use_cases_queries_do_not_mutate import (
    QueryUseCasesDoNotCallRepositoryMutatorsRule,
)
from .use_cases_return_dtos import (
    UseCasesReturnDTOsRule,
)

BUILT_IN_RULES: tuple[type[ArchitectureRuleBase], ...] = (
    CoreInnerPackagesDoNotImportOuterLayersOrIOLibrariesRule,
    ScopeInfrastructureDoesNotImportDeliveryRule,
    DeliveryControllersDoNotImportInfrastructureRule,
    CoreDoesNotContainDeliveryPackagesRule,
    FoundationImportsUseScopedPackagesRule,
    UseCasesDoNotImportOrReturnEntitiesRule,
    UseCasesReturnDTOsRule,
    ResultDTOClassesLiveUnderScopeDTOsPackageRule,
    UseCaseInputsAreLocalCommandsOrQueriesRule,
    UseCasesOrchestrateThroughCollaboratorsRule,
    CoreBehaviorNoAmbientRuntimeAccessRule,
    CoreContractsUseImmutableDataclassesRule,
    CoreNoRuntimeConfigurationOrPydanticRule,
    CommandAndQueryClassesLiveWithUseCasesRule,
    CapabilitiesLiveInExpectedPackagesAndUseExpectedSuffixesRule,
    CapabilitiesDoNotOwnWorkflowsOrOtherPortRolesRule,
    GatewayPortsAndImplementationsLiveInExpectedPackagesRule,
    GatewaysDeclareExternalEffectsAndDoNotReturnEntitiesRule,
    QueryUseCasesDoNotCallRepositoryMutatorsRule,
    NonFoundationSourceClassesHaveExplicitBaseClassesRule,
    ClassesRequireExampleDocstringsRule,
    ServiceClassesUseServiceSuffixRule,
    CoreServicesUseEffectSpecificServiceBasesRule,
    GenericBaseServiceIsNotUsedRule,
    ServiceMethodsUseKeywordOnlyArgumentsRule,
    PureServicesDoNotDependOnIOOrRuntimeStateRule,
    ReadServicesDoNotPerformWritesOrOwnTransactionsRule,
    EffectServicesDoNotOwnTransactionsOrImportDeliveryRule,
    ClassesUseSuffixFromMostSpecificFoundationCategoryRule,
    NonFoundationClassesDoNotUseRawCommonBasesRule,
    OnlyIOCDeliveryAppAndTestsImportContainerRule,
    DIWireNoFunctionInjectionRule,
    LoggingDoesNotInjectLoggersRule,
    PublicRoutesUseFullAPIV1PathsRule,
    NoSchemaBootstrapCallsInSourceOrTestsRule,
    SQLAlchemyModelsLiveUnderScopeInfrastructureRule,
    SQLAlchemyModelsRequireAlembicRule,
    DeliveryFoundationClassesLiveUnderDeliveryRule,
    RootAgentsMDDocumentsProjectCommandsRule,
    FastAPIRootAgentsMDDocumentsEntrypointRule,
    TestsMirrorSourceStructureRule,
    TestsCoreBehaviorResolvesFromContainerRule,
    TestFixturesDoNotBundleMocksRule,
    IntegrationTestsDoNotMockInternalCollaboratorsRule,
    ServicesDoNotOpenUnitOfWorkScopesRule,
    UseCasesOpenAtMostOneUnitOfWorkScopeRule,
    UseCasesInjectUnitOfWorkManagersRule,
    UseCasesDoNotInjectRepositoriesOrInfrastructureRule,
    IOCContainerDoesNotRegisterActiveUnitOfWorkRule,
    InitFilesAreEmptyRule,
    UseCaseModulesDefineOneUseCaseRule,
)

__all__ = [
    "BUILT_IN_RULES",
    "CapabilitiesDoNotOwnWorkflowsOrOtherPortRolesRule",
    "CapabilitiesLiveInExpectedPackagesAndUseExpectedSuffixesRule",
    "ClassesRequireExampleDocstringsRule",
    "ClassesUseSuffixFromMostSpecificFoundationCategoryRule",
    "CommandAndQueryClassesLiveWithUseCasesRule",
    "CoreBehaviorNoAmbientRuntimeAccessRule",
    "CoreContractsUseImmutableDataclassesRule",
    "CoreDoesNotContainDeliveryPackagesRule",
    "CoreInnerPackagesDoNotImportOuterLayersOrIOLibrariesRule",
    "CoreNoRuntimeConfigurationOrPydanticRule",
    "CoreServicesUseEffectSpecificServiceBasesRule",
    "DIWireNoFunctionInjectionRule",
    "DeliveryControllersDoNotImportInfrastructureRule",
    "DeliveryFoundationClassesLiveUnderDeliveryRule",
    "EffectServicesDoNotOwnTransactionsOrImportDeliveryRule",
    "FastAPIRootAgentsMDDocumentsEntrypointRule",
    "FoundationImportsUseScopedPackagesRule",
    "GatewayPortsAndImplementationsLiveInExpectedPackagesRule",
    "GatewaysDeclareExternalEffectsAndDoNotReturnEntitiesRule",
    "GenericBaseServiceIsNotUsedRule",
    "IOCContainerDoesNotRegisterActiveUnitOfWorkRule",
    "InitFilesAreEmptyRule",
    "IntegrationTestsDoNotMockInternalCollaboratorsRule",
    "LoggingDoesNotInjectLoggersRule",
    "NoSchemaBootstrapCallsInSourceOrTestsRule",
    "NonFoundationClassesDoNotUseRawCommonBasesRule",
    "NonFoundationSourceClassesHaveExplicitBaseClassesRule",
    "OnlyIOCDeliveryAppAndTestsImportContainerRule",
    "PublicRoutesUseFullAPIV1PathsRule",
    "PureServicesDoNotDependOnIOOrRuntimeStateRule",
    "QueryUseCasesDoNotCallRepositoryMutatorsRule",
    "ReadServicesDoNotPerformWritesOrOwnTransactionsRule",
    "ResultDTOClassesLiveUnderScopeDTOsPackageRule",
    "RootAgentsMDDocumentsProjectCommandsRule",
    "SQLAlchemyModelsLiveUnderScopeInfrastructureRule",
    "SQLAlchemyModelsRequireAlembicRule",
    "ScopeInfrastructureDoesNotImportDeliveryRule",
    "ServiceClassesUseServiceSuffixRule",
    "ServiceMethodsUseKeywordOnlyArgumentsRule",
    "ServicesDoNotOpenUnitOfWorkScopesRule",
    "TestFixturesDoNotBundleMocksRule",
    "TestsCoreBehaviorResolvesFromContainerRule",
    "TestsMirrorSourceStructureRule",
    "UseCaseInputsAreLocalCommandsOrQueriesRule",
    "UseCaseModulesDefineOneUseCaseRule",
    "UseCasesDoNotImportOrReturnEntitiesRule",
    "UseCasesDoNotInjectRepositoriesOrInfrastructureRule",
    "UseCasesInjectUnitOfWorkManagersRule",
    "UseCasesOpenAtMostOneUnitOfWorkScopeRule",
    "UseCasesOrchestrateThroughCollaboratorsRule",
    "UseCasesReturnDTOsRule",
]
