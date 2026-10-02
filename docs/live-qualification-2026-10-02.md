# Mandatory live qualification before baseline promotion

This replaces the earlier rule that allowed integration after a deterministic suite with skipped
live gates. `main` retains historical source. `working-baseline` is created or advanced only after
a matching complete live qualification report. This gate implementation is itself a candidate
until it passes. A clean checkout or an `accepted` model-profile label is not evidence of a
qualified build. No old revision is retrospectively certified.

## Required matrix

Every versioned local chooser profile is required, including the accepted 14B, load-tested 3B and
experimental 4B VL profile. Another discovered chooser model blocks promotion until it has a
versioned identity/profile and participates. A removed/unavailable profile cannot silently shrink
the matrix. Each of these workflows runs twice per profile, giving 30 required live cells:

| Workflow | Required observations |
| --- | --- |
| Ordinary conversation | Exact existing `chat-0` response, completed durable outcome, no tools |
| Long code | Same existing Pygame prompt for every model and repetition; known normal finish, closed Python fence, compilation and required classes/import; no tool execution |
| Read/edit/clarify/follow-up | One continuous session reading a 65-KiB stylesheet; approved precise edit; clarification leaves bytes unchanged; follow-up makes the second exact edit; only the two expected approvals; every turn durably completed |
| Cancel, then another task | Actual active inference cancelled through Qt; durable cancelled outcome; worker and controls released; next stat task completes in the same session and verifies unchanged 83-byte fixture |
| Model round trip | Current model -> another shipped model -> current model; same session retained; inference succeeds at each stage; replaced servers exit; actual identity, context/output limits and sampling restored |

The ordinary, long-code, first edit, cancellation and metadata request strings reuse existing
acceptance prompts. New session/clarification strings are frozen in
`app/infrastructure/qualification.py` and hashed as a suite. Model/provider sampling, accepted
prompts and production permissions are not adjusted to make a model pass. Fixture paths vary;
the prompt templates and original bytes do not. Two repeats are a minimum, not a statistical
guarantee of reliability.

The long-code validator compiles generated code without executing it. Its structural checks
identify truncation and malformed code; they do not prove gameplay quality or every game feature.
The screenshot did not provide the full original game prompt, so the gate uses the repository's
existing Pygame prompt rather than claiming to reconstruct unseen requirements.

Live workflows use the real local server, real files, production capabilities, journal and store,
and the real off-screen Qt window/worker/control path. There are no scripted provider responses.
Approvals are test-only and restricted to the exact stylesheet edit resource. Generated programs
are never run. Existing user sessions, model selection state and user-owned servers are preserved;
the runner has its own synthetic workspace, state, selection and owned servers.

## Fail-closed evidence

The runner resolves every required model before allocating anything. Missing files, wrong model
hashes, unsafe/downgraded memory resolutions, an uncommitted candidate or an unsupported host block
the run. Limits are checked again during switches, against the running server's `/props`, and
against its actual output/sampling configuration. The accepted 20% free-GPU headroom check remains.
It does not force context or stop another application's server to obtain memory.

Qualification requires all 30 cells, exact expected durable terminal sequences, verified file
bytes, UI release, preserved sessions and released owned processes. A cell marked skipped,
missing, failed or stopped where completion was expected blocks promotion. A complete regression
suite with no failures/errors is also required. Legacy opt-in pytest tests may remain skipped
because the separate mandatory live matrix replaces their absence as qualification evidence;
those skips never count as passed live cells. Windows journal-write failures block qualification,
even when a focused retry later passes. They must be repaired or a fresh entire run must pass;
the gate does not rewrite a failed report into a pass.

Evidence binds the exact clean Git revision, tracked application/config/test/tool/package sources,
fixed prompt suite, model manifest, effective feature flags, Python version and runtime executable
hashes. Promotion checks installed GGUF hashes again. Any source or report mismatch invalidates
qualification. Model changes, environment flag changes and subsequent commits require a fresh run.
The context-recovery flag additionally requires its separate measured acceptance; this candidate
does not qualify enabling that previously rejected policy.

Reports contain only identities/hashes, flags/limits, statuses, terminal/finish/usage counters,
fixture hashes and exception types. Synthetic session history and regression logs live separately
in the ignored workspace. Reports are local trusted workflow artifacts, not cryptographic
attestations against an owner editing both code and evidence. Raw Git can bypass process policy;
only the supported promotion/build entry points create a qualified baseline/release.

## Commands

Commit the candidate first, leaving the checkout clean. Choose a new workspace each run:

```powershell
.\runtime\python\python.exe tools/live_qualification.py --workspace state/qualification-run-new --report state/diagnostics/live-qualification-new.json
.\runtime\python\python.exe tools/promote_working_baseline.py --report state/diagnostics/live-qualification-new.json
```

The runner exits nonzero for blocked or failed qualification and never changes branches. The
verification command is read-only. Only after it passes:

```powershell
.\runtime\python\python.exe tools/promote_working_baseline.py --report state/diagnostics/live-qualification-new.json --promote
```

Promotion uses fast-forward and compare-and-set reference updates, preserves unmerged history,
refuses to move a checked-out working-baseline in another worktree, and performs no remote action.
Release packaging also verifies evidence **before** invoking Nuitka:

```powershell
.\packaging\build-nuitka.ps1 -Python .\runtime\python\python.exe -QualificationReport state/diagnostics/live-qualification-new.json
```

Runtime dependency preparation and launching a development checkout remain available so a
candidate can be tested. Neither operation promotes or labels it a qualified build. See the
content-free run report for current observations; absence of passing exact-revision evidence
always means unqualified.
