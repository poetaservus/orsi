# Skills in Settings

This follow-up was verified on `codex/message-skill-picker`, after picker
revision `e3467f9`, and committed as `9d41df3`. On 4 October 2026, the user
explicitly approved merging it into main and pushing to GitHub. The previous
local main is `9afeaf5`; see [the integration record](git-workflow.md).
The workflow below includes Phase 2 package imports added on 5 October 2026;
see [package installation and its verification](skill-package-install-v1.md).

## User workflow

1. Open Settings, then **Manage skills…**.
2. Paste a public GitHub repository link for complete packages, or a `SKILL.md`
   file/Raw link for instructions alone. File links ending in `?plain=1` remain
   supported. Alternatively, choose/drop a local skill folder or `.md` file.
3. Click **Preview** to check names, descriptions, source, reference count and
   total content size. Multiple packages are listed before publication. Pressing
   Enter in the source field previews; it does not install.
4. Click **Install**, then **Done**. The skill is immediately available in the
   existing `/skill` chooser, without restarting the app. Choosing it still
   attaches it to one outgoing message.

There are no installation or management options in the message input. All
management controls are in Settings. The installed list shows names, with
descriptions on hover. Select a global skill and click **Remove…**, then confirm,
to remove it. Removing a selected draft skill clears that chip and preserves the
prompt text. Project-discovered overrides are listed but cannot be removed here.

Importing a single Markdown file replaces the manual staging-folder step.
The file must contain valid skill frontmatter, including a name and description.
Installation copies its exact reviewed bytes as `SKILL.md`. Matching existing
content is a no-op; an existing name with different content must be explicitly
removed before reinstalling. This dialog does not overwrite installed skills.

Choosing a folder/repository preserves bounded `references/**/*.md` content
alongside the entry point. The preview captures all installed bytes; changing the
source afterward does not change what Install publishes. Reference-only changes
also count as conflicting content. Removal checks the generated ownership
inventory and preserves unknown or edited installed files rather than deleting
them. Legacy single-file skills remain supported without new metadata.

This version accepts public GitHub repository and skill-file links, rather than
marketplace, private or arbitrary web links. For a marketplace skill, use its
public GitHub `SKILL.md` source or a downloaded Markdown file. Existing CLI
installation from local folders and public Git repositories remains available.
CLI changes still require an application restart to refresh its startup catalog.

Imports remain Markdown guidance. Scripts, dependencies and assets are not
imported or executed. With tools enabled, selected skills now provide a compact
reference inventory and the scoped `skill.read_reference` tool. Supporting text
loads on demand and counts toward the existing context budget. If references
are unavailable, the model is instructed to request their content or a skill
refresh. See [conversation integration](skill-reference-conversations-v1.md).
Claude-specific metadata does not create runtime behavior or compatibility.
Model profiles, sampling, skill selection, host permissions and write approvals
are unchanged.

## Implementation boundary

`SkillSettingsDialog` is opened by one Settings button. Preview, installation and
removal each run on an owned, one-shot Qt thread. The dialog joins a completed
worker before releasing it or closing; controls are disabled while it works.
The rest of the UI remains responsive during a network preview. Closing or
pressing Escape cannot destroy a running worker.

For single-file import, the source adapter accepts HTTPS GitHub file/raw URLs and downloads from
`raw.githubusercontent.com`, without redirects, proxies or credentials. It caps
downloads at the existing skill byte limit (at most 1 MiB), uses a 10-second IO
timeout and a 30-second elapsed check between bounded reads, and rejects HTML.
Failures report safe messages without logging response bodies. Local files use
the existing native snapshot reader and path safeguards.

Repository previews use the existing owned bare-Git inspection without checkout,
and snapshot one default-branch commit. Git processes and temporary objects are
released before showing the preview. Install publishes that snapshot without
another network request. A Git executable on PATH is required for this mode.

Preview parses a captured byte snapshot. Install reparses and verifies that
snapshot, then uses the same immutable package transaction as the existing Git
installer. It does not fetch or reread the source during publication. Existing
staging, conflict, rollback, removal and registry-refresh safeguards are reused.
Conversation-service entry methods serialize catalog mutations with the existing
turn lock and reject changes while a response runs or after shutdown. Settings
management is disabled while responding. Metadata labels are plain text and
bounded; tooltips escape HTML. No additional inference request is made by import.

## Original single-file Settings verification

The focused regression passed **339 tests and five subtests**. After the final
preview layout adjustment, all **43 new tests** passed again. These cover URL
restrictions, bounded downloads, response release, malformed inputs, immutable
reviewed bytes, conflict preservation, busy/closed service rejection, project
override protection, actual Qt worker completion, keyboard preview, local drops,
immediate chooser refresh and confirmed removal. Native Windows checks used an
unrestricted shell and repository-local temporary directories.

An earlier focused run encountered a Windows access-denied directory rename in
the unchanged registry handle test. Its isolated recheck passed, and the final
339-test focused run passed. An initial Qt worker lifecycle problem was found
during testing and corrected to a one-shot worker before these passing runs.

The first full regression recorded **1,478 passed, one failed, one teardown
error, 58 skipped and 15 subtests passed** in 207.03 seconds. The failure and
teardown error came from the same unchanged Git installer descendant-process
fixture's temporary-directory cleanup. Its complete **60-test** module passed
the unrestricted recheck in 19.94 seconds. No Git cleanup implementation or
acceptance prompt was changed to bypass that failure.

The final full regression recheck passed **1,479 tests and 15 subtests**, with
**58 existing skips**, in 215.77 seconds. Dependency consistency and authored
file whitespace checks passed. The earlier cleanup failure remains recorded
above; it is not counted as a pass in that first run.

Two isolated native Qt audits exercised real public sources for
`frontend-design` and `handoff`, including the user's `?plain=1` link. Preview,
installation, identical-content reinstallation and immediate chooser refresh
passed. Both audits made zero model requests, preserved the model profile bytes
and released their workers. Screenshots were visually reviewed; the final
preview fits its description, source, list, status and buttons without clipping.
These audits used isolated skill storage, leaving the user's installed skills
untouched. They are not live model qualification tests.

Content-free summaries, screenshots and test reports are local ignored artifacts
under `state/test-artifacts/skill-settings/`. The final visual audit is in
`live-ui/64e20f9b9b92403ea4d6aea272bb8575/`. The suite's 58 existing skips cover
seven host-dependent symbolic-link checks and 51 opt-in live model, cloud or UI
gates; skipped gates are not counted as passes.

Reproduction:

```text
runtime/python/python.exe -B -m pytest tests/test_skill_import_source.py tests/test_skill_settings_ui.py -p no:cacheprovider --basetemp=.pytest-tmp-skill-settings-new --junitxml=state/test-artifacts/skill-settings/new.xml
runtime/python/python.exe -B -m pytest -p no:cacheprovider --basetemp=.pytest-tmp-skill-settings-full-recheck --junitxml=state/test-artifacts/skill-settings/full-recheck.xml
```
