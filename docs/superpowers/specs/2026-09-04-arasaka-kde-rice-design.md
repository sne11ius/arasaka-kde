# Arasaka KDE Rice Design

Date: 2026-09-04
Status: Approved in chat, pending written-spec review

## Purpose

Build a maximum-spectacle Arasaka-themed KDE Plasma environment for daily use on this machine. The result must cover every visible desktop surface, remain usable when the laptop is docked to different external monitors or used alone, and be reproducible and reversible from a local Git repository.

The implementation lives at `~/src/extern/arasaka-kde`. This location intentionally follows the user's convention for non-work projects, despite the general `~/src/CLAUDE.md` guidance that `extern` contains third-party code.

## Baseline

- Operating system: TUXEDO OS, Debian-based
- Desktop: KDE Plasma 6.7.2 on Wayland
- Internal display: `eDP-1`, 2560x1600 at 300 Hz, scale 1.3
- Current external display: `DP-2`, 3840x2160 at 60 Hz, scale 1.6
- Current desktop count: one
- Current panel: one 44 px floating bottom panel
- Existing user-installed Plasma applets, KWin scripts, and KWin effects: none
- Existing user color schemes: only Breeze and TUXEDO variants
- Existing terminal workflow: Konsole `Quake.profile`, tabs at the bottom

The implementation must preserve display modes, scale factors, refresh rates, physical monitor arrangement, desktop files, secrets, power settings, application data, and unrelated configuration.

## Goals

- Deliver an unmistakable Arasaka corporate command-center aesthetic rather than a generic neon cyberpunk theme.
- Favor spectacle: animated wallpaper, strong blur, telemetry, tiling, transitions, and complete cross-application theming are in scope.
- Make any enabled external display primary. Use the internal display as primary only when no external display is connected.
- Keep exactly one KDE virtual desktop.
- Adapt panel roles and tiling behavior without storing monitor UUIDs or assuming one external connector name.
- Theme Plasma, KWin, Qt, GTK, browsers, Electron chrome where supported, terminals, lock screen, splash screen, SDDM, icons, cursor, and desktop sounds.
- Provide deterministic install, dry-run, apply, doctor, and rollback commands.

## Non-Goals

- Replacing Plasma or KWin with another desktop shell or compositor.
- Adding KDE Activities or additional virtual desktops.
- Changing monitor resolution, scaling, refresh rate, orientation, or placement.
- Moving, deleting, renaming, or committing files from the user's desktop or home directory.
- Running opaque upstream installers directly against the live home directory.
- Patching Plasma or KWin core packages.
- Depending on obsolete Plasma 5 or Latte Dock components.

## Visual System

### Palette

The core palette is deliberately narrow:

- Void: `#07090C`
- Gunmetal: `#11151A`
- Raised surface: `#191D23`
- Cold white: `#E8E9EA`
- Telemetry gray: `#737B86`
- Arasaka crimson: `#E60012`
- Critical alert: `#FF3344`

Red is reserved for active focus, separators, warnings, selected controls, progress, and Arasaka identity marks. The design must not introduce a blue-purple cyberpunk gradient or multicolor status palette. Positive and neutral states remain white or gray unless color is required for accessibility.

### Shape And Material

- Near-square window corners with small geometric cuts rather than large rounded cards.
- Thin crimson active-window frame and muted graphite inactive frames.
- Dark translucent panels with controlled blur, fine noise, scanlines, and one-pixel red rules.
- Compact controls, angular separators, and deliberately dense information hierarchy.
- Panel modules appear as segmented data blocks instead of soft pills.

### Typography

- Rajdhani SemiBold for display labels, panel modules, clock, and headings.
- Inter for application UI and long-form readability.
- JetBrains Mono for Konsole, Alacritty, code, sensor readouts, and shell prompts.

Fonts are installed into the user font directory and refreshed without replacing unrelated fonts.

### Icons And Cursor

Use a maintained monochrome dark icon base with an Arasaka override layer for launcher, panel, status, folder, and common application icons. Panel Colorizer may replace system-tray icons by icon name to enforce white/gray idle and red active states. The cursor is a high-contrast white or light-gray shape with a crimson busy state.

## Artwork

Create an original "Mikoshi data core" composition in both 16:9 4K and 16:10 2560x1600 forms. It uses black architectural space, severe red geometry, Japanese corporate markings, scanlines, and an Arasaka emblem. Important visual elements stay inside safe areas so cropping on an unfamiliar external display remains intentional.

The desktop uses a slow, silent animated loop through Smart Video Wallpaper Reborn. Static versions are used as immediate fallback and for SDDM, splash, and recovery. The lock screen may use the animated loop only if a smoke test confirms reliable playback; otherwise it uses the static artwork.

