# Attribution

## Project License

Copyright (c) 2026 Arasaka KDE contributors. Licensed under the EUPL-1.2, except
where a file notice, component metadata or the exceptions below specify another
license. This default covers original project code, configuration, documentation
and artwork; it does not relicense third-party material or existing adaptations.

The unmodified English EUPL 1.2 text in `LICENSE` was downloaded with `curl` from
the European Commission's [developer text](https://joinup.ec.europa.eu/sites/default/files/custom-page/attachment/2020-03/EUPL-1.2%20EN.txt),
linked by its [official EUPL page](https://interoperable-europe.ec.europa.eu/collection/eupl/eupl-text-eupl-12).

Existing component exceptions remain unchanged:

| Component | License |
| --- | --- |
| `plasma/applets/com.arasaka.launcher/` | MIT; see `LICENSES/MIT.txt` |
| `theme/plasma/desktoptheme/com.arasaka.mikoshi/` | CC0-1.0; see `LICENSES/CC0-1.0.txt` |
| `theme/plasma/look-and-feel/com.arasaka.mikoshi/` and `theme/sddm/com.arasaka.mikoshi/` | GPL-3.0, as declared in component metadata; text in `LICENSES/GPL-3.0-or-later.txt` |
| `theme/kwin/effects/arasaka_tv_glitch_minimize/` | GPL-3.0-or-later; see `LICENSES/GPL-3.0-or-later.txt` |
| `packaging/plasmalogin/debian/` | GPL-2.0-or-later for local packaging; the adapted debconf script retains its GPL version 2 notice; see `LICENSES/GPL-2.0-or-later.txt` and the packaging `copyright` file |
| `theme/lockscreen/silent-plasma-6.7.patch` | Retains the upstream Silent KLockscreen GPL terms |
| `assets/wallpapers/shaders/heartfelt-no-heart.patch` and `assets/wallpapers/shaders/dusti.patch` | CC BY-NC-SA 3.0, with the qualifications below |

Downloaded upstream components and shaders retain their own licenses and notices,
as detailed below. The noncommercial shaders are not covered by the project EUPL
grant. License-document copyrights belong to their respective authors; including
a license text does not change any component's grant.

## Credits

The Arasaka color scheme, launcher artwork, Mikoshi wallpapers, splash screen,
SDDM theme, browser integration, and shell palette are original project work.

Klassy, Better Blur DX, Polonium, Panel Colorizer, Application Title Bar, and Kurve
remain licensed by their respective upstream projects. Their pinned source
locations are recorded in `manifest/components.tsv`.

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

[Shader Wallpaper](https://github.com/y4my4my4m/kde-shader-wallpaper) is by
@y4my4my4m (@y4my4m), licensed under GPL-3.0-or-later. Commit
`6a8c01eb7c3a47a0991707561da737b365553247` is pinned with its source archive hash
in `manifest/components.tsv`. The user-local package includes upstream's
`LICENSE`; its native plugin is embedded in that wallpaper package. The separate
`arasaka-login-wallpaper` Debian package builds the same pinned renderer into an
independent system-wide wallpaper package without copying the user's gallery.
Bundled shaders retain their individual licenses rather than inheriting the
wallpaper engine's GPL license.

[Plasma Login Manager](https://invent.kde.org/plasma/plasma-login-manager) 6.7.4 is
by KDE contributors, with daemon/authentication code derived from SDDM by
Abdurrahman AVCI, Alexey Rochev, Jerome Leclanche and other upstream contributors.
The official release archive is pinned in `manifest/components.tsv`. Local Debian
packaging under `packaging/plasmalogin/debian/` is GPL-2.0-or-later; its debconf
registration retains Branden Robinson's GPL-2 Debian xdm/SDDM script notice.
The local package includes upstream `LICENSE`, `LICENSE.CC-BY-3.0`, the complete
`LICENSES/` directory and source-header copyright/license notices under
`/usr/share/doc/plasmalogin/`. Per-file GPL, LGPL, BSD, CC0 and CC-BY terms remain
in effect; see the package's `copyright` file rather than assigning one license
to all upstream materials. PLM's UI does not reuse this project's SDDM QML layout.

**Heartfelt** is by Martijn Steinrucken, aka BigWings (2017), under
[Creative Commons Attribution-NonCommercial-ShareAlike 3.0 Unported](https://creativecommons.org/licenses/by-nc-sa/3.0/).
The pinned [upstream shader](https://github.com/y4my4my4m/kde-shader-wallpaper/blob/6a8c01eb7c3a47a0991707561da737b365553247/package/contents/ui/Shaders/Heartfelt.frag)
retains his contact details and credits Dave Hoskins for the hash function.
The upstream package also adapts the texture's vertical orientation for its engine.
`assets/wallpapers/shaders/heartfelt-no-heart.patch` is Arasaka KDE's local
adaptation: it disables the `HAS_HEART` switch and adds attribution/source notes
for the no-heart rain effect over the existing Arasaka artwork. The generated
`Heartfelt_No_Heart.frag` preserves the upstream header and remains subject to
CC BY-NC-SA 3.0, including its noncommercial and share-alike conditions. It does
not replace the original packaged shader; the complete shader source is fetched
from the pinned archive rather than duplicated in this repository.

**Tokyo** ([Shadertoy Xtf3zn](https://www.shadertoy.com/view/Xtf3zn)) is by
Reinder Nijhoff (`reinder`, 2014), under the explicit
[CC BY-NC-SA 4.0 International license](https://creativecommons.org/licenses/by-nc-sa/4.0/).
The installer uses the author's [GLSL backup](https://github.com/reindernijhoff/shadertoy/blob/2def3ce132b4f5d9590e9eee0c17bd37a011835c/tokyo/Image.glsl)
at commit `2def3ce132b4f5d9590e9eee0c17bd37a011835c`, pinned as `shader-tokyo`.
Original credits include Eiffie's car model from
[Shiny Toy](https://www.shadertoy.com/view/ldsGWB), Dave Hoskins for the rain,
and iq for `smin`. Installation removes the UTF-8 BOM and prepends attribution
and channel-routing comments; executable source and letterboxing are unchanged.

**Dusti [237 Chars]** ([Shadertoy tcXXDB](https://www.shadertoy.com/view/tcXXDB))
is by `HellMood`. Its [archived API JSON](https://github.com/GabeRundlett/shadertoy-api-shaders/blob/f6d538adf936215ccf2d11ba9b4a6c79ccb448c5/shaders/tcXXDB.json)
at commit `f6d538adf936215ccf2d11ba9b4a6c79ccb448c5` (2025-05-29) is pinned as
`shader-dusti`. All decoded GLSL comments are retained, including credits to
Xor's [Dust](https://www.shadertoy.com/view/cdG3Wd), FabriceNeyret2's
[bufferless version](https://www.shadertoy.com/view/DlGyWt), gopher/xor, and catnip.
No author-supplied license override was found in this archived source or its
metadata. Shadertoy's [public default licensing terms](https://www.shadertoy.com/terms)
therefore indicate [CC BY-NC-SA 3.0 Unported](https://creativecommons.org/licenses/by-nc-sa/3.0/),
not the mirror repository's license. The current live shader/license could not
be checked; this records the frozen public snapshot, not a current-page claim.
In addition to attribution and explicit no-input channel-routing comments,
`assets/wallpapers/shaders/dusti.patch` adds `O.a = 1.0` after the active Image
pass's calculations. This opaque-alpha adapter leaves RGB calculations unchanged.
It addresses the original's all-white/static output observed in GPU smoke checks;
the alpha-only variant produced visible animated desert geometry. The original
uninitialized locals and commented alternative are retained, so portability across
other GPU drivers remains a risk. The adaptation retains the same CC BY-NC-SA 3.0
conditions and is identified in the installed shader header and gallery description.

Both imports are single Image passes without textures, buffers, or audio assets.
They remain subject to their individual noncommercial and share-alike conditions,
not the wallpaper engine's GPL license. Complete sources are fetched rather than
duplicated in this repository; author and license details also appear in the
installed gallery descriptions and shader headers.
