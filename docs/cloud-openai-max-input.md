# Maximum cloud input budgets, 4 October 2026

The user requested the maximum supported cloud input allowance while preserving
local mode. The previous cloud input cap of 28,672 tokens could reject a small
follow-up once full file reads and earlier tool history accumulated. The maximum
output update had preserved that input cap rather than expanding it.

The official [Luna model page](https://developers.openai.com/api/docs/models/gpt-6-luna)
and [Sol model page](https://developers.openai.com/api/docs/models/gpt-6.1-sol),
retrieved on 4 October 2026, document a 1,050,000-token context window for each
model. Both accepted cloud profiles now use that complete window. Input gets
the remaining context space after each profile's existing output reserve:

| Cloud profile | Context | Input budget including margin | Output reserve | Maximum estimated input after margin |
| --- | --- | --- | --- | --- |
| GPT-6 Luna | 1,050,000 | 922,000 | 128,000 | 921,744 |
| GPT-6.1 Sol | 1,050,000 | 1,045,904 | 4,096 | 1,045,648 |

The 256-token admission margin is preserved. Input includes system guidance,
conversation history, retained tool arguments/results and the capability schema
catalog; it is not an allowance solely for the latest user message. Existing
conservative offline estimates and final wire-admission checks remain in force.

Only `config/cloud.json` changes application behavior. Local configuration and
limits, output allowances, sampling, prompts, routing, recovery selection, tool
behavior, transcript byte limits and qualification flags remain unchanged.
Restart the normal main launcher to reload these cloud profiles. Saved runtime
selection and conversations are not replaced with test state.

## Verification

All 270 focused checks passed, covering the OpenAI adapter, context admission,
local profiles and mode switching. Real-SDK HTTP fixtures admit previously
oversized synthetic native-tool history for both cloud models without shortening
the retained result. Boundary tests accept input at the configured allowance
minus the safety margin and reject one more estimated token before a network
request. A real Hybrid/Lazy engine mode round trip restores the original local
context and output limits and releases each owned fixture backend.

Two isolated live Luna requests completed with 45,452 and 45,468 input tokens,
each exceeding the former 28,672-token cap. Both generated five output tokens
with the unchanged 128,000-token wire allowance. A real Qt selector switched to
Sol and back to Luna, verifying both 1,050,000-token effective contexts and each
input/output allocation while preserving the synthetic conversation. The owned
SDK client, request thread and in-memory key were released; no local model
process was created.

These live checks verify expanded input admission and a real continuation, not
a full-million-token live test or successful qualification. Sol requests remain
blocked by the previously recorded account permission issue; selecting its
profile in the UI is not a live Sol qualification. Content-free reports are
retained under ignored `state/test-artifacts/cloud-max-input/`.

The full Windows regression passed 1,709 tests and 15 subtests, with 49 existing
skips and no failures. Skipped live/local-model/host gates remain skips; earlier
qualification failures are not relabeled as passes.

## Integration and recovery

The bounded branch `codex/cloud-max-input` starts from local main `35eb8eb`.
Configuration copies, ref/worktree maps and a verified all-ref recovery bundle
were preserved under ignored `state/backups/cloud-max-input-20261004/` before
edits. After verification the change is committed, local main fast-forwards and
the merged local branch is removed. Other active checkouts and their independent
state remain untouched.
