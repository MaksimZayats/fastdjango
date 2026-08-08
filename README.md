<p align="center">
  <a href="https://specx.dev">
    <img alt="specx" src="https://raw.githubusercontent.com/maksimzayats/specx/main/docs/public/favicon.svg" width="72">
  </a>
</p>

<h1 align="center">specx</h1>

<p align="center">
  Executable architecture guardrails for agent-built Python services.
</p>

<p align="center">
  <a href="https://pypi.org/project/specx/"><img alt="PyPI" src="https://img.shields.io/pypi/v/specx.svg"></a>
  <a href="https://pypi.org/project/specx/"><img alt="Python versions" src="https://img.shields.io/pypi/pyversions/specx.svg"></a>
  <a href="https://github.com/maksimzayats/specx/actions/workflows/deploy-storybook.yml"><img alt="Documentation build" src="https://img.shields.io/github/actions/workflow/status/maksimzayats/specx/deploy-storybook.yml?branch=main&label=docs"></a>
  <a href="https://github.com/maksimzayats/specx/blob/main/LICENSE.md"><img alt="MIT license" src="https://img.shields.io/github/license/maksimzayats/specx.svg"></a>
</p>

<p align="center">
  <a href="https://specx.dev"><strong>Documentation</strong></a> ·
  <a href="https://specx.dev/docs/overview/quickstart/"><strong>Quickstart</strong></a> ·
  <a href="https://specx.dev/docs/reference/architecture-rules/"><strong>Rules</strong></a> ·
  <a href="https://github.com/maksimzayats/specx/issues"><strong>Issues</strong></a>
</p>

`specx` gives coding agents a shared architecture for Python backends and checks
that the implementation still follows it. Typed foundation classes, generated
project guidance, project commands, and rule-based checks work without any
installed skill.

## Highlights

- **Enforcement-first.** Structured diagnostics include remediation and links
  to authoritative rule documentation; one optional skill helps navigation.
- **Architecture as code.** `specx check` catches layer leaks, incorrect
  inheritance, hidden transaction ownership, misplaced types, and test drift.
- **Project management CLI.** Inspect core components, scaffold typed use cases,
  and run trusted application actions through the project's DI container.
- **Explicit building blocks.** Typed foundation classes give use cases,
  services, capabilities, controllers, repositories, gateways, and DTOs clear
  roles.
- **A strict starting point.** `specx init` creates a small, framework-neutral
  service with uv, Ruff, mypy, pytest, DI composition, and mirrored tests.

## Installation

Install the CLI in an isolated environment with
[uv](https://docs.astral.sh/uv/getting-started/installation/):

```sh
uv tool install specx
```

Upgrade it later with `uv tool upgrade specx`.

The optional navigation skill is installed separately and requires Node.js.
Projects do not need it for specx enforcement:

```sh
npx skills add maksimzayats/specx --skill specx --agent codex -y
```

See [Install agent skills](https://specx.dev/docs/guides/install-agent-skills/)
for other agents and installation options.

## Quickstart

Create a framework-neutral Python service and run its checks:

```console
$ specx init order-service
$ cd order-service
$ make check
```

For an existing `src/`-layout project, add specx as a project dependency:

```sh
uv add specx
uv run specx check
```

Inspect the available guardrails from the command line:

```sh
uv run specx rule list
uv run specx rule explain use-cases.return-dtos
```

Explore and run the project's application actions:

```sh
uv run specx project component list
uv run specx project use-case list
uv run specx project use-case show health/check-health
uv run specx project use-case run health/check-health
uv run specx project use-case create orders/get-order --kind query --dry-run --output-format json
```

Project commands find the nearest `pyproject.toml` ancestor by default. Use `--output-format json`
for stable inspection/scaffold output and `specx project --error-format json ...` for structured
failures. Missing or mistyped IDs include discovered suggestions; install dynamic completion with
`specx --install-completion`.

Configuration lives in `pyproject.toml`. See the
[configuration reference](https://specx.dev/docs/reference/configuration/) and
[adoption guide](https://specx.dev/docs/guides/adopt-specx-in-an-existing-service/)
for selectors, exclusions, JSON output, and incremental rollout.

## Documentation

- [Quickstart](https://specx.dev/docs/overview/quickstart/)
- [How specx works](https://specx.dev/docs/overview/how-specx-works/)
- [Architecture rules](https://specx.dev/docs/reference/architecture-rules/)
- [Foundation API](https://specx.dev/docs/reference/foundation-api/)
- [Optional skill](https://specx.dev/docs/reference/skills-catalog/)
- [CLI reference](https://specx.dev/docs/reference/cli/)

## Contributing

Contributions are welcome. See the
[contributing guide](https://github.com/maksimzayats/specx/blob/main/CONTRIBUTING.md)
for local setup and validation. Run `make check` before opening a pull request.

## License

specx is released under the
[MIT License](https://github.com/maksimzayats/specx/blob/main/LICENSE.md).
