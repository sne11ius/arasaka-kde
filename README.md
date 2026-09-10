# Arasaka KDE

Arasaka KDE manages a KDE Plasma 6 rice for TUXEDO OS. The repository is intended
to be the source of truth for the whole rice: authored assets, pinned upstream
components, local adaptations, and scoped installation/configuration commands.
Keep accepted visual changes here rather than only in the live home directory.

Do not commit complete personal configuration directories, browser profiles,
signing keys, caches, or runtime window/monitor state. Capture the settings needed
to reproduce the appearance instead.

## License

Copyright (c) 2026 Arasaka KDE contributors.

Except where file notices, component metadata, or [ATTRIBUTION.md](ATTRIBUTION.md)
specify otherwise, original project code, configuration, documentation, and artwork
are licensed under the **European Union Public Licence v1.2 (EUPL-1.2)**.
The complete official English text is in [LICENSE](LICENSE).

Existing component licenses and third-party terms remain in effect, including
MIT, CC0, GPL, and the shaders' noncommercial/share-alike licenses. Adding the
EUPL does not relicense those materials. See [ATTRIBUTION.md](ATTRIBUTION.md) for
the scope, credits and exceptions, and [LICENSES/](LICENSES/) for additional texts.

## Apply

The current deployment command is:

```sh
./bin/apply-live
```

Run it as the desktop user inside the target Plasma session. It changes the live
desktop, installs assets, builds and applies the shader wallpaper, and configures
applications. It requires the shader build prerequisites listed below and assumes
the required fonts, applets, Kvantum theme, and native KWin plugins are already
installed. Full dependency provisioning is still unfinished.

**There is no full-desktop dry-run or transactional snapshot/rollback implementation yet.**
`apply-live` does not accept a `--dry-run` flag. Existing backups are component
specific, not a complete desktop recovery system.

## Login Screen

**Current status (2026-09-07): PLM is installed, selected, and running.**
After the user-run installation and reboot, service state and logs confirmed the
existing account entered Plasma Wayland; the user confirmed the login appearance.
SDDM remains installed but disabled for recovery. The user runs privileged
commands directly; agents must not invoke `pkexec`.

This migration targets TUXEDO OS on Debian testing/forky, amd64, with Qt 6.10.2,
Frameworks 6.28 and Plasma 6.7. It does not import Neon packages or repositories.
PLM uses its own login UI, not the retained SDDM Arasaka QML theme. The login
background is independently configured as Heartfelt No Heart at 30 FPS, 75%
speed, full resolution, with the 16:9 Mikoshi texture and `pauseMode=3`.
Autologin stays disabled. Desktop shader selections, per-screen textures, window
pausing, gallery/favorites, launcher, KWin, and lock screen are left alone.

The login clock is disabled with `[Greeter] ShowClock=false`; this does not change
the lock-screen clock. `apply-plm` includes it in new installations. On the current
installation, the setting is in the root-owned, mode-644 file
`/etc/plasmalogin.conf.d/arasaka-clock.conf`. Its separate location leaves the
original migration-managed configuration and rollback snapshot unchanged.
Configuration readback confirms `false`; the clock-free appearance takes effect
when the greeter next starts and has not yet been visually confirmed.

To apply that preference to an existing installation without rerunning migration:

```sh
sudo install -d -m 755 /etc/plasmalogin.conf.d
sudo kwriteconfig6 --file /etc/plasmalogin.conf.d/arasaka-clock.conf \
  --group Greeter --key ShowClock --type bool false
sudo chmod 0644 /etc/plasmalogin.conf.d/arasaka-clock.conf
```

The final permission step is required because `kwriteconfig6` creates new files
as root-only. Do not restart the display manager from the running desktop.

Build unprivileged:

```sh
./bin/build-plm
```

The outputs are `build/plm/plasmalogin_6.7.4-0arasaka1_amd64.deb` and
`build/plm/arasaka-login-wallpaper_1.0-1_amd64.deb`, alongside `inventory.json`,
package metadata, file lists and inspected maintainer scripts. `--plm-only`
builds just PLM. The official 6.7.4 archive is SHA-256-pinned in the manifest;
builds use `DEB_BUILD_OPTIONS=nocheck` and `BUILD_TESTING=OFF`. No tests or
synthetic greeter previews are part of this migration.

Build dependencies are declared in `packaging/plasmalogin/debian/control`; also
install `build-essential`, `dpkg-dev`, and the shader prerequisites below.
`systemd-dev` is required in addition to `libsystemd-dev`. Build tools never
install dependencies. Simulate dependency changes first and do not proceed with
desktop removals/upgrades. The user installed the build dependencies. The login
transaction installed the two local packages, `plasma-keyboard` and
`qt6-virtualkeyboard-plugin`, without upgrades/removals.

For a fresh SDDM-to-PLM migration, run this yourself **as the desktop user inside
Plasma Wayland, without a leading `sudo`**. Do not rerun it on this already
migrated machine:

```sh
./bin/apply-plm --skip-build
```

`--skip-build` uses and re-inspects the existing artifacts, not unverified files.
Without it, the command rebuilds both packages first. `--baseline` preserves the
private audit record supplied as a path and dependency history; omit it to create a new
baseline. The recorded pre-dependency installed-package inventory was explicitly
reconstructed from APT history because the user installed dependencies before
the original complete snapshot. A fresh invocation captures its own desktop/file
digests and reports differences from historical observations without resetting
user settings. Changed shader appearance requires review before continuing.

