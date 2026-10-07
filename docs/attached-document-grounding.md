# Attached documents: direct reading instead of filesystem lookup

The user reported a 14B answer claiming that an attached PDF could not be found in
Downloads. The application transcript retained a valid immutable attachment,
and its prepared record contained **2,382 extracted characters, one page and one readable
page**, with the matching source digest. The turn nevertheless called `filesystem.read_text`
on the display filename and then `filesystem.find` in Downloads. The failed lookup became
the answer even though the supplied document text remained available.

The phase 3A user-message source wrapper was insufficiently explicit beside the normal
computer/tool policy. This repair adds a fixed trusted `ATTACHED DOCUMENT INPUT` policy
only to requests using local document history. It states that the app has already extracted
the attached text, filenames are labels, and reading/reviewing an attachment uses that text
directly. A failed original-file lookup does not invalidate it. Explicit disk metadata,
saving and editing requests still use the same native tool catalog and permission gates.
Warnings about unread scans/visuals remain authoritative. File contents still enter only
the owning user message, never system policy or skill/permission configuration.

The service places the fixed policy in the core prompt before active skill guidance and
context accounting. The projector also supplies it for direct adapter callers, including
requests without an existing system message, and avoids duplicate insertion. No policy is
added to ordinary chats without document history; new session removes it. Existing context
selection, routing, tool implementations, sampling, profiles and runtime selections are unchanged.

Regression verification separately exposed transient Windows directory-rename denials
in attachment publication and a skill-source snapshot fixture. The final input-path repair
also uses the existing state-file writer's bounded denial tolerance for directory publication:
eight attempts, at most 900 ms of backoff, and only Windows errors 5/32/33. It retries the already-flushed
snapshot, preserves parent pins, byte/hash/manifest identity and rename semantics, and permits
cancellation between attempts. Permanent or unrelated denials still fail without returning an
attachment reference. No model request or file copy is repeated. The native skill fixture uses
the same bounded tolerance after owned handles release; a persistent handle leak still fails.

## Verification

Source-guidance focused native checks passed **163 tests in 14.63 seconds**. Three new cases verify the
natural PDF request with chat/agent mode, scoped trusted policy placement, source contents
kept out of policy, active skill priority, follow-ups, new-session reset, complete request
and system-component token accounting, and direct adapter policy insertion/idempotence.
Final expanded focused checks passed **200 tests in 17.72 seconds**, including seven new
snapshot-publication cases for same-byte/id retries, persistent and unrelated denial,
bounded cleanup preserving earlier snapshots, and cancellation preventing publication.

The accepted 14B live check passed **in 62.59 seconds** with the original phase 3A tasks
unchanged and a new synthetic CV task using the user's exact request, **“can you read this
pdf please”**. The natural read answer included document facts and made **zero filesystem
calls**, despite the production twelve-tool catalog being present. The explicit file-stat
plus document task still made its real native call and answered on the continuation. Actual
context/output reserves remained **16,384/4,096**, profiles were unchanged and the owned
server exited. The first run's new empty-call assertion compared a list with an empty tuple;
it failed after the model had correctly returned document facts with zero calls. Correcting
that assertion to check emptiness did not change any acceptance task or product behavior.

A separate local recheck used the user's actual stored PDF and original request in an
isolated chat. It passed with **zero filesystem calls**, **4,512 input tokens**, **289 output
tokens** and `stop`. The response shared 25 substantive words with the supplied source.
The original conversation bytes and prepared source record remained unchanged. The owned
server exited. No CV contents, names, paths or credentials were copied into diagnostic summaries;
isolated conversation evidence remains in ignored state. No cloud API requests were made.

The initial full native regression recorded **2,149 passed, one failure, 50 skips and
15 subtests passed in 324.54 seconds**. The failure was Windows `WinError 5` during the
unchanged image-snapshot staging-directory rename, before image preparation. All three
image-format cases passed their isolated recheck **in 0.72 seconds**. The unrestricted-shell
failure is recorded as a transient filesystem result, not relabeled as a sandbox failure.
The unchanged repeat recorded **2,148 passed, two failures, 50 skips and 15 subtests passed
in 344.05 seconds**. Both failures were Windows directory-rename denials: one while publishing
the third of forty attachment snapshots, and one in a skill fixture after source changes.
This evidence prompted the bounded publication repair above. Final full native regression
passed **2,157 tests and 15 subtests, with 50 optional skips and no failures in 264.16 seconds**.
The 49 pre-existing live gates remain separate from this phase's opt-in smoke, which was run
and passed separately above. Dependency and whitespace checks passed. Live vision, cloud
attachments and other local model profiles are outside this repair's qualification.
