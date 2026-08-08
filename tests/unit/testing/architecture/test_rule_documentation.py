from __future__ import annotations

import ast
import re
from pathlib import Path

from specx.testing.architecture.models import ArchitectureRuleType
from specx.testing.architecture.rules import BUILT_IN_RULES

REPOSITORY_ROOT = Path(__file__).parents[4]
RULE_DOCS_ROOT = REPOSITORY_ROOT / "docs" / "rules"
RULE_REFERENCE_PATH = REPOSITORY_ROOT / "docs" / "pages" / "RulesReference.mdx"
REQUIRED_HEADINGS = (
    "### Why this exists",
    "### Failing example",
    "### Passing example",
    "### Detection notes",
)


def test_every_builtin_rule_has_one_complete_reference() -> None:
    rule_documents = [
        (path, path.read_text(encoding="utf-8")) for path in sorted(RULE_DOCS_ROOT.glob("*.mdx"))
    ]
    documented_rule_ids = [_string_export(source, "ruleId") for _, source in rule_documents]
    documented_rules = dict(zip(documented_rule_ids, rule_documents, strict=True))
    built_in_rules = {str(rule.metadata().rule_id): rule for rule in BUILT_IN_RULES}

    assert len(documented_rule_ids) == len(set(documented_rule_ids))
    assert documented_rules.keys() == built_in_rules.keys()

    reference_source = RULE_REFERENCE_PATH.read_text(encoding="utf-8")
    reference_imports = re.findall(
        r'^import (\w+) from "\.\./rules/([a-z0-9_]+)\.mdx"$',
        reference_source,
        flags=re.MULTILINE,
    )
    expected_stems = [rule.__module__.rsplit(".", maxsplit=1)[1] for rule in BUILT_IN_RULES]
    assert [stem for _, stem in reference_imports] == expected_stems
    assert len({component for component, _ in reference_imports}) == len(reference_imports)
    index_rows = [line for line in reference_source.splitlines() if line.startswith("| [`")]
    expected_index_rows = [_index_row(rule) for rule in BUILT_IN_RULES]
    assert index_rows == expected_index_rows

    for rule_id, rule in built_in_rules.items():
        metadata = rule.metadata()
        path, source = documented_rules[rule_id]
        expected_stem = rule.__module__.rsplit(".", maxsplit=1)[1]
        expected_status = (
            "Enabled by default" if metadata.default_enabled else f"Opt-in `{metadata.family}` rule"
        )
        component = next(
            component for component, stem in reference_imports if stem == expected_stem
        )

        assert path.stem == expected_stem
        assert _string_export(source, "summary") == metadata.summary
        assert _string_export(source, "family") == metadata.family
        assert _bool_export(source, "defaultEnabled") is metadata.default_enabled
        assert _optional_string_export(source, "requiredProjectSurface") == (
            metadata.required_project_surface
        )
        assert source.count(f'<span id="{expected_stem}"></span>') == 1
        assert metadata.remediation
        assert metadata.documentation_url == (
            f"https://specx.dev/docs/reference/architecture-rules/#{expected_stem}"
        )
        assert source.count(f"## `{rule_id}`") == 1
        assert f"\n\n{metadata.summary}\n\n**Status:** {expected_status}." in source
        if metadata.required_project_surface is None:
            assert "**Required project surface:**" not in source
        else:
            assert f"**Required project surface:** `{metadata.required_project_surface}`." in source
        assert all(heading in source for heading in REQUIRED_HEADINGS)
        examples = re.findall(r"```python\n(.*?)\n```", source, flags=re.DOTALL)
        assert len(examples) == 2
        for example in examples:
            ast.parse(example)
        assert reference_source.count(f"../rules/{expected_stem}.mdx") == 1
        assert reference_source.count(f"<{component} />") == 1


def _index_row(rule: ArchitectureRuleType) -> str:
    metadata = rule.metadata()
    rule_id = str(metadata.rule_id)
    stem = rule.__module__.rsplit(".", maxsplit=1)[1]
    status = "Default" if metadata.default_enabled else f"Opt-in `{metadata.family}`"
    return f"| [`{rule_id}`](#{stem}) | {status} | {metadata.summary} |"


def _string_export(source: str, name: str) -> str:
    value = _export_value(source, name)
    parsed = ast.literal_eval(value)
    assert isinstance(parsed, str)
    return parsed


def _bool_export(source: str, name: str) -> bool:
    value = _export_value(source, name)
    assert value in {"false", "true"}
    return value == "true"


def _optional_string_export(source: str, name: str) -> str | None:
    value = _export_value(source, name)
    if value == "null":
        return None
    parsed = ast.literal_eval(value)
    assert isinstance(parsed, str)
    return parsed


def _export_value(source: str, name: str) -> str:
    match = re.search(rf"^export const {name} = (.+)$", source, flags=re.MULTILINE)
    assert match is not None, f"missing {name} export"
    return match.group(1)