The command prints and invokes a scoped `sudo` installation step after
unprivileged preparation. Before installing, it creates a root-owned mode-700
backup under `/var/backups/arasaka-kde/plm-*`, including selectors, relevant
configuration, package inventories and executable standalone `rollback.sh`.
The current protected backup is `/var/backups/arasaka-kde/plm-q3fl2q9u`.
APT rechecks the transaction and installs explicit protected copies of the two
packages. Package maintainer scripts do not start, stop, enable, or select a
display manager. The controller verifies account/PAM/assets and configuration,
then coordinates debconf, `/etc/X11/default-display-manager`, and the systemd
alias for the next boot. It never stops SDDM or reboots the session.

The system wallpaper package owns
`/usr/share/plasma/wallpapers/online.knowmad.shaderwallpaper/`, including its
embedded native QML module, and `/usr/share/wallpapers/Arasaka/`. These root-owned
assets need no private-home access. The existing user-local plugin keeps its
normal precedence for desktop sessions. The package preserves upstream licenses,
shader headers, gallery attribution and local adaptation patches.

To refresh only the login artwork and shader after migration, preserve the
previously installed wallpaper `.deb` for asset rollback before rebuilding. The
existing builder produces both packages, but install **only**
`arasaka-login-wallpaper`; do not reinstall PLM or rerun `apply-plm`:

```sh
./bin/build-plm
apt-get --simulate --reinstall --no-remove --no-install-recommends install \
  ./build/plm/arasaka-login-wallpaper_1.0-1_amd64.deb
```

Proceed only if the simulation proposes one wallpaper-package reinstall, with no
other package installations, upgrades, or removals. Run the privileged step
yourself:

```sh
sudo apt-get --reinstall --no-remove --no-install-recommends install \
  ./build/plm/arasaka-login-wallpaper_1.0-1_amd64.deb
```

The explicit local package and `--reinstall` are needed because its version stays
`1.0-1`. It has no maintainer scripts or configuration files and does not restart
the login manager. PLM's existing `/usr/share` paths load the colorful artwork and
reduced-lightning shader at the next normal greeter start. Desktop and lock-screen
assets are user-local and updated separately; login authentication, clock settings,
and session configuration are unchanged. Do not restart PLM from the running
desktop. To undo just an asset refresh, reinstall the saved previous wallpaper
package rather than using the SDDM migration rollback below. Back up any local
modifications to package-owned system assets separately before reinstalling.

For this installation, the standalone TTY recovery command is:

```sh
sudo /var/backups/arasaka-kde/plm-q3fl2q9u/rollback.sh
```

With the checkout available, `./bin/apply-plm --rollback BACKUP` accepts that same
backup path. A different migration has its own printed path. Recovery restores
selectors and migration-owned configuration,
not user settings, and leaves packages installed. PLM is disabled for the next
boot; the running service is unchanged. If PLM is already running, you must
explicitly reboot to return to SDDM. Keep SDDM and its theme installed. This is a
one-shot migration: pre-existing or partially installed PLM packages/accounts
require inspection, not a forced rerun or autoremove.

The current migration has crossed the reboot boundary and successful login was
observed. Standalone rollback has not been exercised. Future migrations must still
distinguish next-boot selection from actual login and rendering. Do not run
`apply-live`, `apply-launcher`, or desktop shader activation as part of migration.
See `TODO.md` for the completion record and remaining clock-appearance check.

## Lock Screen

The Plasma lock screen is configured independently from PLM to use **Interactive
Rain with passive mouse hover and no clock/date**. It uses the same current rounded,
merging droplets as the desktop, the user-local shader plugin and 16:9 Mikoshi
texture at 30 FPS, 75% speed and full resolution. Window-based pausing is disabled
for this surface (`pauseMode=3`). Mouse permission is enabled; audio, window-reactive
inputs, playlists, source watching and buffer passes remain off. Desktop settings
and gallery contents are not changed.

Only committed native Rain may observe button-free pointer motion inside the
locker's own wallpaper window. The observer never consumes buttons or keyboard
events, grabs input, changes focus, reads password text or polls the global cursor.
The desktop behind a locked session still rejects rain input. Ordinary lock-screen
shaders and all PLM/login shaders retain their input restrictions; global cursor
tracking and the stock MouseArea stay disabled on both greeter roles.
Mouse permission also stays off before attachment and classification. The wallpaper
publishes the attached window and roles together only for recognized desktop, lock
or login sources; missing/unknown sources fail closed. Detach, reparent and source
changes revoke that permission before reclassification, cancelling pending input
without a delay or timer. The settings mini-preview uses its own input-disabled
renderer and does not participate in this host handoff.

To apply only this appearance, run as the desktop user without sudo:

```sh
./bin/apply-lockscreen
```

The command requires the already-built user-local shader package and artwork,
`kreadconfig6`, `kwriteconfig6`, Python 3 and `ldd`. It inspects the installed native
module, dependencies and configuration schemas before writing. It requires the
exact native-rain shader marker and generated native metadata declaring the writable
boolean `ShaderEngine.rainLockScreenHost`; an old renderer is rejected before any
configuration writes. Install the updated package before running this command.
It stages and reads
back the proposed appearance, then uses KConfig's locking/merge writer to update
only the managed keys in `kscreenlockerrc`, selecting the wallpaper plugin last.
It does not rebuild or replace assets, alter authentication/lock timing, change
PLM, edit lockscreen QML, force a lock, or restart anything.

