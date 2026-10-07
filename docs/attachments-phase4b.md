# Attachment input: phase 4B cloud capacity

Cloud capacity is bounded by the provider's transport limits, the selected model's accepted
input profile and the account's model/project rate ceilings. There is no small application
file-count cap. Local retains one combined file/image per outgoing message.

## Admission and reply space

Before context admission, the worker counts each source-bearing user message through the
native Responses input-token endpoint. Counts replace file-byte estimates, so a large sparse
PDF is not treated as millions of text tokens. An in-memory, 4,096-entry cache holds only
model/message hashes and numeric counts. The complete user text and immutable reference
metadata bind each hash; model, root and credential changes clear measurements. Reopening
the same root retains valid measurements. Source verification remains independent of the
cache, and altered sources are rejected before provider dispatch. UI counters remain offline.

The complete selected request is counted again immediately before generation, including
the existing policy, reasoning and native tool schemas. Its actual count plus a 256-token
safety margin gates the accepted input ceiling. Attachment requests reserve the smaller of
the profile's output allowance and the fixed account ceiling minus input/margin. Fewer than
32 remaining output tokens stops before generation. Temporary remaining account balances
cause paced waits rather than reducing reply quality. The same fitted allowance is used for
generation and every SDK retry; counting retries also consume request capacity. Quota errors
are permanent and do not trigger repeated count requests.

Only the individual attachment request's output allowance changes. Accepted model profiles,
plain request settings, prompts, sampling, tool behavior/permissions, manual model/skill
selection, runtime step budgets, default mode and local GPU/CPU behavior are unchanged.
Numbered, quoted user-role labels make source order/name visible even when a native parser
does not expose filename metadata. They do not grant instructions inside source files authority.

Metadata-only composer admission rejects invalid aggregate selections before clearing the
message, attachments or manually selected skill. Actual source reading and provider counting
remain cancellable worker work. Existing immutable inline input and stateless replay retain
the phase 4A lifecycle contract; this phase adds no provider upload resources or persisted keys.

## Limits and evidence

The current documented guards remain: each file smaller than 50 MB, combined files at most
50 MB, up to 1,500 images and a 512 MB total JSON payload. Image decoding/pixel guards,
accepted context profiles and account capacity can impose tighter limits. The byte guards
use decimal MB. The complete JSON/body limit includes base64 overhead and tool schemas.
Large byte size does not imply high context use; many pages or detailed images can cost
more tokens than larger sparse files. Maximum image count does not guarantee exhaustive
analysis or perfect source retrieval by every model. Native spreadsheet and non-PDF visual
limitations from phase 4A still apply.

Official source basis:

- [File inputs](https://developers.openai.com/api/docs/guides/file-inputs): individual and combined
  native document bounds and parser limitations.
- [Images and vision](https://developers.openai.com/api/docs/guides/images-vision): image count,
  request-size bounds and model/detail-dependent visual token use.
- [Counting tokens](https://developers.openai.com/api/docs/guides/token-counting): native input counts.
- [Rate limits](https://developers.openai.com/api/docs/guides/rate-limits): model/project ceilings
  and output-allowance sizing. The existing conservative input-plus-output pacing ledger is retained.

## Verification

Synthetic live fixtures are isolated under ignored test state. Numeric-only summaries contain counts/limits and fixed
outcomes; credentials, filenames, source contents and response bodies do not enter baseline
snapshots or those summaries. The user-authorized key is read only from its file's first line
and held in memory. Owned SDK transports close and the session key clears after every live gate.

Initial capacity probes accepted 1,500 native images (46,511 input tokens) and 256 small native
files (1,547 input tokens) at the counting endpoint. The initial complete-model gate read the
49,999,999-byte sparse PDF correctly, using 800 input tokens, but failed ordinal recognition
of a unique middle image among 1,500 and denied seeing a 256-file selection. Both requests
completed with measured source tokens; transport acceptance alone was not labeled semantic
qualification. Numbered source labels address the visibility/order ambiguity. Acceptance
requests and synthetic source contents remain unchanged for the recheck.

The unchanged three capacity requests passed after numbering sources, in **217.446 seconds**
on the default `gpt-6-luna` profile:

| Case | Actual input tokens | Request output allowance | Result |
| --- | ---: | ---: | --- |
| 1,500 images, first/middle/last colors | 97,283 | 102,461 | All three colors correct |
| Sparse PDF, 49,999,999 bytes | 809 | 128,000 | Source code correct |
| 256 text files, 7,680 bytes combined | 7,684 | 128,000 | First/last codes correct |

The account token ceiling was **200,000**. Image generation consumed only ten output tokens;
the dynamic allowance reserves space rather than forcing a longer response. The accepted
profile retains its 128,000-token output setting. These qualify the documented maximum image
count and a document immediately below the individual byte ceiling, plus a large file count.
256 is a tested selection, not an imposed file-count maximum. The complete 512 MB payload
boundary and combined-file overflow guards were checked deterministically, not uploaded at
full size. Other cloud-profile account access and unrelated model qualification remain unrun.

The original phase 4A live gate also passed, in **43.168 seconds**, with unchanged acceptance
requests: seven synthetic sources, scanned-PDF recognition, follow-up/reopened/archive recall
and actual `filesystem.stat` followed by source-aware continuation. All twelve production
tool definitions and the actual 1,050,000 context/128,000 profile reserve were retained.
The four turns used **1,339 / 1,471 / 1,493 / 4,115** input tokens and one actual native tool
call in the restored turn. Owned SDK resources closed and session credentials cleared.

The first deterministic retry test used a fixture SDK client with retries fixed at zero;
the fixture now follows its explicit configuration. A command referencing a nonexistent
test module did not execute tests; the corrected expanded check passed 200 tests in 19.916
seconds. After numbering sources, 67 focused native checks passed in **8.503 seconds**, including
source ordering/quoted names, measured admission, cached-count invalidation, tampering/cancellation,
account boundaries, quota/retry pacing, plain/local behavior and complete composer draft retention.
Compilation, dependency consistency and Git whitespace checks passed. Broader context
compaction/recovery, lifecycle cleanup and final end-to-end work remain phase 5.

Final full native regression passed **2,236 tests and 15 subtests**, with **56 optional skips**,
zero failures/errors, in **258.313 seconds**. The three new capacity gates and the original
cloud gate passed separately under their explicit live opt-ins; other optional gates retain
their previous qualification status. The earlier full run before numbered labels also passed,
with 2,235 tests/15 subtests and 56 skips in 284.823 seconds. User settings, original histories,
credential files, accepted profiles and other active worktrees were untouched.
