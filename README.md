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
