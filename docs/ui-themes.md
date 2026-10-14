# Cosmetic UI themes

Settings → Appearance → Theme changes the background, interface palette, user
bubbles, composer, interface/chat font family and action icons immediately.
Original preserves the existing appearance. Ocean provides a contrasting example.
See the [essential verification record](ui-themes-verification.md).

Response formatting, Markdown parsing, headings, emphasis, spacing, font sizes,
code's monospace font and syntax highlighting, control geometry, animations,
notification artwork, notification events and notification sounds retain their
existing behavior. A different font family naturally changes text wrapping.
The microphone and folder retain their current placeholder behavior.

## Create or add a theme

1. Select a starting theme and click **Export current theme…**. Choose a parent
   folder. O.R.S.I creates a new theme folder without overwriting existing files.
2. Edit its `theme.json` in any text editor. `PALETTE.txt` lists available color
   roles and Original's representative values. Omitted fields inherit Original.
3. Click **Add theme…**, select that `theme.json`, and the theme applies immediately.
   Referenced assets are copied into the profile; the source folder is no longer
   needed. Import the same ID again to update an existing custom theme.

To share a theme, share the exported folder. No installation, dependency downloads,
registry changes, code, account connection or restart is needed. Built-in IDs
`original` and `ocean` are reserved; their exports receive editable `my-` IDs.

A minimal theme is:

```json
{
  "version": 1,
  "id": "my-ocean",
  "name": "My Ocean",
  "font": {"family": "Segoe UI"},
  "background": {
    "type": "gradient",
    "colors": ["#071b26", "#103444"],
    "direction": "diagonal"
  },
  "palette": {
    "text": "#e0f5f4",
    "icon": "#b5e9e5",
    "user_bubble_top": "#286573ee",
    "user_bubble_bottom": "#205361ee",
    "user_text": "#edffff",
    "composer_top": "#1c4b57",
    "composer_middle": "#194550",
    "composer_bottom": "#153e49"
  }
}
```

The stable ID starts with a lowercase letter and can contain lowercase letters,
digits, `_` and `-`, up to 64 characters. Names can contain up to 80 characters.
Colors use `#RRGGBB` or `#RRGGBBAA`, with alpha last.

## Assets and fonts

```text
my-theme/
  theme.json
  background.png
  fonts/
    UI.ttf
  icons/
    send.svg
    settings.png
```

Add only the assets the manifest references:

```json
"font": {"file": "fonts/UI.ttf"},
"background": {"type": "image", "file": "background.png", "fit": "cover"},
"icons": {"send": "icons/send.svg", "settings": "icons/settings.png"}
```

A font can name an installed family or supply a TTF/OTF file. Bundled fonts load
from memory and are released when switching away or closing the profile. Missing
installed fonts fall back to Saira, with an inline explanation. Keep any font or
artwork licenses when distributing your theme.

Background options:

- Solid: `{"type": "solid", "color": "#112233"}`.
- Gradient: 2–8 `colors`, with `direction` of `vertical`, `horizontal` or `diagonal`.
- Image: PNG/JPEG, with `fit` of `cover` (default), `contain` or `stretch`.
  Optional `top_crop` removes that many source-image pixels before fitting.
  Original's export retains its existing 68-pixel crop and stretch behavior.

Icon action names are `new_message`, `settings`, `send`, `stop`, `microphone`,
`attach`, `folder`, `copy` and `check`. Use static SVG or PNG files. Omitted icons
use the existing artwork; `palette.icon` recolors that inherited artwork.
Explicitly supplied icons retain their own colors. Button sizes, hit targets,
enabled/disabled state, animations and actions remain controlled by the app.

Asset paths are relative to the manifest folder. External references, filesystem
links, scripts and animated assets are rejected. Each asset is limited to 8 MiB,
with 24 MiB combined per theme. Images are limited to 24 megapixels and 8192 pixels
per side. Up to 100 custom themes / a 64 MiB saved catalog are supported.

## Palette roles

| Area | Roles |
| --- | --- |
| Text | `text`, `text_muted`, `text_disabled` |
| Controls | `surface`, `surface_hover`, `surface_pressed`, `border`, `focus`, `accent` |
| Selection | `selection`, `selection_text` |
| Icons | `icon` |
| Settings panel | `settings_top`, `settings_bottom` |
| Composer | `composer_top`, `composer_middle`, `composer_bottom`, `composer_border`, `composer_highlight`, `composer_text`, `placeholder` |
| User messages | `user_bubble_top`, `user_bubble_bottom`, `user_bubble_border`, `user_text` |
| Other | `inline_reference`, `scrollbar`, `error`, `success` |

Application code maps its existing style values to these roles. Omitted roles
retain their exact original values, rather than flattening the existing palette.
Theme files cannot supply arbitrary Qt stylesheets or change formatting rules.

## Storage and failure behavior

The existing UI preference file stores only `theme_id` alongside other settings.
Custom packages and their assets live in `state/themes/catalog_v1.json`, relative
to the active personal profile. Legacy mode uses ignored application `state/`.
Encrypted profiles use the existing protected-record interface, including
in-memory image/font loading, with no plaintext asset cache. Profile backup,
restore and portable copies retain the catalog. Legacy preference migration also
includes it. The locked/unlock screen uses the original appearance.

Import validates the full package and decodes its assets before saving or applying
it. Invalid imports leave the current appearance intact. Missing or invalid saved
themes fall back to Original while preserving the saved selection/catalog. An
unreadable preference or catalog file is not silently overwritten.

Switches update existing widgets in place. Drafts, attachments, streaming state,
text selection, copy feedback and reader scroll position remain intact. The
existing text sizing code reflows messages for the selected font. Custom
backgrounds are rendered once per surface size so the composer glass samples
the same background pixels.