All third-party visual material must retain source and license attribution in the repository. Assets without clear redistribution terms may be used only as local source inputs and must not be committed.

## Repository Architecture

`~/src/extern/arasaka-kde` is the source of truth. It contains:

- Authored Plasma color, shell, Kvantum, Konsole, terminal, GTK, browser, sound, and artwork assets.
- A manifest of upstream components pinned by release or commit and checksum.
- Scripts for dependency installation, component staging, applying the theme, topology reconciliation, diagnostics, and rollback.
- Shell and fixture tests.
- Documentation for installation, operation, recovery, and attribution.

The repository does not store copies of live configuration containing machine-specific or sensitive state. It stores templates and narrowly scoped transforms instead.

## Display Topology

The topology reconciler classifies built-in outputs by connector family (`eDP`, `LVDS`, or `DSI`) and treats any other enabled output as external. It does not identify monitors by EDID, UUID, model, or a fixed connector such as `DP-2`.

Rules:

- If one external output is enabled, it becomes KDE primary.
- If multiple external outputs are enabled, preserve KScreen's relative priority among them and make the highest-priority external primary.
- If no external output is enabled, the internal display becomes primary.
- Never change mode, scale, refresh, transform, position, brightness, HDR, VRR, or color profile.
- Reconcile panel roles idempotently after login and after KScreen configuration changes.
- Never create duplicate panels after repeated events.

A systemd user service runs reconciliation at graphical-session startup. A user path unit watching KScreen's output configuration triggers the same idempotent service after hotplug or topology changes.

## Panel Layout

### Primary Display

The primary display receives two native Plasma panels:

1. A full-width top command strip containing the Arasaka launcher, active-application identity, media state, compact CPU/GPU/network status, system tray, and segmented date/time.
2. A centered floating bottom task dock containing an icons-only task manager and essential pinned applications.

Panel Colorizer renders angular module backgrounds, red focus edges, and consistent foreground colors. The top strip remains narrow enough to preserve work area; the dock uses dodge-windows behavior rather than permanently consuming a large bottom region.

### Internal Support Display

When an external display is connected, the internal panel becomes a support surface with a single slim telemetry rail. It shows CPU/GPU load and temperature, network throughput, audio/media state, battery, and a restrained audio visualizer. It does not duplicate the main launcher, task dock, or system tray.

When the laptop is used alone, the telemetry-only panel is removed or hidden and the complete primary command strip and task dock move to the internal display.

### Desktop Surface

Desktop icons are hidden by changing the containment presentation, but the underlying files remain untouched. The wallpaper and right-click desktop actions remain available.

## Window Management

Keep exactly one virtual desktop and no workspace pager. Polonium manages windows independently per physical output under Wayland:

- Wide external displays default to a center-master/side-stack layout.
- The internal display defaults to a simpler master-stack layout.
- Inner and outer gaps default to 6 logical pixels.
- Dialogs, launchers, authentication prompts, picture-in-picture windows, and transient utility windows float.
- Existing standard KDE move, resize, fullscreen, and overview behavior remains available.

Use KWin Overview/Present Windows for the dramatic overview transition. Do not enable Desktop Cube because one virtual desktop makes it functionally meaningless.

## Effects

- Better Blur DX provides force blur, noise, and controlled translucency. It must be built for the exact installed KWin version and replace, not stack with, native Blur.
- Native Magic Lamp handles minimization.
- Native overview, fade, and scale animations remain enabled with a deliberate but responsive animation duration.
- Wobbly Windows remains disabled because it conflicts visually with Better Blur DX.
- Burn My Windows is excluded from the initial build because its KWin 6.7 animation API support is currently unreliable.

If Better Blur DX fails compatibility checks, the installer enables native Blur and records the degraded state in `doctor` output.

## Component Stack

The authored layer includes:

- `Arasaka.colors`
- Kvantum Qt application theme
- Klassy application/window-decoration preset
- Plasma shell style and panel assets
- Konsole and Alacritty color schemes
- GTK 3 and GTK 4 CSS integration
- Firefox user chrome and Chromium/Edge system-frame integration where supported
- Zsh/Powerlevel10k color preset
- Static and animated wallpapers
- Lock, splash, and SDDM artwork
- Icon overrides and cursor selection
- A short synthetic desktop sound theme

The pinned extension layer includes:

- Klassy v6.7.2, released for the installed Plasma generation
- Panel Colorizer v8.0.0, including Plasma 6.7 per-output support
- Polonium v1.2.1, whose current upstream recommends Plasma 6.7
- Better Blur DX v2.5.1, built locally against the installed KWin 6.7.2
- Smart Video Wallpaper Reborn v2.14.1
- Application Title Bar v0.10.0, a pure-QML Plasma 6 active-window applet
- Plasma-native System Monitor sensor faces
- Kurve v3.6.0 with CAVA, used only on the support display

