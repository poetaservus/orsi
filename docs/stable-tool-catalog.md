# Stable tool catalog

The screenshot workflow exposed a visibility defect, independently of model quality:
`confirmed`, `you're authorized to do it`, and `list me the tools you have` could
receive only `filesystem.stat` and `filesystem.list`. The system prompt then told
the model that it had exactly two read-only capabilities. Previously executed tools
were added back from history, making capability availability differ between sessions.

ConversationService now resolves every agent turn from the enabled runtime registry.
The same ordered catalog supplies the system prompt, provider schemas and runtime
validation. User wording and previous calls do not change availability. Disabled
tools stay absent. Context recovery controls context management, independently of
tool reachability.

This adopts OpenCode's registry/permission separation, not its entire implementation:

- [Tool registry](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/tool/registry.ts)
- [Session tool resolution and execution permissions](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/session/tools.ts)
- [Permission configuration](https://opencode.ai/docs/permissions/)

Concrete operations still pass schema validation, host policy, permission decisions,
operation approval, execution journaling and bounded runtime recovery. A conversational
confirmation does not grant blanket authorization. No pending mutation is replayed on
restart. The change leaves model profiles, sampling, prompts, context recovery and
startup archiving unchanged.

Regression coverage includes the exact confirmation phrases, all enabled/disabled
catalogs, sequential approved operations, denied/cancelled operations with original
fixture bytes preserved, a task after cancellation and startup-style session rotation.
Existing filesystem tests now assert that metadata requests retain enabled write
tools while performing no write. Both context-recovery settings use the same catalog.

Advertising the full catalog increases schema tokens. Real-model correctness and
continuous-session cost must be measured separately from deterministic tests.
The user explicitly approved integration into `main` on 3 October 2026 after reviewing
the repair and native Windows styling. This is user-approved integration, not successful
qualification of every model. Neither skipped live gates nor a green unit suite establish
qualification. See [the integration record](git-workflow.md) for measured results.
Live diagnostics remain under ignored `state/`, bound to the tested revision, effective
flags and model profile.
