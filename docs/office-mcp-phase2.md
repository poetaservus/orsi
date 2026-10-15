# Office MCP phase 2: portable connection and execution foundation

Phase 2 starts from verified local `main` at `1c2354e` on
`codex/office-mcp-phase2`. It implements the portable MCP runtime, persistent local
connection and opt-in ORSI capability integration. The phase 1 schemas, manifest
and token ceilings are unchanged.

Default application startup remains disconnected. There is no live Office
discovery, COM document attachment, Office editing handler or connection UI yet.
The bundled server lists the reviewed contracts and reports live operations as
unavailable. Phase 3 supplies discovery, attachment, read adapters and the trusted
host resource policy; phases 4-6 add actual editing. Phase 7 completes UI lifecycle
controls and phase 8 qualifies full portable nodes on another physical host.

## Portable runtime

`requirements-mcp.txt` pins MCP 2.3.0, mcp-types 2.3.0, pywin32 312 and the reviewed
additional runtime dependencies. The SDK is included in `pyproject.toml`; Windows
automation is in its Windows extra. `requirements.txt` includes the pinned additions.
Existing OpenAI SDK, model, sampling and context configuration remain unchanged.
The additions use httpx2/httpcore2 alongside the existing provider HTTP libraries.

Dependencies are installed inside `runtime/python`, with their distribution
licenses preserved. There is no system Python/Node installation, Windows service
or pywin32 global post-install step. The existing runtime already had pywin32 312.
The runtime builder now runs `tools/verify_mcp_runtime.py`, which checks the pins,
actual license files and application-local MCP/COM module locations without
starting Office or requesting a provider.

The node payload includes `requirements-mcp.txt`, the accepted Office manifest
and the runtime verification helper. Its existing runtime copy carries the SDK,
native DLLs and licenses. New connections resolve the bundled Python executable
relative to the node root; no source-host executable path is exported.

## Connection lifecycle and protocol

`app/mcp/office_connection.py` owns one persistent SDK client on a dedicated
async worker thread. `connect()` is an explicit worker operation, allowed only in
cloud mode. Construction and imports perform no connection, discovery or launch.
The application/discovery intersection defaults empty, so the phase 2 shell
cannot expose Office tools to an ordinary user session.

Initialization validates the bundled accepted manifest and byte/token budget,
then checks the server identity/version and every accepted input/output schema.
Tool lists are cached per connection; pagination is bounded to four pages with
duplicate/cyclic cursor rejection. Extra, duplicate, missing or changed tools fail
the connection. Model definitions use the local reviewed contracts, not server
instructions, descriptions, annotations or unreviewed tools.

The SDK uses its `legacy` initialization mode, which was verified with the
bundled SDK/server. The standard stdio transport is provided by
`app/mcp/stdio_transport.py` using ORSI's existing atomic Windows job ownership.
`start_owned_process` now accepts an optional stdin descriptor, preserving existing
callers. Only explicit pipe handles are inherited; the child is hidden and all
owned descendants release on cleanup. There is no PID-based process killing and
no listening network port.

Frames are capped at 65,536 bytes. Invalid JSON, duplicate fields, non-finite JSON
constants, oversized or incomplete frames close the connection. Pipe work is
off-thread and is not abandoned onto file descriptors a reconnect could reuse.
The owner releases the process before SDK teardown waits for its reader tasks.
Stderr is discarded and raw SDK exceptions are not retained in diagnostics.

The bridge inherits a bounded Windows environment, excludes credentials and
Python path overrides, and uses `state/mcp/tmp` for temporary files. Model data
cannot select the process command or module. Internal test fixtures inject their
own trusted transport factory; that is not a user/model server-registration API.

Initialization and calls have separate deadlines, each capped at 30 seconds;
defaults are 10 seconds. SDK calls are serialized. Shutdown joins the worker with
a six-second bound and releases owned processes. Opaque handles and document maps
are in memory and cleared on disconnection. Explicit reconnect creates a new
generation. A 512-call replay record ceiling requires explicit reconnect rather
than evicting old call identities or replaying work.

Structured MCP results are validated against the reviewed result contract and
the actual request, then forwarded once. Duplicate text representations, resource
links and media blocks are not added to model context. Write receipts must name
the exact ORSI operation ID passed as MCP request metadata; this metadata adds
no model-facing schema fields.

## Capability, permission and recovery boundaries

`build_agent_runtime()` accepts optional `office_connection` and
`office_resource_policy` arguments for trusted application composition. Without
them, current startup behavior and built-in catalogs are unchanged. The connection
must belong to the same portable application root.

