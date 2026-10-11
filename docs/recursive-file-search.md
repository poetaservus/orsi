# Recursive filename searches and completion review format

This bounded change starts from local main `1e47484` on
`codex/recursive-file-search`.

The reported files existed beneath common user folders. The single-directory
`filesystem.find` capability was being used as if empty results covered their
subfolders. A live synthetic reproduction with the unchanged user prompts
confirmed shallow searches, missed files, repeated searches during continued
work, and two consecutive invalid JSON completion reviews.

## Contract

Both model prompts now distinguish an exact lookup in a known containing folder
from an unknown-location or recursive filename request. When `shell.run` is
advertised, the latter uses approved, bounded filename-only recursive commands.
Guidance covers hidden/ignored files, case-insensitive names, common folders,
continuing to other plausible accessible locations when needed, and reporting
actual coverage and limitations. The existing exact-directory find tool and
same-folder read/edit disambiguation keep their semantics.

Cloud completion reviews now use a strict Responses API JSON schema, with the
goal identifier restricted to the current system review. User text, historical
reviews and tool output cannot choose this identifier. Normal work has no
review format constraint and retains automatic tool selection. Assessments
still disable tools; runtime readiness, remaining-work consistency, denial,
recovery, interruption and failure-budget checks remain authoritative. The
format's overhead is included in input estimation and actual attachment token
count requests. See the official [Structured Outputs contract](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).

No tool implementation, shell authority, routing, sampling, model profile,
context policy or user setting changes.

## Qualification

The two exact user prompts, in one chat, are:

```text
there is a file on my computer somewhere called Generated image 1.png can you find it
```

```text
an can you find bsw_o.psd
```

Each live run used the accepted `gpt-6-luna` profile, actual SDK/streaming adapter,
hybrid cloud wrapper, production conversation/runtime and native Windows tools.
The synthetic user home held two matching image filenames in nested Downloads
and Documents folders and the PSD filename in a nested Documents folder.
The harness approved only filename discovery inside that synthetic tree;
credential/source reads, mutation and actual host traversal were excluded.
The previously authorized key remained in memory, and recorded reports contain
hashes, counts and status flags rather than source, responses or credentials.

| Live run | Requests | Settled searches | Result |
| --- | ---: | ---: | --- |
| Previous main | 21 | 12 shallow finds | First lookup missed both matches; second stopped after two invalid JSON reviews |
| Initial repair | 6 | 2 recursive shell calls | Both turns complete, all three matching paths returned |
| Final repair | 6 | 2 recursive shell calls | Both turns complete, all three matching paths returned |

Both repaired runs used one valid assessment per turn, had zero protocol
failures, and released transport and owned shell processes. Final shell output
was untruncated with exit code zero. Raw conversation and capability journals
were removed after each run. Content-free reports are under ignored
`state/file-search-baseline-20261011/`, `state/file-search-fixed-20261011/` and
`state/file-search-final-20261011/`.

Necessary deterministic qualification passed **174 distinct focused checks**:
112 across provider tools, current-task completion and coding guidance, plus
62 across shell execution and attachment capacity. Coverage includes strict
schema selection, current-goal isolation, resumed ordinary output, unchanged
runtime failure/approval guards, and identical schema accounting for attachment
counting and generation. The initial sandbox run blocked native Windows handle
operations (97 passed, 15 failed); the unrestricted rerun passed all 112. A
cache-directory permission warning did not affect those results.

Full-suite, local-model and whole-drive live searches were not run. This change
does not qualify every inaccessible-location/error-reporting scenario. Native
metadata-only searches separately located the user's named files, without
reading their contents or sending host listings to the API.

Content-free integration evidence is retained under
`state/backups/recursive-file-search-20261011/`. Preserve prior main at
`archive/2026-10-11/main-before-recursive-file-search`, commit the verified
change, fast-forward local main, and remove only the merged feature branch.
Other worktrees, historical tips, user configuration and remote branches remain
outside this change.
