---
name: specx
description: Navigate a specx Python project by inspecting its shape, using its project commands and scaffolds, and resolving structured architecture diagnostics.
---

# specx project navigation

Use this optional skill to navigate an existing specx project. Correctness comes from the project's executable checks, not from installing this skill.

1. Read the repository `AGENTS.md`, `pyproject.toml`, `Makefile`, and the relevant source and test modules.
2. Inspect components and use cases with `specx project ... --output-format json` before changing or scaffolding behavior.
3. Prefer the project's existing commands and specx scaffold dry runs over inventing parallel structure.
4. Run `specx check --output-format json`; follow each diagnostic's `hint` and `documentation_url`.
5. Consult the linked public architecture, core behavior, delivery, DI, settings, persistence, migration, testing, or tooling guide when judgment is still required.
6. Finish with the project's full check command, normally `make check`.

Do not copy generic architecture policy into project guidance. If a rule cannot express a judgment, document the project-specific decision in the repository.
