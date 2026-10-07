# 70 — Untrusted input, privacy and data integrity

Read when code accepts external data, invokes processes, stores information or
uses credentials. Apply controls proportionate to the actual trust boundary.

## Define trust and limits

Identify input origin, permitted effects and existing authorization boundaries.
Validate schema, lengths and numeric ranges before expensive work. Bound file
sizes, request bodies, archive expansion, buffered results and decompression.
Do not assume a filename extension or a type annotation validates content.

Avoid `eval`/`exec` for untrusted strings and `pickle` for untrusted data. Prefer
an explicit data format with validation; use a safe YAML loader for YAML data.
A JSON parser alone does not enforce the application's business contract.

## Paths and process execution

Use argument lists for subprocess calls and `shell=False` for ordinary commands.
Do not splice external data into a shell command. Verify the executable, working
directory, timeout, return code and output size. Do not assume a killed parent
also settled its children; process ownership and platform behavior matter.

For a storage root, normalize and validate containment deliberately. Lexical
prefix checks are unsafe (`root-other` is not `root`). `resolve()` can follow
symlinks and a later check can race a filesystem change. If an attacker can alter
the tree, use platform-appropriate anchored/handle-based operations or an existing
safe abstraction. Do not claim `pathlib` makes redirect races safe.

Check archive members and extraction destinations; prohibit traversal/redirects
outside the allowed area. Define collision/overwrite policy before copying,
moving or deleting. Never recursively delete a computed target before establishing
its exact identity and allowed boundary.

## Secrets and diagnostics

Load credentials through the existing configuration/secret mechanism. Never place
real secrets in source, examples, fixtures, filenames, exception messages or
logs. Do not print a whole environment or connection string to diagnose a failure.
Redact by construction: allowlist useful diagnostic fields rather than trusting
blacklist scrubbing after serialization.

Useful fields include operation name, bounded IDs, counts, duration, attempt,
status and error class. User/file/conversation content is not ordinary telemetry.
Metrics need bounded labels; avoid unbounded identifiers as label values. Configure
logging at application startup, not in every reusable module.

## Network and database boundaries

Use parameterized database operations; do not construct SQL from untrusted input.
Keep validation separate from authorization. Map errors to public responses without
exposing implementation or credentials. If the application fetches user-provided
URLs, consider SSRF according to its deployment: scheme/host restrictions, private
addresses, redirects and DNS changes can matter. Do not invent a generic URL
filter and claim complete protection.

Use TLS verification with appropriate trust configuration. Distinguish connect,
read and operation deadlines. If requests cause mutations, establish idempotency
and audit outcomes before retrying. A timeout is not evidence that the other
service did nothing.

## Safe persistence and updates

Use a transaction for changes that must commit together. For files, serialize and
validate before replacement and define locking, permissions and crash recovery.
Preserve an accepted older value if validation or replacement fails. Schema
migrations require a backup/recovery story and compatibility tests.

Document what sensitive data is retained, for how long and where it is exposed
when the task involves that behavior. Avoid adding encryption, accounts or a
security framework unrelated to the requested feature.

Official reference: [Python pickle warning](https://docs.python.org/3/library/pickle.html).
For cleanup and retry semantics read [30](30-errors-and-resources.md); for failure
evidence read [40](40-testing.md).
