# OpenCode harness analysis

## Reference boundary

This analysis is pinned to OpenCode commit
[`1f94d8a3c86b67f4f49a0e341de74e9188381b3a`](https://github.com/anomalyco/opencode/commit/1f94d8a3c86b67f4f49a0e341de74e9188381b3a),
recorded on 2026-08-12. OpenCode is a reference implementation, not a dependency or a source to copy.

The relevant upstream files are:

- [`tool/tool.ts`](https://github.com/anomalyco/opencode/blob/1f94d8a3c86b67f4f49a0e341de74e9188381b3a/packages/opencode/src/tool/tool.ts)
- [`tool/registry.ts`](https://github.com/anomalyco/opencode/blob/1f94d8a3c86b67f4f49a0e341de74e9188381b3a/packages/opencode/src/tool/registry.ts)
- [`session/prompt.ts`](https://github.com/anomalyco/opencode/blob/1f94d8a3c86b67f4f49a0e341de74e9188381b3a/packages/opencode/src/session/prompt.ts)
- [`session/processor.ts`](https://github.com/anomalyco/opencode/blob/1f94d8a3c86b67f4f49a0e341de74e9188381b3a/packages/opencode/src/session/processor.ts)
- [`permission/index.ts`](https://github.com/anomalyco/opencode/blob/1f94d8a3c86b67f4f49a0e341de74e9188381b3a/packages/opencode/src/permission/index.ts)
- [`tool/shell.ts`](https://github.com/anomalyco/opencode/blob/1f94d8a3c86b67f4f49a0e341de74e9188381b3a/packages/opencode/src/tool/shell.ts)
- [`tool/read.ts`](https://github.com/anomalyco/opencode/blob/1f94d8a3c86b67f4f49a0e341de74e9188381b3a/packages/opencode/src/tool/read.ts)
- [`tool/truncate.ts`](https://github.com/anomalyco/opencode/blob/1f94d8a3c86b67f4f49a0e341de74e9188381b3a/packages/opencode/src/tool/truncate.ts)

## Reliability patterns to adapt

### Typed capability boundary

OpenCode gives every tool an ID, description, parameter schema, execution method, and normalized
result. Its wrapper validates unknown model input before the implementation runs. O.R.S.I should
adopt the same boundary with Pydantic models and stable error codes. Invalid arguments must become
a result the model can correct, not an exception that escapes into the UI.

### Central catalog

OpenCode builds the model-visible catalog centrally and keeps tool construction out of the agent
loop. O.R.S.I should similarly separate internal registration, permission-based visibility, and
provider-specific schema conversion. Initially, only one production capability will be enabled at
a time.

### Explicit lifecycle state

OpenCode represents calls as durable parts and moves them through pending, running, completed, and
error states. O.R.S.I should persist a call before execution, give it a stable ID, and persist every
transition atomically. Startup recovery must mark interrupted work; it must never replay a
state-changing call automatically.

### Model/execution separation

The model requests a structured call. Trusted runtime code validates permissions and performs the
operation. The result is inserted into the conversation before the model chooses another step.
O.R.S.I must not infer successful execution from assistant prose.

### Process lifecycle and bounded output

OpenCode's shell implementation races normal exit, cancellation, and timeout; kills a process that
loses that race; retains a bounded preview; and spills oversized output to a file. O.R.S.I should
adapt those mechanics in a dedicated Windows-first process runner. Every capability—not only the
shell—will also receive an outer executor deadline.

### Permission rules

OpenCode evaluates allow, ask, and deny rules and lets capabilities request authorization through
their execution context. O.R.S.I should use explicit READ, WRITE, EXECUTE, and SYSTEM classes, with
the runtime owning approval state. Approval must have a deadline and must resolve on cancellation
or UI shutdown so it cannot leave a session stuck.

## Patterns not to copy

- OpenCode's Effect/TypeScript dependency graph; O.R.S.I needs a small explicit Python design.
- Dynamic plugins, MCP, subagents, or parallel calls in the first implementation.
- A local HTTP server or daemon.
- Broad command-string parsing before `process.run` is proven reliable.
- Automatic replay of interrupted calls.
- Provider-specific workarounds mixed into core execution state.
- Permission waits without a bounded lifetime.

## Initial conclusion

The first implementation work is infrastructure, not a large capability catalog. After contracts,
registry, executor, session transitions, provider-native calls, and a bounded loop are tested, the
first real capability will be `filesystem.stat`. Nothing else will be advertised until that path is
reliable end to end.
