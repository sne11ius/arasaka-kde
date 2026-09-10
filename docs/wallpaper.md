# Wallpaper and lock screen

[Docs](README.md) / Wallpaper

**Interactive Rain** is the managed background: native droplets fall, merge,
refract Mikoshi artwork, and leave wet trails through fog. Hover influences nearby
drops. A left-click splits a drop into a small splash that conserves its water
and inherited momentum.

## One experience, three hosts

| Property | Desktop | Session locker | PLM login |
| --- | --- | --- | --- |
| Artwork and effect | Mikoshi + Interactive Rain | Same | Same |
| Target frame rate | 30 FPS | 30 FPS | 30 FPS |
| Playback / resolution | 75% / full | Same | Same |
| Hover and click splashes | Passive native observer | Same observer, locker-local | Same observer, with PLM pointer bridge |
| Animation lifecycle | Pauses behind maximized/fullscreen windows on that screen | Animates while visible | Animates while visible |
| Assets | User-local | User-local | System package under `/usr/share` |

The shared source is [`plasma/wallpaper-defaults.json`](../plasma/wallpaper-defaults.json).
Host-specific pause policy is a lifecycle adaptation, not a different rain effect.
Desktop texture selection supports both 16:9 and 16:10; greeters use the 16:9
texture. Frame rate is a configured target, not a measured performance guarantee.

### How input reaches the rain

Only recognized native-rain hosts gain interaction. The observer does not consume
mouse or keyboard events, grab input, change focus, read password text, or poll
the global cursor. The obscured desktop rejects input while the session is locked.

PLM's top-layer greeter and wallpaper are **separate processes**. Its patched
frontend forwards only screen identity and normalized, screen-local pointer
activity over PLM's existing session bus. The wallpaper delivers it to the same
native observer. Installing the shader or setting `mouseEnabled=true` alone does
not provide this bridge: the updater currently requires the known patched PLM
package **6.7.4-0arasaka2**. A higher upstream version alone does not prove support.

Unknown/detached hosts revoke permission. Pausing, switching shaders, changing
hosts, or disabling input cancels pending splashes. The settings preview remains
input-disabled. Ordinary gallery shaders do not inherit greeter input permission.

## Apply the shared background

First update the user-local assets and desktop, then the session locker:

```sh
./bin/apply-shader-wallpaper
./bin/apply-lockscreen
```

Run both as the desktop user in the intended Plasma session. The first command
builds, backs up, installs, and activates the desktop defaults. The second uses
the installed assets and preserves the clock, authentication, and lock policy.
The shader installer also publishes the wallpaper template, shared defaults and
matching display reconciler under its existing reconciliation lock. Newly attached
desktops therefore use the same current defaults. The launcher layout is preserved.

