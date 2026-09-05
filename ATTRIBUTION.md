# Attribution

The Arasaka color scheme, launcher artwork, Mikoshi wallpapers, splash screen,
SDDM theme, browser integration, and shell palette are original project work.

Klassy, Better Blur DX, Polonium, Panel Colorizer, Application Title Bar,
Smart Video Wallpaper Reborn, and Kurve remain licensed by their respective
upstream projects. Their pinned source locations are recorded in
`manifest/components.tsv`.

The fallback Plasma shell artwork and icon set come from Daemon 2.0 by
MathisP75, licensed under GPL-3.0 and adapted from Simply Circles where noted
upstream. The session lock-screen UI comes from Silent KLockscreen by Khip01,
a GPL-licensed Plasma 6 port of SilentSDDM. Both sources are pinned in the
component manifest; their installers are not executed.

TV Glitch comes from [Burn-My-Windows](https://github.com/Schneegans/Burn-My-Windows),
release v48, by Simon Schneegans, Martin Floeser, and Vlad Zahorodnii. The TV Glitch
shader credits Kurt Wilson for combining the TV and Glitch effects. The individual
Plasma 6 package is SHA-256-pinned in `manifest/components.tsv`; shaders, settings
UI, and translations are downloaded from that package rather than duplicated here.

`theme/kwin/effects/arasaka_tv_glitch_minimize/` is this project's local
minimize/restore adaptation, distributed under GPL-3.0-or-later. Its metadata and
configuration schema are adapted from Burn-My-Windows; its event handling reuses
the upstream shader for minimization, restoration, and interrupted-animation
reversal. The upstream open/close script is not modified. The GPL text is included
in `LICENSES/GPL-3.0-or-later.txt` and installed with both effects.
