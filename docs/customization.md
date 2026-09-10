# Customization

[Docs](README.md) / Customization

Keep accepted visual changes in the repository so they can be reproduced. The
source files below are a better starting point than copying complete personal
configuration directories.

## Palette

| Role | Color | Source |
| --- | --- | --- |
| Window surface | `#11151A` | `theme/color-schemes/Arasaka.colors` |
| View / deep surface | `#07090C` | Same |
| Alternate surface | `#191D23` | Same |
| Main text | `#E8E9EA` | Same |
| Accent | `#E60012` | Same |
| Hover | `#FF3344` | Same |
| Muted text | `#737B86` | Same |

The Mikoshi artwork adds coral, cyan, and small amber accents so the wallpaper
stays visible through tiling gaps and fog. Its palette is intentionally brighter
than the application surfaces.

## Fonts and application styling

| Component | Managed input |
| --- | --- |
| UI and small text | Inter, configured in `bin/apply-live` |
| Terminal / fixed-width text | JetBrains Mono |
| Window titles | Rajdhani SemiBold |
| Konsole | `theme/konsole/Arasaka.colorscheme` |
| Plasma colors | `theme/color-schemes/Arasaka.colors` |
| Plasma shell / splash | `theme/plasma/` |
| GTK accents | `theme/gtk/gtk.css` |
| Firefox chrome | `theme/firefox/userChrome.css` |
| Edge integration | `theme/browser/` and `bin/apply-edge-theme` |
| Zsh prompt overlay | `theme/zsh/arasaka-p10k.zsh` |
| KWin transitions | `theme/kwin/effects/arasaka_tv_glitch_minimize/` |

`apply-live` installs these inputs, configures Klassy and KvFlatRed, imports the
GTK overlay, and adds the Zsh overlay source line when appropriate. Firefox
integration enables userChrome styles for profiles found through `profiles.ini`.
Review the relevant command before reapplying application-specific changes.

## Artwork

Edit the source artwork:

- [`mikoshi-16x9.svg`](../assets/wallpapers/mikoshi-16x9.svg)
- [`mikoshi-16x10.svg`](../assets/wallpapers/mikoshi-16x10.svg)
- [`arasaka-launcher.svg`](../assets/branding/arasaka-launcher.svg)

The shader installer renders its PNG textures from these SVGs. The static README
previews use the sources directly. Generated textures and upstream shader copies
are build outputs rather than separately maintained artwork.

To carry a background change everywhere, update user-local assets for desktop and
locker **and** the system packages for PLM. See [wallpaper](wallpaper.md) and
[login updates](login.md#update-an-existing-plm-installation).

## Rain performance

The shared defaults are in
[`plasma/wallpaper-defaults.json`](../plasma/wallpaper-defaults.json):

| Setting | Default | Effect |
| --- | --- | --- |
| `targetFps` | `30` | Frame-rate target |
| `shaderSpeed` | `0.75` | Simulation and shader playback speed |
| `resolutionScale` | `1` | Full rendering resolution |
| `mouseEnabled` | `true` | Native hover and click splashes |
| `audioEnabled` | `false` | No managed audio capture |
| `windowsEnabled` | `false` | No window-reactive shader input |

Lower rendering resolution or frame-rate target can reduce GPU work. Reducing
shader speed changes the effect's pace, not necessarily its rendering cost.
Build parallelism (`ARASAKA_SHADER_BUILD_JOBS`) controls compilation memory/CPU
use, not runtime frame rate.

The desktop pauses for maximized/fullscreen windows on its respective display.
Visible greeters keep animating. Preserve that host distinction when changing
shared visuals. A configured 30 FPS target is not a benchmark; measure frame times
on the intended GPU and display setup before making performance claims.

## Keeping your choices

Standalone launcher deployment leaves wallpaper selection alone. The full-theme
display watcher preserves existing shader choices and initializes desktops not
yet using the shader plugin. Explicit shader reapplication resets managed rain
defaults, while retaining compatible gallery entries and favorites.

Background-only locker/PLM updates preserve clock preference and lock/authentication
policy. Prefer scoped commands when you only want to refresh one component.

For contributions, include the source change and a clear visual description.
Credit upstream artwork and shaders, retain their terms, and avoid publishing
private desktop content in screenshots. [Contribution guide →](../CONTRIBUTING.md)
