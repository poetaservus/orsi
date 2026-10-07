# 99 — Sources, selection and licensing

Research snapshot: 7 October 2026. This package is an edited synthesis, not an
unmodified concatenation. Sources were inspected as data; their hooks, scripts,
installers and model-provider settings were not executed or inherited.

## Selected source families

### Jeff Allan / claude-skills — Python Pro (MIT)

Revision: `1be15d8064f88fc25216442406d40add8fd23b53`.

[Python Pro entry point](https://github.com/Jeffallan/claude-skills/blob/1be15d8064f88fc25216442406d40add8fd23b53/skills/python-pro/SKILL.md)
and its type-system, async-patterns, standard-library, testing and packaging
references informed explicit interfaces, Python idioms and task-based routing.

Adaptation: removed mandatory async-first implementation, universal strict-mode
and docstring rules, >90% coverage requirements and toolchain preferences.
Corrected the implication that valid `os.path` usage is deprecated. Static type
claims now distinguish annotations from runtime validation. Illustrative upstream
snippets depending on imaginary application modules were not copied as runnable
code.

### Seth Hobson / agents — Python development skills (MIT)

Revision: `46891e7e60da0e52baf1050b7b6391b64e84c6d9`.

[Python development collection](https://github.com/wshobson/agents/tree/46891e7e60da0e52baf1050b7b6391b64e84c6d9/plugins/python-development/skills).
The specialized skills covering design patterns, project structure, type safety,
testing, error handling, resource management, resilience, configuration,
observability, packaging, performance, async patterns and anti-patterns informed
the corresponding references here.

Adaptation: partial failure versus atomic batches is a contract choice, not an
always-continue rule. Retry policies require idempotency and an overall budget.
CPU parallelism distinguishes Python threads, native code and processes; task
admission distinguishes active concurrency from allocated task count. Logging
is content-conscious and does not require production metrics for a tiny script.
The package does not chain to uninstalled sibling skills.

### Trail of Bits / skills — Modern Python (CC BY-SA 4.0)

Revision: `82fe8226252622fa807643bdca1710901198553a`.

[Modern Python entry point](https://github.com/trailofbits/skills/blob/82fe8226252622fa807643bdca1710901198553a/plugins/modern-python/skills/modern-python/SKILL.md)
and its pyproject, script metadata, testing and migration references informed
environment-aware setup, developer/runtime dependency separation and installable
deliverables. [Upstream license](https://github.com/trailofbits/skills/blob/82fe8226252622fa807643bdca1710901198553a/LICENSE).

Adaptation: retained modern tooling as choices and preserved working pip/Poetry/
Black/mypy/Pyright workflows. Removed automatic migration, mandatory uv/ty/prek
and build-backend replacement. Hooks and remote installer commands are not part
of this instruction-only package.

## Synthesis map

| Reference | Main influences | Additional editorial work |
| --- | --- | --- |
| 00 foundations | Python Pro, project structure | Explicit working contract and version gates |
| 10 architecture | Design patterns, Python Pro | Refactoring preservation and lifecycle ownership |
| 20 types | Type safety, Python Pro type system | Runtime/static distinction and strict boundary example |
| 30 errors/resources | Errors, resilience, resource management | Failure-preserving save example and ambiguous side effects |
| 40 testing | Testing patterns, Python Pro, Modern Python | No-op-resistant checks and failed-save example |
| 50 concurrency | Async patterns, Python Pro | Cancellation ownership, admission limits and Qt handoff |
| 60 packaging | Packaging, Modern Python | Existing workflow preservation and installed-artifact checks |
| 70 security/data | Configuration, observability, Modern Python | Privacy, filesystem races and bounded trust boundaries |
| 80 debugging/performance | Performance, anti-patterns | Minimal reproduction, baseline and honest measurement |
| 90 applications | Architecture/async/testing principles | Original CLI, service and desktop delivery guidance |
| 95 review | Anti-patterns, testing, resource management | Bounded review and evidence-based definition of done |

## Primary documentation checked

These are verification links, not copied manuals or dependencies. The reader
does not fetch them automatically. Check the version appropriate to the project.

- [Python asyncio tasks and cancellation](https://docs.python.org/3/library/asyncio-task.html)
- [PyPA packaging projects](https://packaging.python.org/en/latest/tutorials/packaging-projects/)
- [pytest monkeypatch behavior](https://docs.pytest.org/en/stable/how-to/monkeypatch.html)
- [Qt for Python QThread ownership](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QThread.html)
- [Python pickle trust warning](https://docs.python.org/3/library/pickle.html)

## Reuse terms

The `python-coder` instruction package and its Markdown references are licensed
under [Creative Commons Attribution-ShareAlike 4.0 International](https://creativecommons.org/licenses/by-sa/4.0/)
([legal code](https://creativecommons.org/licenses/by-sa/4.0/legalcode.en)).
Copyright 2026 O.R.S.I. contributors for new editorial material. Attribution to
Trail of Bits and the above authors is retained for the adapted material. Changes
are identified above. Redistributed adaptations of this package must preserve
attribution, indicate changes and use the same license or an officially
compatible one. No endorsement by upstream authors is implied.

The original executable Python examples authored for references 20, 30, 40 and
50 are additionally offered under the MIT license below, so they can be reused
as code separately from this documentation. Using the skill as guidance does
not require licensing an independently written user project under CC BY-SA.

### MIT notice — original runnable examples

Copyright (c) 2026 O.R.S.I. contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

### MIT notice — Jeff Allan / claude-skills

MIT License

Copyright (c) 2025

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

### MIT notice — Seth Hobson / agents

MIT License

Copyright (c) 2024 Seth Hobson

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