The locker uses `[Greeter] WallpaperPlugin`, not PLM's `WallpaperPluginId`.
Shader values live under
`[Greeter][Wallpaper][online.knowmad.shaderwallpaper][General]`; the installed
Silent lockscreen hides its clock and date with
`[Greeter][LnF][General] alwaysShowClock=false`. Existing `[Daemon]` settings and
the static-image configuration remain intact. Full `apply-live` calls this same
scoped command after the desktop shader and lockscreen theme have been installed.

Before writing, the command saves `kscreenlockerrc` privately under
`${XDG_STATE_HOME:-$HOME/.local/state}/arasaka-kde/backups/lockscreen-*` and prints
the path. The current backup is
`$HOME/.local/state/arasaka-kde/backups/lockscreen-20260907-225436-v6rjgj9j/`.
For a shader-only fallback without restoring potentially stale lock-policy values:

```sh
kwriteconfig6 --file kscreenlockerrc --group Greeter --key WallpaperPlugin org.kde.image
```

The next normal lock-screen start loads this configuration and the new native
module. A guarded host binding also permits updated shared QML to load in an
already-running desktop that still has the preceding native module cached; no
desktop restart is required. The host role is not a persisted configuration key.
Native input, real host QML and private KConfig fixture tests cover this behavior,
not authentication. Live lock-screen rendering, hover delivery and clock absence
still need observation at a normal user-initiated lock; no lock, authentication
preview or live configuration change is part of these tests.
The native renderer requires OpenGL; this command does not override global Qt
settings or disable the locker's software-rendering crash recovery.

## Launcher

The launcher replaces the managed top bar and laptop rail with a desktop-hosted
native QML popup. There are no managed bars or hidden edge panels. Press **Super**
to open a compact, focused application search on the **main display**, regardless
of pointer or active-window location. Every opening starts with an empty field,
a **Full Menu** button, and the native system tray below. Typing reveals up to six
rows of matches before scrolling; arrow keys select a match and **Enter** launches
it and closes the popup. The six-row results area stays reserved even when empty,
so typing, changing matches, and clearing the query never move the search field
or tray. An empty search shows no favorites or suggestions.
**Escape** or pressing **Super** again dismisses it.

**Full Menu** expands the same popup into KDE's stock Kickoff, including favorites,
application categories, locations, and session actions. **Back to Search** restores
the compact view and its query. The tray stays below either view, including native
tray submenus. Compact search uses KDE's application runner (`krunner_services`),
not file, browser-history, calculator, or shell-command providers; native app
actions can also appear. This requires the application runner to remain enabled
in KDE's search settings. Its private Kicker API is verified on Plasma 6.7.2 and
should be rechecked after Plasma upgrades. Kickoff and the tray are embedded stock
applets, not copied implementations. Unmanaged panels are not removed. The layout requires
the loaded host to acknowledge the current Plasma session token before removing
managed panels; a saved `ready=true` alone is not sufficient.

Activation uses Plasma's existing **Activate Application Launcher** shortcut.
Another launcher on a preserved unmanaged panel can take precedence under KDE's
normal routing rules. The installer does not overwrite other shortcut bindings.
The popup keeps its original desktop owner to avoid Plasma 6.7's embedded-widget
configuration migration bug. The display reconciler supplies the primary
connector, which the popup resolves on each opening; it does not assume Qt's
screen order matches KDE's output priority on Wayland. An existing host can be
retargeted while Plasma is still assigning desktops to screens; only creating a
new host requires an available primary desktop in the current activity.

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
`shader-wallpaper.js`, and the currently required `Arasaka.json` in
`$HOME/.local/libexec/arasaka-kde/`. It runs the display reconciler with `--force`,
retrying failures for up to roughly ten seconds, and independently checks live
host readiness and managed-panel removal. Failure is reported, not treated as
successful installation. This is not the full `apply-live`: it does not install
themes, change window effects or application settings, or generate wallpapers.
Layout and display-priority reconciliation still run, but wallpaper and desktop
icon settings are preserved. Full-theme deployment and its automatic display
watcher opt into `--hide-desktop-icons --ensure-shader-wallpaper`: icons are
hidden, and active desktops not yet using the shader plugin receive Interactive
Rain defaults with hover enabled. Existing shader selections and settings are
preserved.

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
newly installed launcher package or the five runtime files, leaving unrelated
runtime files alone. After restoring, remove the corresponding
`arasaka-kde/launcher-restart.json` marker from the state directory. Start Plasma
again and resume the watcher only if it was active before. Do not overwrite
Plasma configuration while the shell is running: it can overwrite the restore.

Installer behavior is tested with temporary homes and stub session tools. Run the
opt-in native integration test inside a Wayland session:

```sh
python3 tests/launcher_smoke.py
```

It uses isolated settings and a private D-Bus session, briefly displaying compact
search, the real Kickoff, and the tray. It checks readiness acknowledgements,
placement, keyboard and mouse launching, scrolling, query replacement and pending
launch cancellation, switching views, tray interaction, reopening, Escape, and
focus-loss dismissal. Temporary desktop entries launch only marker-file commands;
the test also requires `kbuildsycoca6` to index these fixtures.
The clipboard applet requires a real window system; Qt's offscreen backend is not
supported. Missing-service warnings in the isolated bus are expected.

