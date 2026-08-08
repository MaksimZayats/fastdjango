from __future__ import annotations

import ast

from specx.testing.architecture.context import ArchitectureContext
from specx.testing.architecture.models import SpecxArchitectureViolation
from specx.testing.architecture.rule_id import SpecxRuleId
from specx.testing.architecture.rules._shared import ArchitectureRuleBase, violation


class FastAPIRootAgentsMDDocumentsEntrypointRule(ArchitectureRuleBase):
    """Require FastAPI projects to document the project-specific application entrypoint."""

    id: SpecxRuleId = SpecxRuleId.FASTAPI_ROOT_AGENTS_MD_DOCUMENTS_ENTRYPOINT
    family = "fastapi"
    default_enabled = False
    required_project_surface: str | None = "delivery/fastapi"
    remediation: str | None = (
        "Add the exact importable FastAPI application entrypoint to `AGENTS.md`."
    )

    def check(self, context: ArchitectureContext) -> tuple[SpecxArchitectureViolation, ...]:
        path = context.project_root / "AGENTS.md"
        if not path.exists():
            return (violation(self.id, path=path, message="AGENTS.md is missing"),)
        expected = f"{context.config.package_name}.delivery.fastapi.__main__:app"
        entrypoint_path = context.src_root / "delivery" / "fastapi" / "__main__.py"
        findings: list[SpecxArchitectureViolation] = []
        if entrypoint_path not in context.ast_project.files:
            findings.append(
                violation(
                    self.id,
                    path=entrypoint_path,
                    message="documented FastAPI entrypoint module is missing",
                )
            )
        elif not _defines_app(context.tree(entrypoint_path)):
            findings.append(
                violation(
                    self.id,
                    path=entrypoint_path,
                    message="FastAPI entrypoint module does not define or import `app`",
                )
            )
        if expected not in " ".join(path.read_text(encoding="utf-8").split()):
            findings.append(
                violation(
                    self.id,
                    path=path,
                    message=f"missing project FastAPI entrypoint {expected!r}",
                )
            )
        return tuple(findings)


def _defines_app(tree: ast.Module) -> bool:
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == "app":
                return True
        elif isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == "app" for target in node.targets):
                return True
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == "app":
                return True
        elif isinstance(node, (ast.Import, ast.ImportFrom)) and any(
            (alias.asname or alias.name.rsplit(".", maxsplit=1)[-1]) == "app"
            for alias in node.names
        ):
            return True
    return False
