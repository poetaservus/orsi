# Independent interface font

Appearance replaces the Text size placeholder with an active Font selector:
Theme default, Lora, Merriweather, Outfit, Nunito, DM Sans and Montserrat.
The new label, options, help and error text stay in English, including when
the GUI language changes. No translation catalogs were edited.

Theme default follows the selected theme's original family. An explicit font
overrides interface and transcript prose immediately and remains selected when
themes change. Theme manifests, imported assets and exports retain their own
original fonts. Existing message content, text selections, composer drafts and
fixed-width code editors survive font changes and responsive reflow.

The profile-scoped `font_v1.json` preference is separate from theme selection
and other UI settings. Reads do not create or migrate preferences. Invalid
saved data and failed saves preserve the existing file. Protected profiles
store this preference inside the vault; its consumer closes when the profile
locks. The public login appearance cache may remember only the bundled font
ID, alongside existing public appearance metadata, so login restores the font
before unlock without copying private assets. Older login caches remain valid.

The six families are bundled from pinned official Google Fonts sources under
`app/ui/assets/fonts/`, including upright variable weights, available italic
faces and complete adjacent SIL Open Font License notices. Font binaries are
unchanged; license trailing whitespace is normalized without changing wording.
`SOURCES.md` records pinned URLs and local SHA-256 hashes. Git attributes keep
font binaries and license line endings stable. Existing package-data rules,
the standalone asset inclusion and the portable source exporter already include
these files. Font loading uses paths relative to the installed application;
it needs neither host installation nor a network request. Public font
registrations live for the Qt application lifetime, independently of theme
font registrations, including Conformist's separate DM Sans copy.

## Essential verification, 15 October 2026

The final native checks passed **76 tests** with no failures, errors or skips:
15 focused font checks in 55.64 seconds and 61 relevant existing theme, Settings
and login regressions in 57.04 seconds. Both runs used isolated repository-local
basetemp directories. The first focused run's seven optical-size-alias
expectation failures and sandbox vault-lock denial are retained separately;
the corrected native alias expectations and unrestricted Windows lock check
pass. No acceptance prompts or unrelated assertions were changed.

Twenty-eight native font/theme/window-size layouts verified that Font stays
inside the viewport and its selected label fits at 760×600 and 1280×900.
Representative serif and sans-serif Settings, dropdown and chat previews were
visually inspected. The built Python wheel contains all fonts/licenses/source
metadata with matching recorded hashes; all six families also load from an
extracted, relocated package. Compilation and whitespace checks pass.

Evidence is retained in ignored `state/font-focused.xml`, `state/font-native.xml`,
`state/font-regression.xml`, `state/font-preview/` and `state/font-wheel/`.
The full suite, live-model/API gates and full standalone runtime rebuild were
not run under the user's essential-UI-check scope.