Live checks on Plasma 6.7 confirmed activation through the action bound to Super,
centered open/close/reopen, no remaining panels, unchanged wallpaper/icon policy,
and stable host identity after reapplying. Physical monitor unplug/replug and
fresh login with the original owner display disconnected remain manual checks.

## Window Tiling

Application windows and dialogs now use **forced automatic tiling**. The managed
Polonium adaptation keeps **Binary Tree / Shallow** insertion, **Swap Insert Side**,
and **8 logical px padding**. New windows split the least-deep branch, with the
third window splitting the right half and the fourth splitting the left. Placement
is independent of focus; rotation and active-tile insertion are disabled.

**Dragging between displays is supported.** Grab the title bar or use
**Super+left-drag**; while dragging, the window is temporarily released from its
tile. On drop it joins the destination display's automatic layout. A same-display
drop also retiles, and cancelling a drag restores the original display. Mouse
resizing is cancelled inside KWin. Maximize, fullscreen, manual untiling and the
old floating toggle cannot leave an ordinary window outside the layout.
Minimize/restore and close remain available. **Super+H/J/K/L** focuses
adjacent tiles, **Super+Shift+H/J/K/L** rearranges windows, and
**Super+Ctrl+H/J/K/L** resizes shared tile boundaries. The per-output settings menu
and alternative layout engines are disabled for this managed policy.

**GeForce NOW is allowed to enter fullscreen.** Its `GeForceNOW` application
window leaves the tiling layout while fullscreen and automatically rejoins it
when fullscreen ends.

Display removal/reconnection rebuilds the automatic trees from current window
membership. Output identity is checked against KWin's live outputs, including
when a connector returns with a new native object after resume. Retired tile
callbacks are disconnected. A failed output rebuild is contained and event
processing always releases its busy flag, so one exception cannot permanently
disable subsequent tiling updates.

**The only floating application window is the Stream Deck Quake Konsole.** The
native helper watches `/tmp/konsole-quake.pid`, verifies ownership and the running
Konsole executable, and selects one non-transient top-level window from that
process. Ordinary Konsole windows and Konsole dialogs still tile. Late PID
registration, minimization, restoration and tiler reloads preserve the exception.
The existing launcher keeps its borderless, always-on-top placement and toggle;
its old Polonium floating-toggle call is now harmless. No title matching or broad
Konsole-class exclusion is used. Menus, tooltips, desktop surfaces and other
non-application surfaces are not layout tiles.

Applications use their **native decoration preference**: client-decorated apps
keep their own controls, while apps such as Dolphin receive KDE's title bar.
The former catch-all `arasaka-frame` rule is retired (`noborderrule=0`): even
**Apply Initially** with `noborder=false` forced an extra server decoration onto
client-decorated applications. The old Klassy titlebar-hiding exception stays
disabled. Thin outlines remain off. Fixed-size windows, including pinentry, get
a larger maximum-size allowance so KWin accepts their tile membership; their
minimum content sizes remain respected.

Apply just this policy inside the target Plasma session, without sudo:

```sh
./bin/apply-window-policy
```

`apply-live` calls the same command. It fetches the SHA-256-pinned Polonium v1.2.1
package, applies `lib/arasaka_polonium.py`, builds `native/window-policy/`, and
installs `${XDG_DATA_HOME:-$HOME/.local/share}/kwin/scripts/arasaka-polonium`.
The upstream `polonium` package remains installed but disabled. Managed settings
live in `[Script-arasaka-polonium]` in `kwinrc`; old upstream exclusions do not
override forced tiling. The helper needs a C++20 compiler, CMake, ECM, KWin headers
and library, Qt 6 Quick/DBus/Widgets development packages, and KF6 Config and
WindowSystem development packages. Deployment also requires Python 3, KDE KConfig
tools, `qdbus6`, and `kpackagetool6`; dependencies are not installed automatically.

Before replacing anything, the command builds and validates the package, then
prints a private backup under
`${XDG_STATE_HOME:-$HOME/.local/state}/arasaka-kde/backups/window-policy-*` containing
`kwinrc`, `kwinrulesrc`, `klassy/klassyrc`, and the previous managed package if any.
It reloads the tiler and rebuilds existing layouts, without restarting KWin,
Plasma or applications. Versioned runtime paths and native module names avoid
stale QML/plugin caches. Completion requires the running helper to report the
expected source versions and all visible application windows in the requested
state. Inspect its read-only report with:

```sh
qdbus6 org.kde.KWin /ArasakaWindowPolicy org.arasaka.WindowPolicy1.report
```

For a fallback, disable `arasaka-polonium` and re-enable `polonium` in KWin Scripts,
or restore the saved settings and managed package, then reconfigure KWin. Restoring
the retired frame rule also restores its duplicate-decoration behavior.

Build and run the opt-in integration checks in a private virtual KWin session:

```sh
./bin/apply-window-policy --stage-only /tmp/opencode/policy-package
python3 tests/window_policy_smoke.py /tmp/opencode/policy-package
```