`OfficeCapabilityRegistry` preserves built-ins and skill extensions and exposes
Office definitions only for an eligible connection, actual cloud model mode and
an installed trusted host resource policy. The agent freezes its usual turn
definitions. Mode, generation, session or target changes are checked again before
dispatch. User wording does not select or hide tools.

The host policy callback produces a canonical resource, live identity and bounded
approval preview. Its absence denies execution. Saved documents are checked through
the existing host read policy or the common protected-path write policy; Save As
must match its exact destination. A None resource is reserved for explicitly
authorized unsaved documents or metadata. Phase 3 must resolve real COM identities,
document paths and snapshot scope; a model session ID grants no file authority.

Default Office read rules allow only after those host checks; mutations use ASK.
Existing explicit DENY rules retain precedence, and the existing approval ON/OFF
preference remains authoritative. Bindings hash exact arguments, exposure and live
resource identity. A changed approved target is rejected before sending a tool call.
Capability execution uses the existing cooperative executor and content-free crash
journal. Shutdown clears prepared bindings and closes the shared connection.

Cancelled requests that never dispatch do not reach the bridge. Once a write may
have been sent, cancellation, timeout, disconnection, server error or an invalid
receipt becomes `OUTCOME_UNKNOWN`. Existing journaling blocks later writes until
the user reviews the uncertain outcome. There is no automatic retry. This cannot
promise rollback or interruption of a future external Office COM operation.

Office-enabled native tool requests retain cloud errors instead of automatically
falling back to a local model. Constrained text recovery uses the dedicated
`respond_cloud_only` route too. Stale Office catalogs are rejected in local mode.
Ordinary non-Office provider selection/fallback and existing recovery prompts are
unchanged.

## Essential verification

The final unrestricted Windows selection recorded **105 passed in 41.16 seconds**,
with no failures, errors or skips. Evidence is retained under ignored
`state/office-mcp-phase2-qualified.xml`.

The selection covers real SDK/stdio initialization and persistent synthetic calls,
schema rejection, frame bounds, exact approvals and denial, replay prevention,
changed identities, missing host authority, protected destinations, cancellation,
timeouts, malformed results, disconnect/reconnect, stale handles, cloud-only native
and constrained recovery, journal privacy and unknown-outcome review. Selected
existing ownership checks include descendant cleanup; selected ordinary cloud
fallback, schema-accounting and fresh-node export checks also pass.

A copied minimal runtime under a different path containing spaces imports MCP and
native COM DLLs locally and starts the bundled server. The fixture carries existing
application/provider import dependencies, excluding GUI, GPU and model assets.
This is a relocation check on the current PC, not a physical second-host or full
GUI/node qualification.

The runtime pin/license/import verifier, `pip check`, compilation, portable-builder
PowerShell syntax and staged whitespace verification pass. Reports are
`state/office-mcp-phase2-runtime.json` and `state/office-mcp-phase2-budget.json`.

The eight-tool model schema remains **7,390 UTF-8 bytes / 2,848 conservative reserve
tokens**, below **9,000 bytes / 3,500 reserve tokens**. Local, disabled, unready or
host-policy-less exposure adds no Office schemas. These are offline reserve
estimates, not billed provider usage. SDK handshake/tool-list traffic is local and
does not require model requests.

Early failures are preserved separately: the SDK initialization mode name, fixture
metadata shape, startup/call deadline separation, test journal accessor, host-policy
method integration, missing relocation fixture import dependencies and a missing
test directory. One selected deployment-test collection encountered the existing
import cycle in unchanged personality/conversation modules; including the directly
affected schema-accounting compatibility test initializes the normal application
import path. No unrelated product import behavior or acceptance prompt was changed
to make that collection pass.

Per user instruction, the full suite was not run. Live Office operations, real
provider/model billing, physical fresh-host behavior, complete GUI and profile-lock
qualification remain separate later gates. No keys or real document contents were
read or recorded. Test providers and document values were synthetic.

Ref/worktree inventories are under ignored
`state/backups/office-mcp-phase2-20261015/`. Preserve prior main, commit the bounded
change, fast-forward local main and remove only the merged feature branch. Other
worktrees, private settings, historical/unmerged tips and remote refs remain intact.

## Sources

- [Official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [SDK transports and custom transport interface](https://py.sdk.modelcontextprotocol.io/client/transports/)
- [MCP stdio transport](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
- [pywin32](https://github.com/mhammond/pywin32)
