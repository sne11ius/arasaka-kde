# Arasaka KDE

Arasaka KDE manages a KDE Plasma 6 rice for TUXEDO OS. The repository is intended
to be the source of truth for the whole rice: authored assets, pinned upstream
components, local adaptations, and scoped installation/configuration commands.
Keep accepted visual changes here rather than only in the live home directory.

Do not commit complete personal configuration directories, browser profiles,
signing keys, caches, or runtime window/monitor state. Capture the settings needed
to reproduce the appearance instead.

## Apply

The current deployment command is:

```sh
./bin/apply-live
```

Run it as the desktop user inside the target Plasma session. It changes the live
desktop, installs assets, generates wallpaper media, and configures applications.
It assumes the required fonts, applets, Kvantum theme, and native KWin plugins are
already installed. Full dependency provisioning is still unfinished.

**There is no dry-run or transactional snapshot/rollback implementation yet.**
`apply-live` does not accept a `--dry-run` flag. Existing backups are component
specific, not a complete desktop recovery system.

## Launcher

The launcher replaces the managed top bar and laptop rail with a desktop-hosted
native QML popup. There are no managed bars or hidden edge panels. Press **Super**
to toggle the menu and system tray centered on the **main display**, regardless of
pointer or active-window location; **Escape** dismisses it. Kickoff and
the tray are KDE's stock applets, including native tray submenus, rather than
copied implementations. Unmanaged panels are not removed. The layout requires
the loaded host to acknowledge the current Plasma session token before removing
managed panels; a saved `ready=true` alone is not sufficient.

Activation uses Plasma's existing **Activate Application Launcher** shortcut.
Another launcher on a preserved unmanaged panel can take precedence under KDE's
normal routing rules. The installer does not overwrite other shortcut bindings.
The popup keeps its original desktop owner to avoid Plasma 6.7's embedded-widget
configuration migration bug. The display reconciler supplies the primary
connector, which the popup resolves on each opening; it does not assume Qt's
screen order matches KDE's output priority on Wayland.

To install or reapply only the launcher:

```sh
./bin/apply-launcher
```

Run this as the desktop user in the target Plasma session. It requires Python 3,
`kpackagetool6`, `qdbus6`, `systemctl`, `kscreen-doctor`, `jq`, Bash and standard
Unix utilities, plus Plasma's stock Kickoff and System Tray applets. Before
writing deployment state, it checks commands, readable inputs and backup sources,
validates the absolute source package with
`kpackagetool6 --type Plasma/Applet --show`, and pings the live Plasma D-Bus service.
Symlinked deployment/backup sources are rejected rather than followed.

The tracked package is `plasma/applets/com.arasaka.launcher`, with entry point
`contents/ui/main.qml`. It is copied only to
`${XDG_DATA_HOME:-$HOME/.local/share}/plasma/plasmoids/com.arasaka.launcher`.
The command also stages `reconcile-displays`, `arasaka_topology.py`, `layout.js`,
and the currently required `Arasaka.json` in
`$HOME/.local/libexec/arasaka-kde/`. It runs the display reconciler with `--force`,
retrying failures for up to roughly ten seconds, and independently checks live
host readiness and managed-panel removal. Failure is reported, not treated as
successful installation. This is not the full `apply-live`: it does not install
themes, change window effects or application settings, or generate wallpapers.
Layout and display-priority reconciliation still run, but wallpaper and desktop
icon settings are preserved. Only full-theme deployment opts into the legacy
wallpaper policy with `reconcile-displays --force --wallpapers`.

Before replacement, the command prints a unique backup path under
`${XDG_STATE_HOME:-$HOME/.local/state}/arasaka-kde/backups/launcher-*`.
Each backup contains existing `plasma-org.kde.plasma.desktop-appletsrc` and
`plasmashellrc` from `${XDG_CONFIG_HOME:-$HOME/.config}`, plus `runtime/` and
`package/` snapshots when those directories existed. Backup directories and
their contents have owner-only permissions. They may contain personal settings;
keep them local. There is no automatic transactional rollback.

The existing display watcher is paused while files are installed, and its
reconcile service is stopped to prevent concurrent deployment. Normally the
watcher is resumed only if it was already active; the scoped command never
enables or disables units. `apply-live` uses `apply-launcher --install-only` as
its first staging step, then the full command at layout application time.
`--install-only` still requires a live session and backups, but does not apply
the layout or claim that the launcher is ready.