The staging directory must be empty/nonexistent. The tests use disposable Qt
windows, a fixed-size dialog, a real pinentry confirmation (no credentials), and
a separate disposable Konsole. They check decorations, actual tile membership,
cross-display dragging on two virtual outputs, same-display drops and cancellation,
resize/maximize/fullscreen rejection, minimize/restore, manual detach, all-activity
windows, PID validation and registration, and reloads with existing/minimized windows. Test
artifacts remain under `/tmp/opencode/window-policy-*`; the live home and session
are not used. The suite also removes and recreates a virtual output twice,
checking that occupied outputs have no empty tile branches and that later window
events still work. KWin 6.7.4's isolated compositor and the running 6.7.2 session have
identical window/workspace API headers for this helper.

`python3 tests/polonium_controller_test.py` runs the adapted pinned controller and
layout engine under Node.js, with the native KWin boundary simulated. It covers
retired output references, exception recovery, same-name output recreation,
topology/event ordering, and callback cleanup across repeated hotplug. This test
also runs under `make test` and requires Node.js and the component fetch tools.

Applied in the live session on 2026-09-10. Readback confirmed the existing Quake
process remained the sole floating application while Firefox, Mattermost, Edge
and Telegram were tiled. Live disposable SSD/CSD windows and a fixed-size dialog
also enrolled and the layout reconverged after closing them. The two-output
isolated suite passed cross-display dragging, same-output drops and cancellation.
The original pre-policy backup is
`$HOME/.local/state/arasaka-kde/backups/window-policy-ldr9wud3/`; later reapply
backups contain already-managed settings.

A later suspend/resume on 2026-09-10 exposed a retired-output reference that
stalled Polonium's event gate and left stale/untiled windows. The topology and
event-cleanup repair above was deployed that evening. Seven controller
regressions and all fifteen isolated KWin checks passed; live readback confirmed
visible application windows tiled with no empty branches on either occupied
display. The repair backup is
`$HOME/.local/state/arasaka-kde/backups/window-policy-gqnr2kik/`.
Physical suspend/resume remains a check at the next normal user-initiated sleep;
the automated suite exercises real output destruction/recreation in isolation.

## Authentication Prompts

GPG PIN/passphrase (`pinentry-qt`) and KDE SSH (`ksshaskpass`) prompts are forced
into KWin's keep-above layer and cannot be kept below other windows. The rule
matches their Wayland app IDs and XWayland resource classes, for both normal
windows and dialogs. Newly opened prompts can appear above the Stream Deck Quake
Konsole without disabling its always-on-top behavior. This does not change the
global focus policy or make prompts permanently outrank every always-on-top window.

To apply only this policy in the running Plasma session:

```sh
./bin/apply-auth-window-rules
```

`apply-live` also calls this command. It preserves existing window rules and
legacy upstream Polonium exclusions, saves `kwinrulesrc` and `kwinrc` under
`${XDG_STATE_HOME:-$HOME/.local/state}/arasaka-kde/backups/auth-window-rules-*`,
and reloads KWin's rules without restarting Konsole or Polonium. Keep these
backups local because they can contain personal settings.

Stacking changes apply immediately. Under the managed forced-tiling policy above,
these prompts **tile like other dialogs**; the old upstream Polonium exclusions
are inactive. The standalone authentication command only reloads window rules.
No key-agent, credential-storage, or SSH/GPG security settings are changed.

Verified in the live Plasma session on 2026-09-08 with auto-closing confirmation
dialogs from both helpers on Wayland and XWayland: all four opened above the
existing keep-above Konsole. No real credentials or keys were used.

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
`theme/kwin/effects/arasaka_tv_glitch_minimize/` handles minimize/restore and popup
show/hide using the same shader, including rapid-toggle reversal and animation
cleanup. Regular windows retain 700 ms; the launcher, tray flyouts, menus,
dropdowns, and tooltips use 300 ms. This covers separate KWin windows, not menus
drawn inside an application's window. Popup Fade and Sliding Popups are disabled
to avoid competing animations; lock-screen surfaces and outlines are excluded. The overlay
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
selects TV Glitch again. Window and popup durations are set in
`bin/apply-window-effects`; the local effect's defaults are in its
`contents/config/main.xml`.

## Shader Wallpaper

