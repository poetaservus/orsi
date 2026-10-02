# Completion-state preservation, 2 October 2026

Length-ended text was previously logged with its finish reason but returned as an ordinary string,
so the runtime treated it as a completed answer and the UI rendered an unfinished fence as prose.
Truncated tool arguments were decoded and repaired before the output-limit check; otherwise-valid
or repairable partial calls could pass that boundary. A failed context-meter refresh could also
interrupt terminal UI cleanup before controls were released.

## Resulting behavior

- Local server, llama-cpp and cloud conversational responses retain finish reason and input,
  output and total-token usage alongside text. Lazy and hybrid adapters preserve the same value.
- Structured responses retain completion metadata and bounded partial assistant text. Known
  incomplete generation is rejected before native argument decoding/name repair and before
  constrained fallback JSON repair. Raw native tool arguments are never repurposed as assistant
  prose. A call with valid JSON but `finish_reason=length` is still rejected.
- The runtime uses a distinct incomplete terminal status, preserves per-step metadata, and never
  marks length-ended assistant text completed. It does not automatically retry or continue an
  incomplete generation. Cloud output-limit responses stop instead of losing their state through
  failover. Existing failover for other malformed/provider failures is unchanged.
- Conversation history retains partial text and completion metadata. Complete earlier tool
  results stay in the in-memory trace when the final generation is incomplete. Partial final text
  is not replaced by result-grounding output that would imply a completed answer.
- The worker sends the response object to Qt. The chat shows an incomplete notice and token
  metadata, and renders unfinished backtick or tilde fences as code. Code remains read-only and
  copyable; missing content and closing fences are not synthesized.
- Response cleanup releases send/input/session/model controls and stops the thinking indicator
  before refreshing the context meter. Thread completion also restores controls independently.
  Model-switch failure presentation is protected against context-meter exceptions.

Plain-string custom/test adapters remain compatible. Missing provider finish metadata remains
missing; the implementation does not invent a provider stop reason. Complete response formatting,
model profiles, sampling, feature flags, tool visibility and acceptance prompts are unchanged.

## Verification

Deterministic regression cases cover valid, malformed and repairable length-ended native calls;
filtered generation; partial prose mixed with a call; preservation through all three chat adapters
and lazy/hybrid routing; cloud truncation without failover; runtime status and usage history;
defensive checks on custom adapters; constrained fallback rejection before repair; partial replies
after a completed filesystem-stat call; persistent history reload; unfinished fence rendering/copy;
and success/failure UI cleanup with a deliberately failing context meter and model controls present.
Padding cannot bypass the partial-text size limit.

The opt-in real 14B check uses a **test-only 32-token request budget** for an unchanged code prompt
and a tool-generation request. Both actually terminated with `length` and 32 output tokens, retained
usage, and yielded no executable incomplete tool call. It executes no tool and verifies native
server shutdown. The accepted profile configuration is byte-for-byte unchanged. Content-free
evidence is in `state/test-artifacts/completion-state-live.json`; no generated code or tool arguments
are written to that evidence file.

The 32-token live budget was exhausted during reasoning, so both checks had zero visible partial
text. This verifies actual provider termination and the empty-partial path; deterministic fixtures
verify retention and rendering of visible partial code. It does not prove that a full game-generation
task now completes.

```powershell
$env:ORSI_RUN_COMPLETION_STATE = '1'
runtime\python\python.exe -m pytest tests/test_completion_state_live.py --basetemp .pytest-tmp-completion-live -s
```

Final full-suite result: **762 passed, 54 skipped, 5 subtests passed** in 113.78 seconds. The live
completion-state gate passed separately (1 test). Skipped live gates are not claimed as passed.
The final focused run had 184 passes and one journal-persistence failure before the partial-response
assertions; that regression and the short-response notice check passed on recheck (2 tests).

An earlier full run also reproduced `WinError 5` at `os.replace` in the unchanged crash journal
(`app/execution/audit.py`). The final clean run does not resolve that intermittent reliability
problem. Focused/full outputs are retained under ignored `state/test-artifacts/completion-state-*.txt`.
This change does not alter the persistence retry policy or claim that all architectural defects
from the robustness audit are resolved. Source starts from `82d15f284cf784eadf3fda40caca71b51fd55a03`;
the bounded completion-state repair is integrated locally through the normal fast-forward workflow.