**Updating an already-loaded host requires an explicit Plasma restart.** QML
cannot reliably reload changed package code in place. In that case the command
backs up and stages the files, leaves existing bars alone, keeps the watcher
paused, and exits unsuccessfully with restart instructions. It never restarts
Plasma automatically. Log out and back in, or explicitly restart Plasma yourself,
then rerun `./bin/apply-launcher`. A private `launcher-restart.json` session marker
prevents a same-session rerun from trusting old cached QML; successful convergence
clears it and resumes the previously active watcher. If a newly installed package
is not discovered by Plasma within the retry window, restart Plasma explicitly
and rerun the command as well.

For manual recovery, retain the printed backup path and choose the snapshot from
before the unwanted change, not a later retry. Stop
`arasaka-display-reconcile.path` and `arasaka-display-reconcile.service` with
`systemctl --user stop`, then stop Plasma (or restore from a separate session
while Plasma is not running). Restore the two saved configuration files to the
configuration directory and replace the affected package and runtime with their
snapshots. If a snapshot is absent, that source did not exist: remove only the
newly installed launcher package or the four runtime files, leaving unrelated
runtime files alone. After restoring, remove the corresponding
`arasaka-kde/launcher-restart.json` marker from the state directory. Start Plasma
again and resume the watcher only if it was active before. Do not overwrite
Plasma configuration while the shell is running: it can overwrite the restore.

Installer behavior is tested with temporary homes and stub session tools. Run the
opt-in native integration test inside a Wayland session:

```sh
python3 tests/launcher_smoke.py
```

It uses isolated settings and a private D-Bus session, briefly displaying the real
Kickoff and tray. It checks fresh readiness acknowledgements, placement, typing,
tray popup interaction, closing/reopening, Escape, and focus-loss dismissal.
The clipboard applet requires a real window system; Qt's offscreen backend is not
supported. Missing-service warnings in the isolated bus are expected.

Live checks on Plasma 6.7 confirmed activation through the action bound to Super,
centered open/close/reopen, no remaining panels, unchanged wallpaper/icon policy,
and stable host identity after reapplying. Physical monitor unplug/replug and
fresh login with the original owner display disconnected remain manual checks.

## Window Effects

Open, close, minimize, and restore use **TV Glitch at 700 ms**. The global Plasma
animation-speed setting also scales that duration. Magic Lamp, Squash, and Scale
are disabled to avoid competing animations. Better Blur DX is left unchanged by
the standalone effect command.

To install or reapply only the window effects:

```sh
./bin/apply-window-effects
```

This fetches the SHA-256-verified Burn-My-Windows v48 TV Glitch package and builds
two local KWin effects from it. The upstream `kwin6_effect_tv_glitch` handles
open/close. The tracked overlay in
`theme/kwin/effects/arasaka_tv_glitch_minimize/` handles minimize/restore using the
same shader, including rapid-toggle reversal and animation cleanup. The overlay
is not a complete package on its own; the command supplies its upstream assets.
No installed home-directory package is needed as an input.

Both effects install under `${XDG_DATA_HOME:-$HOME/.local/share}/kwin/effects/`.
Before changing configuration or replacing packages, the command saves `kwinrc`
and any replaced packages under
`${XDG_STATE_HOME:-$HOME/.local/state}/arasaka-kde/backups/window-effects-*` and
prints the backup path. Backups may contain personal settings; keep them local.
The command fails visibly if KWin cannot load either effect.

The setup was exercised on **KWin 6.7.2**, with Better Blur DX enabled, using live
open/close, minimize/restore, rapid reversal, and close-during-animation checks.
This supersedes the original design's initial Burn-My-Windows exclusion. Recheck
third-party effects after Plasma upgrades; other KWin versions are not verified.

Check the loaded state:

```sh
qdbus6 org.kde.KWin /Effects org.kde.kwin.Effects.isEffectLoaded kwin6_effect_tv_glitch
qdbus6 org.kde.KWin /Effects org.kde.kwin.Effects.isEffectLoaded arasaka_tv_glitch_minimize
```

For a quick fallback, open **System Settings > Animations** and choose **Scale**
for Window Open/Close and **Magic Lamp** for Window Minimize. Reapplying the rice
selects TV Glitch again. Its shared applied duration is set in
`bin/apply-window-effects`; the local minimize effect's Reset default is in its
`contents/config/main.xml`.