The managed desktop default is **Interactive Rain**: native simulated droplets
fall, merge, refract the Arasaka/Mikoshi artwork, and leave trails through fog.
Move the pointer over exposed desktop space to influence nearby drops with passive
hover. **Left-click a drop to splash it:** a small fingertip margin makes targeting
forgiving, and the nearest cap breaks into roughly 3–8 uneven droplets that scatter
outward, refract the artwork, and leave wet trails. Fragments conserve the original
water and inherited momentum, merge into drops they hit, and push them into motion.
Friction slows the spray and gravity pulls larger drops downward. Each press makes
one burst, including the second press of a double-click; holding does not repeat it.
Clicks on clear glass do nothing. Very small drops, cramped edges, and scenes at the
1,024-drop limit receive a nudge; limited remaining capacity produces fewer fragments.
Desktop clicks continue through to Plasma normally. Splashes use unmodified left
presses on the desktop; the lock screen retains its passive hover interaction.
Merging drops retain their visible lobes, form a smooth liquid neck, and pull into
one rounded cap over roughly a quarter-second at the managed playback speed.
Small drops are absorbed faster. This also applies to splash-fragment impacts;
clicking a drop mid-merge targets its visible lobes and breaks up the whole body
without leaving solid ghost drops. Physical water and momentum combine once at
contact, while a bounded four-lobe surface handles the brief optical transition.
Successive collisions start from the current shape. Animation time and wet trails
follow playback, so pausing freezes the merge as well as the rainfall.
It adapts BigWings' Heartfelt through
[kde-shader-wallpaper](https://github.com/y4my4my4m/kde-shader-wallpaper).
**Heartfelt No Heart remains a separate gallery effect and the unchanged PLM/login
selection.** The separately scoped `apply-lockscreen` command selects Interactive
Rain with passive hover for the lock screen; installing desktop assets alone does
not change its saved appearance or any authentication settings.

Both wallpaper aspect ratios use illuminated crimson/coral architecture, cyan
light channels, and small amber accents. Broad colored midtones extend through
the center and screen edges so the 8 px tiling gaps remain distinct from dark
windows, even under fog. The emblem, grid, and scanlines remain; application and
window palettes are unchanged.
Managed desktop activation targets 30 FPS, full resolution, 75% shader playback
speed, and pauses for maximized/fullscreen windows on each respective screen.
Mouse input is explicitly enabled for hover and desktop splashes; audio capture,
window-reactive shader input, playlists, and generic A-D buffer passes remain
disabled. Only texture channel 0 is enabled. The native rain field is independent
of those buffer passes.
Selecting Interactive Rain from the gallery does not enable mouse input: with
mouse disabled, physical rainfall continues without hover forces or click splashes
until you enable the existing mouse setting. No new settings UI is required.

This is the only managed desktop wallpaper implementation. `apply-live` calls
`apply-shader-wallpaper` once to build, back up, install, and activate the same
Interactive Rain defaults, including rendering the PNGs used by the shader and
static fallback. A shader installation/activation failure stops deployment
rather than selecting another wallpaper.

Launcher-only application leaves wallpaper selections alone. The full-theme
display watcher initializes active non-shader desktops automatically, including
newly created or reconnected desktops, while preserving existing Tokyo, Dusti,
Heartfelt, or custom shader settings. It checks coverage of every enabled output
before recording success and retries if Plasma has not created a desktop yet.
This lightweight step uses installed assets, without rebuilding the plugin or
restarting Plasma. It also resumes interrupted managed rain initialization, but
only while that pending target's managed settings are unchanged. Wallpaper setup
requires the native plugin, both `Heartfelt_No_Heart.frag` and
`Interactive_Rain.frag`, and the artwork. If any asset is unavailable, the runtime
warns and defers only wallpaper setup: launcher layout and icon reconciliation
continue without changing any wallpaper selection or input permission. This keeps
launcher-only updates and an interrupted/failed full-theme build safe on older
installations. Every watcher run rechecks readiness, even with unchanged topology;
once the assets are installed, the normal two-phase wallpaper initialization resumes.
Full-theme or standalone shader reapplication still selects
Interactive Rain again with hover enabled, without discarding the gallery.

```sh
./bin/apply-shader-wallpaper --install-only
./bin/apply-shader-wallpaper
```

For independent system packaging, `./bin/apply-shader-wallpaper --stage-only DEST`
exports to an absolute empty/nonexistent directory with final `/usr/share` URLs.
It is mutually exclusive with `--install-only`, rejects symlinked output paths,
and skips user-gallery merging, home deployment/backups, and all session calls.
It includes the native rain extension and both external effects. `build-plm` uses
this mode without changing PLM's existing Heartfelt No Heart selection.

Run as the desktop user, without `sudo`. The first command builds, validates,
backs up, and installs artifacts without any live session calls. The default
command does the same work and then applies only `plasma/shader-wallpaper.js`
through two separate evaluations of Plasma's D-Bus scripting API. It requires a nonempty set of existing
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

Before CMake configuration, the installer applies
`assets/wallpapers/shaders/interactive-rain-host.patch` at the extracted source
root and copies the six explicit `native/rain/{dropletsimulation,rainfieldrenderer,raininput}.{h,cpp}`
files into `src/rain/`. Missing or symlinked required inputs are rejected during
preflight, including in stage-only mode. The extension is compiled into the existing
GPL native module, not installed as a second plugin.

The artwork inputs are `assets/wallpapers/mikoshi-16x9.svg` and
`assets/wallpapers/mikoshi-16x10.svg`. Installation renders
1920x1080 and 1600x1000 PNGs into `$XDG_DATA_HOME/wallpapers/Arasaka/`, using the
same data-home fallback above. It copies upstream `Heartfelt.frag` to a separate
`shaders/Heartfelt_No_Heart.frag` there and applies `heartfelt-no-heart.patch`.
It then copies that adapted shader to `shaders/Interactive_Rain.frag` and applies
`interactive-rain.patch` only to the copy. All patches use
`--batch --forward --fuzz=0 -p1`; generated rain must retain the upstream license
header, entry point, exact `// @arasaka-effect rain-v1` marker and `iRainField`
sampler. The packaged original and the existing no-heart adaptation are unchanged
by the new patch.

Background fog uses cubic B-spline filtering across adjacent mip levels, with a
one-level bias toward finer detail. This reduces blur modestly and avoids the
visible mip-grid corners produced by the original single linear sample as fog
increases. Heartfelt No Heart retains its procedural rain timing; Interactive Rain
uses native droplet physics, an optical history field, and hover input instead.
Its 1024-drop identity cap limits particles, not incoming water: bounded
active-time condensation grows existing caps fairly, allowing pinned beads to
start sliding naturally. Mostly small births and slow accretion retain several
hundred varied beads alongside fewer large flowing drops. Birth radii and adhesion
scale together with viewport height; pause freezes growth as well as motion.
Moving caps elongate along velocity; downward motion gives them a wider, rounded
lower bulb and a shallower upper film. The upper surface meets the glass gently,
softening its outline and refraction while the thickest water sits in the lower
body. The footprint and height profile preserve area and integrated water volume,
blend through liquid merges, and keep click targeting aligned with the visible
body. Stationary caps remain round. These physical drops do not reproduce
Heartfelt's procedural shapes exactly.
Both adaptations retain the artwork filtering, fog and postprocessing. Lightning
keeps one in four original burst windows at 25% strength, without changing flash
timing or the background's normal brightness. This gives roughly one burst every
67 seconds of active playback at 75% speed: half the previous frequency and
75% weaker flashes, avoiding harsh pulses over the brighter artwork.
Generated PNGs and the complete upstream shader are not committed to this repo.
The shader and artwork are configured with escaped, absolute `file://` URLs.

`python3 tests/wallpaper_artwork_test.py` renders both SVGs and checks blurred
horizontal/vertical gap samples for contrasting color against the dark window
surface. It requires `rsvg-convert` and Python Pillow (`python3-pil` on Debian),
and also runs under `make test`. GPU smoke checks below exercise the actual rain
shader; the artwork check alone does not model its animated lighting.

The gallery also offers **Tokyo** (`Xtf3zn`, Reinder Nijhoff) and **Dusti [237
Chars]** (`tcXXDB`, HellMood). These are selectable alternatives, not changes to
the default Interactive Rain selection. The installer fetches their immutable raw
resources through `fetch-components`, strips Tokyo's UTF-8 BOM, and extracts
Dusti's single Image pass from the archived API JSON. Both are installed under
the package's `contents/ui/Shaders/` as `Tokyo.frag` and `Dusti.frag`. Tokyo's
executable code and both shaders' original credits are preserved. Dusti receives
the alpha-only adapter described below. Added attribution and
`// @channels none,none,none,none` headers prevent artwork/audio channel routing
from carrying over when selected. Neither shader requires textures or buffers.

The staged `shader_index.json` retains its upstream entries and gains credited
entries for Tokyo, Dusti, **Heartfelt No Heart**, and **Interactive Rain**
(`arasaka-interactive-rain`). Both external rain entries point to their separate
files above and declare textures required, no audio and no generic buffers.
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
the previous `package/`, replaced PNGs and both custom shaders under `artwork/`, and
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
Tokyo, Dusti, and both generated external rain shaders remain managed and are
updated rather than restored from old copies, including on a repeat Interactive
Rain installation; their saved gallery identities and favorites survive. Conflicting
non-managed files (including edits to bundled shaders), file/directory collisions, and duplicate
gallery IDs cause refusal before replacement, not silent overwrite. Preserve or
rename the conflicting custom shader before retrying. Other package locations
are replaced as before and remain available in the complete package backup.
`--install-only` leaves the active shader selection and Plasma configuration alone.

Both the installer and display reconciler use the same template in two phases.
`prepare` persists and verifies the safe shader path/code and capture/playlist
opt-outs with mouse off, records `arasakaRainPending=true` in that desktop's
wallpaper `General` group, and requests the plugin selection. Plasma's scripting
setter is cached: the real selection is committed at wrapper cleanup after the
evaluation, not at assignment. Mouse stays off throughout that boundary.

A separate `activate` evaluation uses fresh wrappers to read back the committed
plugin and unchanged prepared settings. Only verified pending targets receive
`mouseEnabled=true`; final settings are checked before clearing the pending marker.
Both evaluations check enabled-output coverage and leave parked desktops alone.
Interruption or an ignored mouse-enable write leaves managed initialization
pending for retry, not falsely complete. A failed pre-selection setting write
does not select the plugin. Ensure-only leaves existing custom shaders and input
permissions alone; if a pending target's managed settings have changed, it cancels
only the pending marker without restoring defaults or enabling input. Returning
to Rain later cannot revive that cancelled opt-in. Explicit reapplication resets
defaults during preparation, but activation never overwrites an intervening edit.

Activation requires an explicit success marker with JSON readback of the plugin,
paths, and configuration on every target desktop. A fresh wrapper after commit
proves the selected host and configuration, not rendered readiness, GPU output,
hover delivery or pause behavior. If Plasma has cached a previous native plugin/QML
or has not discovered the new package, explicitly restart Plasma or log out/in
and rerun the command. The installer never performs that restart automatically.
For recovery, stop Plasma first, restore the saved configuration and affected
package/artwork from the backup preceding the unwanted change, then start Plasma.
Restore runtime policy only when undoing a separate integration change; this
scoped installer backs it up but does not modify it. A snapshot's absence means
that source did not exist before installation. Preserve unrelated artwork and
runtime files. Full deployment delegates shader installation and explicit resets
to this command; display reconciliation handles layout/display priority, opt-in
desktop-icon hiding, and shader initialization on non-shader desktops. Keep the
paired runtime scripts together unless explicitly reverting that policy.

For a retained patched source tree and native test build, run from the repository
root (temporary source/build directories avoid live installation):

```sh
ARCHIVE=$(./bin/fetch-components shader-wallpaper)
UPSTREAM=$(mktemp -d)
BUILD=$(mktemp -d)
tar -xzf "$ARCHIVE" --strip-components=1 -C "$UPSTREAM"
patch --batch --forward --fuzz=0 -p1 -d "$UPSTREAM" \
  -i "$PWD/assets/wallpapers/shaders/interactive-rain-host.patch"
mkdir -p "$UPSTREAM/src/rain"
cp native/rain/{dropletsimulation,rainfieldrenderer,raininput}.{h,cpp} "$UPSTREAM/src/rain/"
cmake -S "$UPSTREAM" -B "$BUILD" -DCMAKE_BUILD_TYPE=Release
cmake --build "$BUILD" --parallel 2
cp "$UPSTREAM/package/contents/ui/Shaders/Heartfelt.frag" "$UPSTREAM/Heartfelt_No_Heart.frag"
patch --batch --forward --fuzz=0 -p1 -d "$UPSTREAM" \
  -i "$PWD/assets/wallpapers/shaders/heartfelt-no-heart.patch"
cp "$UPSTREAM/Heartfelt_No_Heart.frag" "$UPSTREAM/Interactive_Rain.frag"
patch --batch --forward --fuzz=0 -p1 -d "$UPSTREAM" \
  -i "$PWD/assets/wallpapers/shaders/interactive-rain.patch"

python3 tests/apply_shader_wallpaper_test.py -v
bash tests/reconcile_displays_test.sh
python3 tests/rain_simulation_test.py -v
python3 tests/apply_lockscreen_test.py -v
cmake -S tests/native_rain -B build/rain-tests -DRAIN_UPSTREAM_SOURCE="$UPSTREAM"
cmake --build build/rain-tests --parallel 2
ctest --test-dir build/rain-tests --output-on-failure
python3 tests/shader_smoke.py --rain-check --package "$UPSTREAM/package" \
  --shader "$UPSTREAM/Interactive_Rain.frag" --texture assets/wallpapers/mikoshi-16x9.svg \
  --screenshot /tmp/interactive-rain.png
```

The pure physics wrapper needs a C++20 compiler, not Qt/OpenGL. Native GL and QML
checks require Qt development packages, Qt Quick Test and a working exposed
OpenGL test window. `--rain-check` exercises rendering, pause/resume, selection
failure and the desktop/lock/login input role matrix; it cannot be combined with
`--blur-check`. Add `--previous-native /path/to/previous/contents/ui/shaderwallpaper`
to check updated host QML with a copied previous module without modifying that module.
Renderer testing observed animated opaque/nonblack artwork, paused frame stability,
selection failure preservation, and HiDPI behavior in isolated windows, with native
field/input checks on hardware and software GL. These are correctness observations,
not a GPU/frame-time benchmark or proof of live Folder View hover delivery.
The native tests also exercise real Qt clicks at 30 FPS and 75% speed, rendered
fragment separation, fast press/release delivery, passive button forwarding, and
pending-click cancellation across pause, input permission, and host changes.
Wallpaper host tests cover late attachment and whole-container moves between
desktop windows, so secondary/reconnected screens regain hover and click input
after their parent window becomes available, while lock/login roles remain scoped.
Coalescence tests cover intermediate neck/outer-lobe pixels, settling, repeated
impacts, clicking a merging silhouette, splash-fragment absorption, and the full
geometry budget. Isolated caps retain their existing height and optical profile.
The click-splash update was installed on 2026-09-10. After a user-approved Plasma
restart, the shell loaded the new native module and compiled Interactive Rain on
both active displays; the user confirmed the desktop interaction and appearance.
**30 FPS is the configured target, not a measured live guarantee.** Physical
multi-monitor input coverage and live frame times still need dedicated checks;
no automatic Plasma restart or deployment is part of these tests.

After packaging, the read-only gallery test uses the installed/staged package's
actual selection function. Pass paths to its package and external no-heart shader;
an optional third path overrides the default sibling `Interactive_Rain.frag`:

```sh
node tests/shader_gallery_smoke.js "$PACKAGE" "$NOHEART_SHADER" "$RAIN_SHADER"
```

It round-trips Tokyo, Dusti and both rain effects, checks mouse off/on permissions,
keeps audio disabled and verifies that no generic A-D buffers are enabled. It does
not call Plasma or change settings. `make test` runs the noninteractive repository
suite; gallery and GPU checks are opt-in.

The opt-in GPU check can isolate the blur's edge response, verify that three of
every four lightning burst windows are absent and retained flashes use 25%
strength with unchanged timing, and capture light/heavy fog at fixed animation
times, including a simulated hour of playback:

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

Deployment uses the scoped `bin/` commands documented above. Full-desktop
dependency provisioning, diagnostics, dry-run and transactional rollback remain
unimplemented; the Makefile does not expose placeholders for them.

See `docs/superpowers/specs/2026-09-04-arasaka-kde-rice-design.md` for the design and
`docs/superpowers/plans/2026-09-04-arasaka-kde-rice.md` for the implementation plan.