Every upstream component is fetched into a build cache, verified against the manifest, and installed by the project scripts. Upstream install scripts are not executed against the live home directory.

## Application Integration

- Preserve the existing Konsole `Quake.profile` behavior and bottom tab placement while applying the Arasaka palette, font, opacity, and blur.
- Apply equivalent colors to Alacritty if it remains installed or in use.
- Theme Dolphin, Kate, System Settings, and other Qt applications through the color scheme, Klassy, and Kvantum.
- Theme GTK 3/4 applications through scoped CSS backed by the same palette.
- Install Firefox chrome only after discovering active profiles; back up every modified profile file.
- Integrate Edge/Chromium through system title bars, GTK color integration, and supported policy-free launch flags or desktop-entry overrides. Do not alter browser profiles, extensions, history, or sync data.
- Let Mattermost and other Electron applications inherit the system frame and palette where supported; do not inject unsupported application code.
- Theme SDDM only if it is the active display manager. Otherwise report the skipped integration.

## Commands And Data Flow

The repository exposes these user-facing commands:

- `./bin/install`: install distro dependencies, fonts, and pinned components.
- `./bin/apply --dry-run`: print every planned file and KDE setting change without modifying the system.
- `./bin/apply`: create a snapshot, stage and validate assets, then switch the live desktop.
- `./bin/doctor`: report environment, dependency, component, codec, KWin ABI, wallpaper, and panel health.
- `./bin/reconcile-displays`: apply only primary-output and panel-role rules.
- `./bin/rollback [snapshot]`: restore a selected snapshot and remove project-owned deployed assets.

Apply order:

1. Validate the environment and manifest.
2. Create a timestamped snapshot with an inventory of every touched path and setting.
3. Stage assets in a temporary directory and parse all generated configuration.
4. Install user-level assets.
5. Apply colors, application styles, decorations, icons, fonts, wallpaper, KWin settings, and panel layout.
6. Install and enable topology user units.
7. Apply privileged SDDM integration separately after displaying the exact operation.
8. Restart Plasma services or request one logout/login when required by compiled KWin effects.
9. Run `doctor` and capture verification screenshots.

## Safety And Recovery

- Use strict shell execution and explicit error propagation.
- Refuse to apply if the current Plasma major version, session type, required tools, or manifest hashes do not match supported values.
- Treat third-party archives as untrusted input: verify checksums, inspect paths, and reject traversal or writes outside staging.
- Keep user-level operations unprivileged. Isolate and enumerate every `sudo` operation.
- Restore the pre-apply snapshot automatically if a pre-switch or configuration validation step fails.
- If a post-switch component fails, retain a functional Plasma fallback and print the exact rollback command.
- Video wallpaper always has a static fallback and a documented TTY recovery path.
- Better Blur DX always has native Blur as fallback.
- Reconciliation is idempotent and logs decisions without recording EDID or other unnecessary hardware identifiers.

## Testing

Automated tests cover:

- Manifest parsing and checksum verification.
- Dry-run producing no changes.
- Snapshot inventory and restoration.
- Generated KDE, Kvantum, terminal, CSS, desktop-entry, and systemd configuration syntax.
- Idempotent application and rollback.
- Display fixtures for internal-only, one external plus internal, external-only, and multiple-external cases.
- Primary-output selection without changing any display property other than priority.
- Panel reconciliation without duplicates.
- Recovery behavior for missing codecs, failed wallpaper playback, and incompatible KWin effects.

Live verification covers:

- Plasma, KWin, and all required applets/effects loading without errors.
- External display becoming primary on the current dual-display setup.
- Full primary panels appearing on the external display and telemetry-only treatment on the internal display.
- Manual or fixture-assisted laptop-only reconciliation before declaring topology support complete.
- Tiling, floating exceptions, overview, minimization, blur, wallpaper playback, lock screen, splash, and terminal behavior.
- Qt, GTK, Firefox, Edge/Chromium, and Electron appearance where those applications are installed.
- A final full-desktop screenshot at the current combined resolution.
- Successful rollback to the captured pre-rice state.

## Acceptance Criteria

- The desktop presents a coherent black, white, gunmetal, and crimson Arasaka identity across all visible supported surfaces.
- The animated Mikoshi artwork, angular panels, telemetry, tiling, and effects produce the requested maximum-spectacle result.
- Any connected external output is primary; the laptop is primary only when no external output is enabled.
- The layout remains complete with the current external monitor, a different external monitor, or the internal display alone.
- Exactly one virtual desktop remains configured.
- Display modes and physical arrangement are unchanged.
- Desktop files and unrelated user data are unchanged.
- `apply --dry-run`, `doctor`, and `rollback` work as documented.
- A fresh installation can reproduce the rice from the repository and pinned upstream sources.
