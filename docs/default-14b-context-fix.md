# Default 14B context repair, 3 October 2026

The default `Qwen314BQ4KM.gguf` profile must retain its 16,384-token context
when GPU memory is constrained. Previously it could select 8,192 GPU tokens
or 4,096 CPU tokens, both of which can reject the full agent catalog before
a simple greeting reaches inference.

The repair retains 16,384 tokens as the minimum and CPU fallback context for
the default 14B profile and changes its context cache from FP16 to `q8_0`.
The declared cache estimate changes from 163,840 to 87,040 bytes per token.
The catalog now derives that estimate from both GGUF dimensions and cache
format, rather than always assuming FP16. Allocation diagnostics use the same
corrected estimate as the guard.

The alternate chat-only llama-cpp-python backend also passes the configured
Q8_0 cache types for keys and values with flash attention enabled. It previously
ignored `cache_type`; leaving that behavior would make its actual allocation
disagree with the newly corrected guard. Its FP16 constructor options stay unchanged.

Q8_0 stores 32 values plus a two-byte scale in 34 bytes, versus FP16's 64 bytes.
The estimator includes that scale overhead, using the 17/32 storage ratio rather
than assuming exactly half the memory. At 16,384 tokens, the default model's
estimated context cache drops from 2,560 to 1,360 MiB. See the pinned server's
[Q8_0 block definition](https://github.com/ggml-org/llama.cpp/blob/e3546c7948e3af463d0b401e6421d5a4c2faf565/ggml/src/ggml-common.h#L236).

The default model, weight file, sampling, memory guard, GPU output target of
4,096 and CPU output cap of 1,024 remain unchanged. Other model profiles,
prompts, routing, tools and admission accounting are unchanged. Quantizing the
context cache can change model output; the fixed native requests below verify
the repair's scope, without claiming broader model qualification.

If the GPU cannot safely hold the required context, the existing guard selects
CPU execution with the full context. This can be slower, but it no longer
selects an undersized context that makes the default agent unusable.

## Evidence and verification

Before the repair, the small-skill audit on `8318bfd` recorded a 4,096-token
14B CPU context. The unchanged stat request needed 5,188 tokens without any
skill, including schema, output and safety reserves. All eight answer workflows
were rejected before inference. At an 8,192-token GPU context with the 4,096
output reserve, the same baseline budget is 8,260: still too large. See
[the earlier small-skill audit](simple-skill-validation.md).

Five deterministic regression cases exercise the shipped default profile with
no GPU, very low GPU memory, memory sufficient for the old smaller GPU contexts,
and sufficient GPU memory for the complete context. Each retains the default
model and sampling, sends `hey` through the actual conversation/agent admission
path with all 12 production tools, preserves the current request, and fits the
context. GPU offload remains disabled when the guard rejects the full allocation.

Final focused model/profile/lifecycle/backend/registry checks: **113 passed**.
The new cache regression verifies scale overhead, effective memory selection
and consistent allocation diagnostics while existing FP16 behavior remains covered.

Native validation uses the actual 14B weights and pinned llama-server, all 12
production tools, full-local read mode with a synthetic home, denied write/launch
approvals, and isolated conversations and selection state. The acceptance
requests remain unchanged:

- `hey`, before and after a real model switch.
- `Use filesystem.stat to inspect index.html and report whether it exists.`
- The fixed Anthropic CSS request from the small-skill audit, with explicit activation.
- `Reply with OK only.` on the temporary switch to the existing smaller model.

The running server's `/props` confirms the actual context, rather than relying
on configuration alone. Switching away and back must release each previous owned
server before loading its replacement, restore 14B selection, and preserve profile
bytes and sampling. The final shutdown must release every validation server.

The corrected native repair gate **passed all five workflows**. Both 14B loads
ran on the GPU with server-confirmed 16,384-token context and 4,096-token output
allowance. Greeting, successful native stat, explicit CSS skill and the return
to 14B completed without truncation. The smaller model was used only for the
required switch test; 14B remains the default and final selected test model.

The two 14B loads left 4,565 and 4,582 MiB free of 16,384 MiB total: both above
20% headroom. Observed allocations were 9,873 and 9,852 MiB, below the unchanged
guard's corrected 11,827.21 MiB estimate. Both loads verified the original
14B weight hash. Six physical requests used 22,727 input tokens and 1,556 output
tokens. All three owned servers exited; the full 12-tool schema stayed identical.

The unchanged small-skill audit also **passed on the default 14B**: all eight
answer workflows completed, all four explicit/automatic branding checks matched
the skill, five unrelated requests returned no match, and stat succeeded both
without and with the skill. Exact skill injection and the identical full tool
catalog passed. Its server exited. Seventeen physical requests used 40,926 input
tokens and 3,511 output tokens. No selector prompt or acceptance request changed.

The real alternate chat-only backend also loaded 14B on the GPU at 16,384 tokens,
confirmed Q8_0 key/value cache types, completed the fixed `OK` request without
truncation, and closed the model. The user's saved selection was read back as
14B; the tests did not change it.

The final full regression **passed 1,371 tests and 15 subtests, with 58 skips**
in 192.53 seconds, with all validation models closed before the run. The skips
are seven host symbolic-link cases and 51 opt-in legacy live gates; they are
not counted as passed model qualification. All earlier failures remain recorded below.

The first native attempt answered `hey` and completed a native stat round trip,
but its fixture was under the application root while full-local relative paths
resolve under the configured home. The tool correctly returned `not_found`.
The test home was corrected to the isolated fixture directory, preserving the
acceptance prompt and runtime path policy. That attempt's evidence remains in
`state/test-artifacts/default14b-fix/native/`; it is not counted as a passed tool gate.

A second FP16 attempt with the corrected fixture still used CPU fallback and
hit the existing request timeout on stat. Its server exited and its evidence
remains under `native-final/`. It is failed evidence, not a passed native gate.
This justified reducing cache memory rather than relying on a larger CPU context
alone. The final passing repair uses the supported quantized cache on the GPU.
Extremely constrained GPU/CPU operation is not a passed live qualification gate.

The first full suite recorded **1 failed, 1,367 passed, 58 skipped and 15 subtests
passed**. The failure was `WinError 5` during the unchanged skill-registry directory
rename test. Its complete 39-test group passed the isolated recheck. The cause
of that intermittent Windows failure is unresolved; it was not repaired as part
of this profile change.

A second preliminary full suite also recorded **1 failed, 1,367 passed, 58 skipped
and 15 subtests passed**. Its unchanged 30-millisecond agent deadline test reached
timeout before starting the blocking capability during the concurrent CPU-model
run. The complete 32-test agent group passed its isolated recheck. These failures
remain recorded separately from final verification.

The first Q8 full-suite run recorded **1 failed, 1,368 passed, 58 skipped and
15 subtests passed**, again at the unchanged registry directory rename. The
final focused run subsequently passed the complete registry group. No registry
implementation or deadline test was changed to hide these failures.

## Local artifacts and reproduction

Ignored evidence is under `state/test-artifacts/default14b-fix/`:

- `focused.xml` and `registry-recheck.xml`.
- `agent-recheck.xml`, `q8-focused.xml`, and `final-focused.xml`.
- `full.xml` and `full-final.xml` retain separate preliminary full-suite attempts.
- `q8-full.xml` and `final-all.xml` retain separate Q8 regression attempts.
- `native/live-summary.json` retains the first, fixture-mismatched native attempt.
- `native-final/live-summary.json` retains the corrected-fixture FP16 timeout.
- `native-q8/live-summary.json` retains the passing native repair/switch gate.
- `14b-simple-skill/live-summary.json` retains the follow-up unchanged skill audit.
- `chat-only-summary.json` retains the alternate backend's real cache/context check.

Summary files contain fixed case IDs, model IDs, effective limits, sampling,
memory figures, hashes, usage counts and outcome flags. They do not contain
keys, user conversations or user file contents. All temporary model switches
write only the test's isolated selection file. The user's settings and selection
are preserved.

```powershell
runtime/python/python.exe -B -m tests.default_14b_live_validation --root state/test-artifacts/default14b-fix/new-run
```

Restart an already-running O.R.S.I instance to load the repaired profile. Launch
the active `Desktop/orsi_test/ORSI.cmd` checkout.
