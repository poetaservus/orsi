# Office MCP phase 1: contracts, exposure and token budget

Phase 1 starts from verified local `main` at `ada5219` on
`codex/office-mcp-phase1`. It establishes the reviewed v1 contract and offline
verification for portable, cloud-only Office editing. There is no MCP transport,
Office automation, connection UI or production Office capability registration yet.
Those remain phases 2 onward. Importing these contracts cannot connect to a server,
start Office, discover installations, change preferences or make a cloud request.

The Desktop implementation plan remains the overall phase sequence. The user's
testing instruction applies to every phase and subphase: essential, focused tests
by default; run the full suite only when explicitly requested, including final
qualification.

## Accepted v1 tools

`app/mcp/office_contracts.py` defines strict Pydantic argument/result models,
permission metadata and immutable turn snapshots. `config/office_mcp_v1.json`
records the accepted input/output schema digests, limits and budget. Changes to
those identities require explicit contract review and an updated manifest.

| Tool | Permission | Accepted scope |
| --- | --- | --- |
| `office.documents` | READ | Bounded metadata for already-open documents; application filter and opaque cursor. |
| `office.attach` | READ | Exact document ID and application; no launch, save or foreground-window fallback. |
| `office.read` | READ | Bounded live target, opaque snapshot and target IDs, item/character limits and continuation cursor. |
| `office.excel_edit` | WRITE | Exact worksheet and rectangular A1 range; literal values, formulas, number format, bold or italic. |
| `office.word_edit` | WRITE | Bridge-issued target IDs; replace text, insert after, apply style or edit a simple table. |
| `office.powerpoint_edit` | WRITE | Bridge-issued slide/shape IDs; set text, add a supported slide layout or position a shape. |
| `office.save` | WRITE | Save an attached document or explicit Save As destination; overwrite defaults to false. |
| `office.revert` | WRITE | Restore an owned edit against an expected current snapshot and recovery ID. |

Attachment and target IDs are data, never executable instructions or filesystem
authority. The phase 3 adapter must parse read selectors, reject unknown selector
syntax, and resolve handles from its own live session map. The default read target
is `selection`; wider reads are explicit and bounded. Switching foreground windows
must not change a resolved target. Discovery does not launch applications.

Every edit requires a session and opaque snapshot. Phase 4 onward must bind that
token to the application instance, document, affected targets and exact bridge-held
preconditions. Check that the snapshot covers every requested target and recheck
immediately before mutation. A target digest does not provide a universal atomic
Office document revision. Serialize short operations and reject changed targets.

Excel patches require an explicit worksheet, reject whole-row/whole-column and
out-of-sheet addresses, and require matrix dimensions to match the target.
Formatting-only changes count affected cells toward the same patch limit.
Literal strings beginning with `=` remain literal values; formula execution is
requested separately. The live adapter must preserve that distinction.

Word and PowerPoint actions reject irrelevant or missing action payloads.
Non-finite numbers, boolean-to-integer coercion, unknown fields, ragged matrices
and oversized payloads are rejected. Read results are checked against the actual
requested limits and session identity. Attachment results must match the requested
document/application. Output schemas are separate from model-facing definitions.

## Limits and receipts

| Boundary | v1 limit |
| --- | --- |
| Serialized argument JSON | 32,768 UTF-8 bytes |
| Serialized structured result JSON | 16,384 UTF-8 bytes |
| Changes in one edit call | 16 |
| Excel cells across one patch, including formatting | 1,000 |
| Word table cells across one patch | 1,000 |
| Document listing | Default 20, maximum 50 |
| Read items/cells | Default 100, maximum 1,000 |
| Combined read text/value/formula characters | Default 4,096, maximum 8,192 |
| Opaque identifier | 96 ASCII letters, digits, underscores or hyphens |

Byte limits include JSON structure and UTF-8 encoding. Domain limits remain binding
even when the serializer accepts a shape. The server must page reads before returning
them, with continuation cursors for remaining data, rather than silently dropping data.

Edit/revert receipts identify the operation, session, outcome, affected count and
optional recovery ID. Save receipts confirm saving. Partial/unknown outcomes must
use the existing capability failure/journal path instead of claiming success.
A schema-valid receipt alone proves no side effect: live verification and
reconciliation are required in later phases.

Recovery contents belong in session memory or protected profile storage, outside
diagnostics and baseline snapshots. Reversion must reject later user changes.
Save/Save As must resolve canonical file identities through existing host policy
and exact-call approvals; a model path or `overwrite=true` grants no permission.