## Shader Wallpaper

The wallpaper uses **Heartfelt without the heart sequence**, over the existing
Arasaka/Mikoshi artwork, through
[kde-shader-wallpaper](https://github.com/y4my4my4m/kde-shader-wallpaper).
All existing desktops use 30 FPS, full resolution, 75% shader playback speed, and
pause for maximized/fullscreen windows on their respective screen. Mouse and
audio capture, window-reactive shader input, playlists, and buffer passes are
disabled. Only texture channel 0 is enabled.

```sh
./bin/apply-shader-wallpaper --install-only
./bin/apply-shader-wallpaper
```

Run as the desktop user, without `sudo`. The first command builds, validates,
backs up, and installs artifacts without any live session calls. The default
command does the same work and then applies only `plasma/shader-wallpaper.js`
through Plasma's D-Bus scripting API. It requires a nonempty set of existing
desktops with valid screen IDs, including the primary screen; one or more
desktops are supported. Parked containments with screen `-1` are left untouched.
It maps the external-preferred primary connector using
`kscreen-doctor --json` and `lib/arasaka_topology.py`. It does not reconfigure
outputs, change launchers/panels, deploy runtime layout policy, or restart Plasma.

Build prerequisites are Python 3.12+, CMake 3.22+, a C++20 compiler, KDE ECM and
Frameworks 6 development packages (Config, I18n, Package), Plasma/PlasmaQuick
development packages, Qt 6.6+ (Core, Quick, Qml, Gui, OpenGL, Network, Multimedia,
DBus), and `pkg-config`. Runtime/build tooling also needs Bash, `curl`,
`sha256sum`, `patch`, and `rsvg-convert`; activation additionally needs `qdbus6`
and `kscreen-doctor`. Optional native dependencies follow upstream CMake checks.
No dependency packages are installed automatically. Builds default to at most
four parallel jobs; set `ARASAKA_SHADER_BUILD_JOBS=2`, for example, to lower that
limit or explicitly choose another positive job count.

The installer uses `fetch-components` and the immutable SHA-256-pinned archive
in `manifest/components.tsv`. CMake configures and builds extracted temporary
source, not the upstream checkout or live home. Neither upstream `build.sh` nor
`cmake --install` is executed. The complete package, including the native plugin
embedded under `contents/ui/shaderwallpaper/`, is deployed to
`${XDG_DATA_HOME:-$HOME/.local/share}/plasma/wallpapers/online.knowmad.shaderwallpaper`.
Its relative QML import needs no system or separate user QML-module installation.

The tracked inputs are `assets/wallpapers/mikoshi-16x9.svg`,
`assets/wallpapers/mikoshi-16x10.svg`, and
`assets/wallpapers/shaders/heartfelt-no-heart.patch`. Installation renders
1920x1080 and 1600x1000 PNGs into `$XDG_DATA_HOME/wallpapers/Arasaka/`, using the
same data-home fallback above. It copies upstream `Heartfelt.frag` to a separate
`shaders/Heartfelt_No_Heart.frag` there and applies the patch with `-p1`, preserving
the original author/license header. The packaged upstream shader is untouched.
Background fog uses cubic B-spline filtering across adjacent mip levels, with a
one-level bias toward finer detail. This reduces blur modestly and avoids the
visible mip-grid corners produced by the original single linear sample as fog
increases. Rain, trails, and refraction retain their original timing. Lightning
skips alternate burst windows without changing the remaining flashes' duration
or intensity: roughly one burst every 34 seconds of active playback at 75% speed.
Generated PNGs and the complete upstream shader are not committed to this repo.
The shader and artwork are configured with escaped, absolute `file://` URLs.

The gallery also offers **Tokyo** (`Xtf3zn`, Reinder Nijhoff) and **Dusti [237
Chars]** (`tcXXDB`, HellMood). These are selectable alternatives, not changes to
the default no-heart selection. The installer fetches their immutable raw
resources through `fetch-components`, strips Tokyo's UTF-8 BOM, and extracts
Dusti's single Image pass from the archived API JSON. Both are installed under
the package's `contents/ui/Shaders/` as `Tokyo.frag` and `Dusti.frag`. Tokyo's
executable code and both shaders' original credits are preserved. Dusti receives
the alpha-only adapter described below. Added attribution and
`// @channels none,none,none,none` headers prevent artwork/audio channel routing
from carrying over when selected. Neither shader requires textures or buffers.

The staged `shader_index.json` retains its upstream entries and gains credited
entries for Tokyo, Dusti, and **Heartfelt No Heart**. The no-heart entry points to
the external custom shader above and declares that it needs a texture, not audio.
License information is included in descriptions as well as import headers;
upstream may discard the additional JSON `license` field when resaving its index.
Tokyo retains its original letterbox bars. Before adding the import header, the
installer applies the required `assets/wallpapers/shaders/dusti.patch` with `-p1`
to the staged original `Dusti.frag`. It adds only `O.a = 1.0` after the active
shader's RGB calculations, leaving those calculations unchanged. GPU smoke checks
found the original all-white/static and the opaque-alpha variant visibly animated;
PS3 and Heartfelt baselines passed. Upstream's uninitialized local variables remain
a portability risk on other drivers. Missing or failed patches prevent deployment.
See `ATTRIBUTION.md` for
the separate noncommercial/share-alike licenses and Dusti's archived evidence.

Before replacement, the command prints a private backup directory under
`${XDG_STATE_HOME:-$HOME/.local/state}/arasaka-kde/backups/shader-wallpaper-*`.
It saves existing `plasma-org.kde.plasma.desktop-appletsrc` and `plasmashellrc`,
the previous `package/`, replaced PNGs and custom shader under `artwork/`, and
the existing `$HOME/.local/libexec/arasaka-kde/layout.js` under `runtime/`.
Symlinked targets, their parents, and backup sources are refused. A failed build,
patch, or artifact validation leaves the previous package, artwork, and Plasma
configuration untouched. Backups may contain personal settings; keep them local.
This is not an automatic transactional rollback system.

Package replacement retains files absent from the new package under
`contents/ui/Shaders/` and `Shaders6/`, including unindexed imports and complete
custom bundle subdirectories with buffers/resources. Saved gallery entries and
custom categories are carried forward; matching relative paths, absolute paths,
and local `file://` URLs retain their IDs, favorites, and thumbnail references.
Tokyo, Dusti, and the generated external no-heart shader remain managed and are
updated rather than restored from old copies. Conflicting non-managed files
(including edits to bundled shaders), file/directory collisions, and duplicate
gallery IDs cause refusal before replacement, not silent overwrite. Preserve or
rename the conflicting custom shader before retrying. Other package locations
are replaced as before and remain available in the complete package backup.
`--install-only` leaves the active shader selection and Plasma configuration alone.

Activation requires an explicit success marker with JSON readback of the plugin,
paths, and configuration on every target desktop. That verifies configuration, not GPU
rendering or pause behavior. If Plasma has cached a previous native plugin/QML
or has not discovered the new package, explicitly restart Plasma or log out/in
and rerun the command. The installer never performs that restart automatically.
For recovery, stop Plasma first, restore the saved configuration and affected
package/artwork from the backup preceding the unwanted change, then start Plasma.
Restore runtime policy only when undoing a separate integration change; this
scoped installer backs it up but does not modify it. A snapshot's absence means
that source did not exist before installation. Preserve unrelated artwork and
runtime files. Full deployment and display reconciliation own persistent layout
policy separately from this scoped installer.

The opt-in GPU check can isolate the blur's edge response, verify that alternate
lightning bursts are absent and retained flashes are unchanged, and capture
light/heavy fog at fixed animation times, including a simulated hour of playback:

```sh
python3 tests/shader_smoke.py --blur-check \
  --package "$HOME/.local/share/plasma/wallpapers/online.knowmad.shaderwallpaper" \
  --shader "$HOME/.local/share/wallpapers/Arasaka/shaders/Heartfelt_No_Heart.frag" \
  --texture "$HOME/.local/share/wallpapers/Arasaka/mikoshi-16x9.png" \
  --screenshot /tmp/heartfelt-blur
```

This requires the Qt Quick Test runner, a working OpenGL session, and awake
displays. It uses isolated settings and does not change the desktop wallpaper.

## Development

Run all shell and Python tests:

```sh
make test
```

The Makefile also lists the following **planned, currently unimplemented**
operational entry points:

```sh
make doctor
make dry-run
make apply
make rollback SNAPSHOT=<snapshot-id>
```

See `docs/superpowers/specs/2026-09-04-arasaka-kde-rice-design.md` for the approved design and `docs/superpowers/plans/2026-09-04-arasaka-kde-rice.md` for the implementation plan.
