# Office MCP phase 3: discovery and live document reads

This bounded change starts from local main `97db799` on
`codex/office-mcp-phase3`. It adds host discovery, live attachment, read-only
adapters and basic connection controls. Default startup remains disconnected.
The accepted v1 contracts, manifests, model profiles, prompts, sampling, routing
and context policy are unchanged. Editing and saving remain later phases.

## User workflow

In **Settings > Models**, choose Cloud mode, then use **Office documents**:

1. **Connect** discovers installed Office and lists open documents locally.
2. Choose a document and click **Use document** to authorize that exact selection,
   including an unsaved document. Changing the dropdown alone grants no authority.
3. Ask ORSI to inspect the selected document. The model can list the selected
   document, attach to its opaque ID and request bounded reads.
4. **Refresh** explicitly rediscovers installations, rebuilds the bridge and
   invalidates old document/session/cursor identities. **Disconnect** releases it.

These controls perform their work on a Qt worker and prevent conversation/model
changes while connection settings are changing. Local mode cannot start a bridge
or execute Office tools. Runtime selection is memory-only; no user settings are
replaced or migrated. Profile revocation cancels and drains the Office worker,
clears local document labels and retains retired views until their workers finish.
The complete lifecycle/Stop/review workflow remains phase 7.

## Local discovery and COM ownership

`office_discovery.py` reads the registered `Excel.Application`, `Word.Application`
and `PowerPoint.Application` CLSIDs under user/machine Classes registrations in
both registry views. App Paths candidates must be absolute, existing files with
the expected executable name. A fixed set of Office 14/15/16 installation folders
is the fallback; no recursive host scan or executable launch is used.

The application-owned discovery cache survives bridge reconnects. Ordinary turns
and document scans reuse it. Explicit Refresh invalidates the cache; a new
application composition starts with a fresh cache. Discovery makes zero model
requests. Registry data, executable paths and the private control responses stay
outside conversation context and diagnostics.

`office_com.py` obtains existing automation objects through GetActiveObject and
Office native window objects. The native-window path reaches other visible
instances, including their unsaved documents. It never creates an Office
application or opens a document. Every COM operation, object comparison and
reference release runs on the dedicated bridge STA in `office_live.py`.

Document IDs identify retained COM objects rather than names or active windows.
Attachment creates a session bound to that object. Each call checks membership in
the application's open-document collection and the current canonical file path.
Closing/replacing a document or saving it under another path invalidates its old
authority. Changing foreground focus cannot redirect a session.

The bridge has a bounded, private local MCP resource channel for configuration,
metadata listing, resource binding and reference release. Those resources are not
advertised as model tools. Only the trusted parent supplies execution authority
metadata. Saved resources still pass ORSI's existing host read policy; a selected
unsaved document requires explicit local selection. No model-provided session ID
or path grants authority. Metadata/results contain no executable or document paths.

Idle disconnect first requests STA reference release, with a two-second bound,
then tears down the owned bridge. Busy or hung calls retain the existing bounded
abort path. The production adapter never calls Office Quit, Close or Save.

## Read targets and limits

| Application | Supported targets and data |
| --- | --- |
| Excel | `selection` or `SheetName!A1:B2`; individual Value2 values and formulas |
| Word | `selection`, `document` or `text:start:end`; bounded text ranges |
| PowerPoint | `selection`, `slides` or `slide:index`; slide/shape identities, text and representable geometry |

Excel targets are single rectangular ranges, capped at 1,000 cells. Whole
rows/columns, external references and disjoint selections are rejected. Reading
does not evaluate a model expression. Word offsets use Office's UTF-16 positions;
Word and PowerPoint pagination preserve surrogate pairs. PowerPoint slide indices
are one-based; returned labels also identify persistent slide and shape IDs.

The existing requested item/character limits and 16,384-byte result cap remain
binding. Pages use at most 32 items and 1,200-character pieces internally, returning
opaque continuation cursors for remaining data. Large Excel strings/formulas use
labeled text fragments instead of pretending a truncated value is complete.

Cursors bind to the session, target and resource identity, retain frozen COM
references/coordinates, and recheck the preceding returned piece before continuing.
Changed or cross-target cursors fail closed. Read snapshots retain target references
and digests in session memory, outside diagnostics. They describe the returned
region, not an atomic revision of the whole document. Future write phases must
add their own coverage, conflict and recovery checks.

There are bounded ceilings of 256 discovered documents and 128 sessions, cursors
and snapshots. Reconnect/Refresh clears them. Unsupported/ambiguous targets,
closed/busy Office objects, remote/URL paths and inaccessible files fail without
redirecting to another document. Protected View, hidden extra instances without
native windows, grouped/embedded objects and unusual Office versions are not
qualified by the current live selection.

## Schemas and verification

The production registry exposes only `office.documents`, `office.attach` and
`office.read`. The actual three-tool Responses projection measures **1,824 UTF-8
bytes / 752 conservative reserve tokens**. The complete accepted eight-tool v1
manifest remains **7,390 bytes / 2,848 reserve tokens**, below its 9,000-byte /
3,500-token ceiling. Local/disabled/unready exposure adds no Office schemas.
These are offline estimates, not billed provider usage.

Verification evidence is under ignored `state/office-mcp-phase3-*`:

- The final essential deterministic/SDK/runtime/UI/profile/startup selection
  passed **111 focused checks in 69.57 seconds**, without failures, errors or
  skips. Its evidence is `state/office-mcp-phase3-qualified.xml`.
- Live Excel/Word checks use two separate instances; PowerPoint uses two
  presentations in its shared application. Synthetic unsaved content, values,
  formulas, one-character Unicode pagination, focus changes and preservation after
  bridge disconnect are checked. The latest live selection passed all three gates
  in 32.28 seconds, without skips (`office-mcp-phase3-native-release.xml`). Caught Windows RPC notifications during fixture
  shutdown remain in the native log and are not labeled clean shutdown diagnostics.
- Runtime pins, native import locations/licenses, relocated runtime operation,
  the accepted-manifest/budget verifier, compilation and whitespace checks pass.
- Two existing popup assertions fail identically with unchanged main Settings
  source in an isolated process; they are recorded as baseline failures and are
  not included in the passing qualification selection. Sandboxed EnumWindows
  failed with error 14007; normal desktop discovery passes.
- Preliminary fixture/import/cleanup failures are retained separately. Two known
  test-owned Excel processes from failed cleanup attempts were released only after
  their exact PIDs and creation times matched the native test reports. This test
  recovery is separate from production bridge process ownership.

No real document contents or credentials were used in the tests. No live provider
requests, billed-token measurement, full-suite run or physical second-host
qualification was performed. Essential focused tests only follow the user's
explicit instruction.

Ref/worktree inventories are preserved in
`state/backups/office-mcp-phase3-20261015/`. Preserve prior main, commit this bounded
change, fast-forward local main and remove only the merged feature branch. Other
worktrees, historical/unmerged tips, private settings and remote refs remain intact.

## Technical references

- [Windows application registration](https://learn.microsoft.com/en-us/windows/win32/shell/app-registration)
- [Office automation and multiple instances](https://learn.microsoft.com/en-us/previous-versions/office/troubleshoot/office-developer/use-visual-c-automate-run-program-instance)
- [Native Office window object models](https://learn.microsoft.com/en-us/previous-versions/ms696137%28v%3Dvs.85%29)
- [Office threading](https://learn.microsoft.com/en-us/visualstudio/vsto/threading-support-in-office?view=visualstudio)
- [pywin32 ObjectFromAddress ownership](https://github.com/mhammond/pywin32/blob/main/com/win32com/src/PythonCOM.cpp)