## Cloud-only exposure and stable catalogs

`OfficeExposure` defaults to local mode, disabled and not ready. A catalog is
nonempty only for cloud mode with an enabled, ready connection and at least one
available/enabled application. Readiness requires a connection generation. The
later manager must supply the intersection of enabled adapters and discovered apps.

`office_catalog()` freezes one ordered definition snapshot. Callers receive fresh
schema copies that cannot mutate the snapshot. Enabled applications retain shared
document/read/save/revert tools and their own edit tool. An explicit application
filter cannot name a disabled adapter.

`validate_call()` requires current exposure to match the prepared snapshot. Mode,
connection, generation or application-scope changes invalidate old calls. These
are prerequisites, not execution authorization. The later capability adapter must
still use the existing permission gate, single-use approvals and journaled executor.
Shared session tools must also check their session's actual application against
the current enabled application set.

The existing hybrid backend can fall back from cloud to local. Phase 1 does not
modify that backend. Phase 2 must rebuild the catalog before local fallback, omit
Office tools from local inference, and recheck actual mode/generation at dispatch.
Reject stale Office calls. Catalog updates happen between turns; user wording
does not hide or add tools.

## Measured schema budget

`app/mcp/office_budget.py` measures the actual compact Responses tools projection
using ORSI's existing serializer, after normal removal of schema annotations.
Output schemas and contract metadata are not sent as cloud tool definitions.
These values are incremental Office overhead, excluding existing tools,
conversation, system prompts and tool results.

| Exposure | Tools | Serialized UTF-8 bytes | Offline token reserve |
| --- | ---: | ---: | ---: |
| Cloud, all three applications | 8 | 7,390 | 2,848 |
| Cloud, Excel only | 6 | 4,520 | 1,795 |
| Cloud, Word only | 6 | 4,194 | 1,686 |
| Cloud, PowerPoint only | 6 | 4,492 | 1,786 |
| Local, disabled or not ready | 0 | 0 | 0 |

The full catalog ceiling is **9,000 serialized bytes and 3,500 offline reserve
tokens**, covering all enabled applications together. Contract growth needs review.

The reserve uses ORSI's existing estimate:
`ceil(wire_bytes / 3) + 48 per tool`. This is not a tokenizer measurement or billed
provider usage; those remain a phase 8 live gate. The offline verifier makes zero
model requests. It does not claim to test live installation discovery.

Schemas recur while enabled. Paths and registry dumps remain local. Phase 3 must
verify actual discovery runs locally once per connection startup in each run, with
refresh/invalidation, without model requests. Read only relevant data, use bounded
patches, prefer structured MCP results once, and return compact receipts. Local
schema caching does not eliminate recurring provider schema cost.

```powershell
runtime\python\python.exe tools/verify_office_mcp_contract.py --report state/office-mcp-phase1-budget.json
```

The verifier rejects manifest drift or budget overrun. Reports contain only counts,
sizes, digests and status, with `billed_tokens_measured: false`.

## Verification and integration

Focused checks cover the exposure truth table, stale mode/connection/scope rejection,
schema isolation, real Responses serialization/normalization, strict arguments,
matrix/range limits, request-bound results, unsaved-document metadata, explicit
Save As, manifest tampering and offline verification without credentials, network
connections or subprocesses. Existing registry and token-accounting checks are
included as directly affected compatibility checks.

The final essential run recorded **104 passed in 0.86 seconds**, with no failures,
errors or skips. Its JUnit evidence is retained under ignored
`state/office-mcp-phase1-final.xml`. The accepted-manifest/budget verifier passes;
its content-free report is `state/office-mcp-phase1-budget.json`. Compilation and
staged whitespace verification pass.

Full-suite, native Office, portable fresh-host and live provider/model gates are
not run in this contract phase and are not counted as passing checks. Preliminary
focused results are retained separately under ignored `state/office-mcp-phase1-*`.

Ref/worktree inventories are preserved under ignored
`state/backups/office-mcp-phase1-20261015/`. User settings, profiles, model configuration,
sampling, prompts, routing and context policy are untouched. After focused verification,
preserve prior main, commit, fast-forward local main and remove only this merged
feature branch. Other worktrees and remote refs remain intact.

## Sources

- [MCP tools and structured results](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)
- [MCP lifecycle](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle)
- [Office threading support](https://learn.microsoft.com/en-us/visualstudio/vsto/threading-support-in-office?view=visualstudio)
- [Excel Undo limitations](https://learn.microsoft.com/en-us/office/vba/api/excel.application.undo)