For PLM, complete [the system-package update](login.md#update-an-existing-plm-installation),
including the pointer bridge, then apply the shared login settings. Recheck
animation, hover, and clicks at the next normal lock/login on each screen.

### Install or stage without activating

```sh
./bin/apply-shader-wallpaper --install-only
```

This builds and installs the user-local package and artwork without live session
calls or changing saved wallpaper selection.

```sh
./bin/apply-shader-wallpaper --stage-only /absolute/empty/staging-directory
```

Staging exports a system-package tree with final `/usr/share` URLs. The destination
must be absolute and empty or nonexistent, with no symlinked path components.
It skips home installation/backups, gallery merging, and session calls. This is
the same mode used by `build-plm`; it is mutually exclusive with `--install-only`.

## Session lock screen

```sh
./bin/apply-lockscreen
```

The command requires the installed native package, generated rain shader, artwork,
Python 3, `kreadconfig6`, `kwriteconfig6`, and `ldd`. It checks the ELF library,
dependencies, exact `// @arasaka-effect rain-v1` marker, configuration schema, and
native metadata for `rainLockScreenHost` and `rainGreeterInteractionVersion`.
Older modules are rejected before settings are written.

It stages the appearance, verifies it through KConfig, saves a private backup,
and uses KConfig's merge writer to update only managed appearance keys, selecting
the wallpaper plugin last. It does not rebuild assets or force a lock/restart.

| Host | Plugin-selection key | Appearance group |
| --- | --- | --- |
| Locker | `[Greeter] WallpaperPlugin` | `[Greeter][Wallpaper][online.knowmad.shaderwallpaper][General]` |
| PLM | `[Greeter] WallpaperPluginId` | Same group structure in `/etc/plasmalogin.conf` |

The locker configuration is `kscreenlockerrc`. Clock/date preference, `[Daemon]`
lock policy, and unrelated wallpaper settings are preserved. The native renderer
requires OpenGL; the installer does not override global Qt rendering settings or
disable the locker's software-rendering crash recovery.

## Settings and interaction

Managed defaults enable mouse input and texture channel 0. Audio capture,
window-reactive shader input, playlists, source watching, and generic A–D buffer
passes are disabled. The native rain field is independent of those buffer passes.

- **Hover:** move over exposed wallpaper to influence nearby droplets.
- **Splash:** use an unmodified left press on a visible drop. Holding does not
  repeat; the second press of a double-click is another burst. Clear-glass clicks
  do nothing. Plasma still receives the click normally.
- **Small or crowded drops:** a drop may receive a nudge instead of splitting.
  The 1,024-drop cap limits identities, not incoming water.
- **Merging:** colliding drops form a short-lived liquid neck and settle into a
  rounded cap. Clicking a merging silhouette targets the whole body.
- **Pause:** freezes simulation, merge transitions, condensation, and wet trails.

Use the wallpaper's settings to change speed, resolution, or mouse permission.
Selecting Interactive Rain from the gallery does not itself turn mouse input on.
Explicitly reapplying the managed desktop command restores the shared defaults.

Large drops sag under gravity and elongate while sliding; small stationary beads
remain round. Fog uses filtered mip levels, and lightning retains one in four
original bursts at 25% strength: roughly one burst per 67 seconds of active
playback at the default speed. See [customization](customization.md#rain-performance).

## Gallery and preservation

The gallery includes upstream effects plus these credited entries:

| Effect | Origin | Notes |
| --- | --- | --- |
| Interactive Rain | Local adaptation of BigWings' Heartfelt | Native physics; managed default on all three surfaces |
| Heartfelt No Heart | BigWings' Heartfelt, adapted | Separate procedural-rain alternative |
| Tokyo | Reinder Nijhoff | Single pass; original letterbox bars retained |
| Dusti [237 Chars] | HellMood | Single pass; local opaque-alpha adapter |

The installer preserves custom shader files under `Shaders/` and `Shaders6/`,
including compatible bundle directories. It carries forward gallery entries,
custom categories, IDs, favorites, and thumbnail references. Managed entries are
updated without losing their saved identities.

Conflicting edits to bundled shaders, file/directory collisions, and duplicate
gallery IDs cause refusal before package replacement. Preserve or rename the
conflicting import and retry. Other package locations are replaced and retained
in the complete package backup.

Shader licenses differ from the renderer's GPL and the project's EUPL. See
[attribution and shader terms](../ATTRIBUTION.md) before redistribution.

## Build and deployment details

The immutable renderer archive comes from [`manifest/components.tsv`](../manifest/components.tsv)
through `fetch-components`. The installer extracts a temporary source tree,
applies the host patch, and copies the six explicit native rain source/header
files into upstream's existing module. Upstream `build.sh` and `cmake --install`
are not executed.

The native plugin is embedded at:

```text
${XDG_DATA_HOME:-$HOME/.local/share}/plasma/wallpapers/
  online.knowmad.shaderwallpaper/contents/ui/shaderwallpaper/
```

Artwork is rendered from the two original SVGs into 1920×1080 and 1600×1000 PNGs
under the data home's `wallpapers/Arasaka/`. Heartfelt No Heart is generated from
upstream Heartfelt, then copied and adapted into Interactive Rain. All patches
use `--batch --forward --fuzz=0 -p1`; original shader headers and credits survive.
Complete upstream shaders and generated PNGs are not tracked in this repository.

Desktop activation uses two Plasma scripting evaluations:

1. **Prepare:** write/verify the shader and capture opt-outs with mouse off, mark
   the desktop pending, and request the wallpaper plugin.
2. **Activate:** read fresh committed wrappers, verify settings and enabled-output
   coverage, then enable mouse input and clear the pending marker.

Parked containments with screen `-1` are left alone. Failed preparation does not
select the plugin; interrupted activation stays pending rather than claiming
success. An intervening user edit cancels automatic completion.

Full deployment's display watcher initializes non-shader desktops using installed
assets and preserves existing custom shader selections. Missing assets defer
wallpaper setup while launcher/display reconciliation continues. Every watcher
run rechecks readiness, including after reconnection.

## Backups and verification

Shader backups live under the state home's `arasaka-kde/backups/shader-wallpaper-*`.
They include previous Plasma settings, the package, replaced artwork/custom rain
shaders, and runtime files. User-local deployment publishes matching
`reconcile-displays`, `shader-wallpaper.js`, and `wallpaper-defaults.json` together
while holding the watcher's existing lock. The launcher's `layout.js` is backed up
but not rewritten. Locker backups use `lockscreen-*`.
Keep them private. [Recovery instructions →](troubleshooting.md#backups-and-recovery)

`make test` covers installer fixtures, shared defaults, activation sequencing,
artwork rendering, and native simulation. Native graphics/input checks exercise
real Qt/OpenGL and cross-process pointer delivery. Full wallpaper-host and live
session checks remain separate: [development guide](development.md#native-and-live-integration).

Configuration readback is not proof of rendering, actual host input delivery,
or frame times. Cached modules may require an explicit new Plasma session. Check
the locker and PLM at their next normal starts rather than restarting the display
manager from a running desktop.
