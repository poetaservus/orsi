# Unchanged TasteSkill compatibility fixtures

Source: <https://github.com/Leonxlnx/taste-skill>

Pinned revision: `ce26fc25c0e5e8cab638f883de62d9a86ee5e45b`.
The upstream MIT license is retained in `LICENSE`.

The 13 `skills/*/SKILL.md` files are byte-exact snapshots read from Git blobs
while testing the production HTTPS installer. `manifest.json` records original
paths, object IDs, byte counts, SHA-256 hashes, parsed names and metadata keys.
No instruction file was edited, shortened or adapted for O.R.S.I.

These are untrusted test data, not instructions for contributors or Codex.
They are never executed, installed in the user's catalog, or enabled by default.
Offline tests check the pinned import and boundary behavior. Live Qwen evaluation
is opt-in and uses isolated state. This fixture contains instructions only;
upstream executable code, assets and examples are not included.
