# Desktop startup splash verification

Baseline: local main `70d4d28`; bounded branch `codex/splash-launch`.

The splash was only requested when replacing an existing profile window. The
desktop entry point never requested it on a fresh launch, including launches
after choosing to continue without a profile. An isolated launch using the
portable `pythonw.exe` reproduced this before the fix: backend composition began
without any splash window.

The entry point now presents the existing animated, topmost splash after claiming
desktop ownership and before composing the interface. It fades away over the
completed login panel or chat. The initial splash is centered on the available
screen, and the first app window receives the same geometry. Existing unlock and
no-profile transitions retain their window-relative positioning. The bundled
artwork, small pulsing logo and fade timings are unchanged. Secondary launches
continue to activate the existing app without creating another splash or owner.

## Focused verification

26 native Windows cases passed, with no failures, errors or skips (43.98 seconds).
Report: ignored `state/splash-launch-final.xml`.

The five new launch cases run the real desktop entry point under the same
`pythonw.exe` used by `orsi.cmd`, with isolated synthetic profiles and providers.
They check fresh launch without a profile, plain-profile launch, encrypted-profile
login, password unlock, and continuing without a profile. Native window checks
verify that the actual helper is visible and topmost before backend composition,
matches the replacement window's geometry, and exits after the fade. Locked
startup composes no private backend. The launch and unlock splash captures were
visually inspected under ignored `state/splash-launch-preview/`.

Existing focused checks cover continuous logo animation while the parent thread
is blocked, the windowless helper runtime, helper failure fallback, parent pipe
closure, single desktop ownership, locked keyboard unlock, retired-window
activation and repeated unlock clicks. The full suite was not run, as requested.
No live provider, model, physical SSD, minimum-machine or independent security
gates were run. A compiled distribution was not rebuilt.

```powershell
$env:QT_QPA_PLATFORM='windows'
.\runtime\python\python.exe -m pytest tests/test_startup_splash.py tests/test_settings_presentation.py tests/test_desktop_instance.py tests/test_profile_delete_startup.py::test_continue_without_profile_shows_splash_before_building_and_ignores_retired_clicks tests/test_vault_controls.py::test_locked_startup_never_composes_private_consumers_and_keyboard_unlock tests/test_vault_controls.py::test_retired_unlock_window_cannot_reopen_from_activation tests/test_vault_controls.py::test_second_unlock_signal_from_retired_page_cannot_replace_active_profile --basetemp=state/pytest-splash-launch-final -o cache_dir=state/pytest-cache-splash-launch --junitxml=state/splash-launch-final.xml -q
```

## Preservation and integration

Recovery refs, other worktree tips and twelve configuration, state and artwork
fingerprints are under ignored `state/backups/splash-launch-20261010/`. All twelve
entries remained unchanged. The running user app was not stopped, and tests used
only their own synthetic storage. Preserve prior main at
`archive/2026-10-10/main-before-splash-launch`, commit the bounded change,
fast-forward local main, publish main under the user's chat authorization and
remove the merged feature branch. The already-running app must be fully closed
and reopened through `orsi.cmd` to load the changed startup code.
