# 60 — Environments, dependencies, tooling and distribution

Read for project setup, dependency changes, entry points or packaging.

## Respect the environment that runs the code

Inspect the actual interpreter, project Python floor, dependency manager and
lockfile. Use that environment for installation and checks. Prefer
`python -m <tool>` when it prevents invoking a tool from a different environment;
use `uv run`, Poetry, a bundled runtime or the repository's wrapper when that is
the established route. Do not install into a system interpreter just because it
is first on PATH. Do not recreate a lockfile with a different manager.

For new work, choose tooling according to the deliverable and constraints. uv is
a useful environment/dependency option; Ruff can lint and format; pytest and a
supported type checker can verify behavior and contracts. Existing pip, Poetry,
Black, mypy, Pyright or unittest workflows remain valid. A toolchain migration is
its own change, not a prerequisite for fixing a function.

## Select the deliverable

| Deliverable | Appropriate packaging decision |
| --- | --- |
| Standard-library script | Clear entry point and target Python version |
| One script needing dependencies | Document installation; PEP 723 if the chosen runner supports it |
| Application in an existing repo | Existing project/dependency conventions |
| Reusable library or installable CLI | `pyproject.toml`, declared backend, package contents, entry point |
| Frozen desktop application | Target OS/architecture, plugins/assets and clean-machine smoke test |

A `src/` layout helps prevent testing only accidental source imports; do not
reorganize a working flat package without need. In either layout, test the built
artifact outside the source tree. Import package names can differ from the
distribution name: declare and verify both correctly.

## Declare only what the deliverable needs

Use `requires-python` consistent with actual syntax and APIs. Keep runtime
dependencies separate from development tools. Put user-installable extras in
`[project.optional-dependencies]`; use the existing development group mechanism
for lint/test tooling. Declare the build backend and build requirements. Do not
force one backend, dynamic version provider or publisher.

Choose and verify a real dependency, compatible version and suitable license
before adding it. Check whether the project already provides an equivalent.
Avoid ambient undeclared imports, fake package names and blindly using latest
versions. A lockfile fixes one environment; a reusable library's dependency
ranges are a separate compatibility contract.

## Coordinate checks

Configure one authoritative formatter and avoid opposing lint/format rules.
Use the repository's targeted Ruff/Black/isort settings. Match the type checker's
Python/platform target and optional stubs to the actual project. Do not enable
every rule or strict mode wholesale during a small feature change.

Keep application startup explicit. An installable CLI can expose a
`[project.scripts]` entry point pointing at a callable. That callable must exist,
have the expected arguments/return contract, and not rely on the current directory
for bundled assets. Imports should not write files, connect to a service or start
the UI automatically.

## Verify distribution, not just source code

When packaging is requested:

1. Run the configured build and metadata validation tools.
2. Inspect wheel/sdist contents for code, data and licensing; exclude secrets,
   caches, developer state and test artifacts not intentionally distributed.
3. Install the wheel into an isolated environment compatible with the Python
   floor and import it away from the repository.
4. Exercise the console entry point or GUI startup and required assets/plugins.
5. Report which supported interpreter/platform combinations were actually checked.

Building locally does not verify another OS's native dependencies or multimedia
codecs. PyPI publication and releases are external actions requiring the user's
authorization for that operation. A local build is not permission to publish.

Official reference: [PyPA packaging guide](https://packaging.python.org/en/latest/tutorials/packaging-projects/).
For CLI/GUI delivery read [90](90-applications.md); for final gates read [95](95-review.md).
