# OpenCode tool-resolution port

## Existing O.R.S.I. flow before this change

`ConversationService` currently decides whether a request is a computer task with a large set of
English/Hungarian phrase checks and regular expressions. It then narrows the capability catalog,
and in several cases constructs required calls itself. The existing lower layers are already much
stronger: `CapabilityRegistry` exports strict Pydantic schemas, the inference adapters use native
tool calls, `AgentRuntime` validates and loops over results, and permissions, approvals, execution,
and crash journaling are deterministic application code.

The unreliable part is therefore the semantic pre-router, not the registry or executor. Phrases
outside its hand-written vocabulary can stay on the chat-only path and never reach the model with
tools.

## OpenCode flow being ported

The reference implementation is OpenCode at commit
`d870e22c70f27103016dcd479edcfebf86136d93` from
<https://github.com/anomalyco/opencode>. Its relevant flow is:

1. Build one model-visible tool catalog from the central registry.
2. Give the catalog's descriptions and JSON schemas to the model.
3. Accept native structured calls as the primary selection mechanism.
4. Normalize only safe identifier/JSON mistakes and validate arguments against the tool schema.
5. Turn invalid calls into bounded feedback so the model can correct them.
6. Apply trusted permission rules and approval outside the model.
7. Execute the tool, append the structured result, and continue the bounded model loop.

Relevant upstream files are `packages/opencode/src/session/tools.ts`, `session/llm.ts`,
`session/llm/request.ts`, `session/llm/native-request.ts`, `session/llm/native-runtime.ts`,
`session/processor.ts`, `session/prompt.ts`, `tool/registry.ts`, `tool/tool.ts`,
`tool/json-schema.ts`, `tool/invalid.ts`, `provider/transform.ts`, and `permission/index.ts`.

## O.R.S.I. target flow

```text
user request
  -> LLM with the complete enabled registry catalog
  -> native structured capability call
  -> bounded deterministic name/JSON repair
  -> Pydantic schema validation
  -> deterministic permission and approval gate
  -> journaled execution
  -> structured result returned to the LLM
  -> bounded continuation
```

If the selected backend explicitly cannot produce native calls, O.R.S.I. makes a separate
constrained request for exactly one JSON decision. That output is parsed only as a complete JSON
object, resolved against the same registry, and validated through the same trusted path. Assistant
prose is never scanned for tool-shaped text. No fallback may self-authorize or bypass permissions.

The previous regex resolver remains temporarily as unreachable compatibility code so this port can
be small and avoid disturbing accepted filesystem helpers. It is no longer the main routing path
and can be deleted after its focused legacy tests are retired.
