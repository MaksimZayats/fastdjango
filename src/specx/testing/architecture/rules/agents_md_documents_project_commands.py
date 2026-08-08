from __future__ import annotations

from specx.testing.architecture.context import ArchitectureContext, documented_make_targets
from specx.testing.architecture.models import SpecxArchitectureViolation
from specx.testing.architecture.rule_id import SpecxRuleId
from specx.testing.architecture.rules._shared import ArchitectureRuleBase, violation


class RootAgentsMDDocumentsProjectCommandsRule(ArchitectureRuleBase):
    """Keep generated agent guidance aligned with real project paths and runnable commands."""

    id: SpecxRuleId = SpecxRuleId.ROOT_AGENTS_MD_DOCUMENTS_PROJECT_COMMANDS
    remediation: str | None = (
        "Document the real package path and executable Make targets, including the JSON "
        "architecture-check command, without copying specx architecture policy."
    )

    def check(self, context: ArchitectureContext) -> tuple[SpecxArchitectureViolation, ...]:
        path = context.project_root / "AGENTS.md"
        if not path.exists():
            return (violation(self.id, path=path, message="AGENTS.md is missing"),)
        text = path.read_text(encoding="utf-8")
        normalized = " ".join(text.split())
        required = {
            f"src/{context.config.package_name}",
            "make check",
            "make lint",
            "make test",
            "specx check --output-format json",
        }
        missing = sorted(fragment for fragment in required if fragment not in normalized)
        findings: list[SpecxArchitectureViolation] = []
        makefile_targets = context.makefile_targets()
        if not context.src_root.is_dir():
            findings.append(
                violation(
                    self.id,
                    path=context.src_root,
                    message="documented source package path does not exist",
                )
            )
        if missing:
            findings.append(violation(self.id, path=path, message=f"missing fragments {missing}"))
        missing_required_targets = sorted({"check", "lint", "test"} - makefile_targets)
        if missing_required_targets:
            findings.append(
                violation(
                    self.id,
                    path=context.project_root / "Makefile",
                    message=f"missing required Make targets {missing_required_targets}",
                )
            )
        missing_targets = sorted(
            documented_make_targets(text) - makefile_targets - {"check", "lint", "test"}
        )
        if missing_targets:
            findings.append(
                violation(
                    self.id,
                    path=path,
                    message=f"documents missing Make targets {missing_targets}",
                )
            )
        return tuple(findings)
