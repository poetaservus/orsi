# Application logo and shortcuts

The user's corrected 256 × 256 transparent `bsw_o.png` is bundled byte-for-byte at
`app/ui/assets/bsw_o.png`. The supplied source is not altered. The derived
`orsi.ico` contains 16, 20, 24, 32, 40, 48, 64, 128 and 256 pixel frames with
transparent backgrounds, centered artwork and preserved proportions. Rebuild
it with `runtime/python/python.exe tools/build_app_icon.py`; the tool uses the
existing Qt image library and requires no new dependencies.

`app/ui/branding.py` supplies the shared icon for the application, main window,
loading windows and Qt tray fallback. Native Windows tray notifications load
the same ICO and use it for balloons. The native handle is owned, retained
through Explorer tray recreation and destroyed exactly once after tray removal.
Missing artwork falls back to the shared Windows icon without disabling alerts
or destroying a system-owned handle. Notification timing, quiet-time behavior,
sound suppression, click actions and settings are unchanged.

Windows processes and shortcuts share `ORSI.Desktop` as their AppUserModelID,
set before UI presentation. See Microsoft's
[process identity guidance](https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nf-shobjidl_core-setcurrentprocessexplicitappusermodelid),
[application shortcut identity guidance](https://learn.microsoft.com/en-us/windows/win32/shell/appids)
and [native icon ownership rules](https://learn.microsoft.com/en-us/windows/win32/menurc/using-icons).

Run **Create shortcut.cmd** from the application folder to create or refresh
an **O.R.S.I** desktop shortcut with this icon. It launches the bundled
`pythonw.exe -m app.launcher` without a console and uses the application folder
as its working directory. The quiet entrypoint preserves arguments and adds
the same local NVIDIA library path as `ORSI.cmd` before calling the existing
desktop entrypoint. It does not change model configuration or routing.

The helper preserves custom options on matching shortcuts and avoids replacing
a shortcut for another installation or application. It prepares a temporary
link, commits the icon and AppUserModelID, then publishes it. A matching legacy
shortcut to this folder's `ORSI.cmd` can also receive the new icon while keeping
its existing launch options. A host shortcut is not portable: after moving a
node, run **Create shortcut.cmd** again from its new location. Both deployment
and pilot packaging include the ICO and shortcut creator; generated `.lnk`
files and host paths are not copied into new portable nodes.

## Focused verification, 10 October 2026

`codex/app-logo-icon` starts from local main `8295169`. **27 distinct focused
checks passed** on native Qt 6.12.0, using repository-local `--basetemp`. Checks
cover decoding every icon size and transparency, application/window/loading
identity, actual Windows taskbar identity, actual native ICO loading and owned
versus shared handle cleanup, existing notification behavior, quiet-launch
environment and argument preservation, real shell-link creation/AppUserModelID
and custom-option preservation, unrelated-shortcut preservation, and ICO/helper
inclusion in both node and pilot payloads. Latest distinct results are in
`state/app-logo-icon-final-results.xml`; raw runs remain under
`state/app-logo-icon-*.xml` and matching logs.

The first run found a shortcut property initializer that is an inline Windows
helper rather than a callable DLL export, plus a pre-existing notification test
whose broad DLL substitute intercepted native window construction. The shortcut
now constructs the string PROPVARIANT directly, and the test constructs its
window before substituting notification DLLs. Both affected paths passed on
recheck; the final quiet shortcut paths also passed.

Updated application files were applied to the previously owned relocated cloud
node. Its real quiet entrypoint displayed the shared logo, unlocked the
synthetic profile, retained stored data and connections, blocked deployment,
and released helpers, keys and leases. Source preservation passed and network
attempts remained zero. This was an application update check, not a new whole
package checksum qualification. Result: `state/app-logo-icon-native-result.json`.
The icon size preview `state/app-icon-preview.png` was visually inspected.

A new `C:/Users/yaboy/Desktop/O.R.S.I.lnk` was created, with its icon, working
directory, quiet entrypoint and AppUserModelID verified. Existing desktop links
were preserved before creation; metadata is recorded under ignored state.
The original logo, seventeen settings/runtime/selection fingerprints and four
other worktree attachments remain unchanged. Recovery evidence:
`state/backups/app-logo-icon-20261010/`; prior main:
`archive/2026-10-10/main-before-app-logo-icon`. No full suite, live model/provider
calls, old distributed ZIP rebuild, physical-device qualification or remote
publication ran. Integrate by local fast-forward and delete the merged feature
branch.

## Corrected source dimensions

The replacement desktop PNG now supplies the existing shared application,
window, loading, tray, notification and shortcut artwork. The ICO was rebuilt
with the existing tool and all nine sizes were visually inspected. The existing
proportion check now follows the bundled source dimensions rather than the old
780 × 694 image. All 25 essential branding/notification checks pass. A real
Windows banner with the new artwork received its show callback, and the matching
desktop shortcut was refreshed with launch options preserved. Full-suite and
live-model/API checks were not run; see the latest record in `docs/git-workflow.md`.
