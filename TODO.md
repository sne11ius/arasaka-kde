# PLM Migration Status

## Resume Here

PLM and the independent login shader are installed and active. The user completed
installation and reboot, then confirmed the login appearance. Read-only service
and journal inspection confirmed PLM runs and the existing account entered Plasma
Wayland. SDDM remains installed but disabled. No migration rerun is needed.

The user installed the dependencies and requires privileged commands to be
provided for them to run directly. **Do not invoke `pkexec`.** The protected backup
is `/var/backups/arasaka-kde/plm-q3fl2q9u`; its standalone TTY recovery command is:

```sh
sudo /var/backups/arasaka-kde/plm-q3fl2q9u/rollback.sh
```

Recovery changes next-boot selection, not the running service. If needed, run it
from a TTY and reboot when ready. No rollback has been exercised.

The user requested removal of the login clock. `ShowClock=false` is now readable
in `/etc/plasmalogin.conf.d/arasaka-clock.conf` (root:root, 0644); new migrations
also set it through `bin/apply-plm`. The main migration configuration and its
original rollback snapshot were left unchanged. These PLM settings are separate
from the Plasma lock-screen settings.

- [ ] Confirm the clock is absent when the greeter next starts. Do not interrupt
  the current desktop solely for this visual check.

Desktop, idle/session lock and reboot/login now share the Interactive Rain
background contract, including hover and click splashes. The common defaults are
in `plasma/wallpaper-defaults.json`; `AGENTS.md` requires all three surfaces by
default for future background work. `apply-lockscreen` preserves the clock and lock
policy. PLM's separate greeter/wallpaper processes use a tested screen-local pointer
bridge; authentication remains upstream.

The 2026-09-11 parity update is built and installed user-locally. Desktop
configuration readback passed on both active screens, and the locker configuration
was applied with the hidden-clock preference preserved. Backups are under
`$HOME/.local/state/arasaka-kde/backups/`:
`shader-wallpaper-20260911-003227-yd2nrnv0` and
`lockscreen-20260911-003227-27dmuiqv`.
The 54 shader/activation tests, 3 locker/login configuration tests, native
graphics/input/host/QML tests, and staged system-renderer smoke check passed.
Both system packages are built; APT simulation changes only those two packages.

- [ ] User installs `plasmalogin_6.7.4-0arasaka2_amd64.deb` and the refreshed
  `arasaka-login-wallpaper_1.0-1_amd64.deb`, then runs
   `sudo ./bin/apply-lockscreen --login`. See `docs/login.md` for the scoped update.
- [ ] Confirm hover and click splashes at the next normal PLM login.

- [ ] Observe the shader, hover, click splashes and clock preference at the next normal lock.
  No forced lock, preview or restart was performed for this change.

Implementation references:

- [Implementation plan](docs/superpowers/plans/2026-09-07-plm-login-shader.md)
- [Design and preservation contract](docs/superpowers/specs/2026-09-07-plm-login-shader-design.md)

The migration direction is implemented; do not repeat feasibility work or reapply
the one-shot installer on the already migrated machine.
Ask before rebooting or otherwise terminating the running desktop session.

## Non-Negotiable Constraints

- Preserve user accounts, passwords, groups, home directories, and session files.
- Preserve desktop, KWin, launcher, display, application, shell, wallet, and
  unrelated lock-screen configuration. Only the scoped lock-screen command
  changes the background appearance; preserve clock preferences and lock policy.
- Preserve the user-local shader package, imported shaders, gallery, and favorites.
- Do not run `apply-live`, `apply-launcher`, or normal desktop shader activation
  as part of this migration.
- Do not change `/etc/pam.d/common-*`, SDDM PAM files, or `/etc/login.defs`.
- Keep autologin disabled.
- Keep SDDM installed, including its existing configuration and Arasaka theme,
  so a failed PLM login can be reversed from a TTY.
- Do not copy the user's home into the greeter account or loosen home permissions.
- Keep background parity and native input tests current. Component tests do not
  exercise authentication; observe actual login after normal user-initiated reboot.
- Do not import KDE Neon packages or repositories, build a moving Git branch,
  or run an untracked privileged `make install`.
- Do not overwrite unrelated worktree changes or make commits without a request.
- Update documentation directly to current behavior; remove dead instructions
  rather than adding supersession notes.

## Confirmed Setup

- OS: TUXEDO OS, **Debian testing/forky**, amd64, not Ubuntu-based TUXEDO OS.
- Plasma workspace: `4:6.7.2-5`; Plasma libraries: `6.7.4-2`.
- Qt: `6.10.2`; KDE Frameworks: `6.28`; systemd: `261.2`.
- PLM is absent from the inspected Debian/TUXEDO package repositories.
- PLM 6.7.4 and the independent wallpaper package have built successfully against
  the installed stack. Installation, PLM startup, successful login and the login
  appearance are confirmed. The later clock-free appearance remains unobserved.
- All three inspected desktops use `online.knowmad.shaderwallpaper`, Interactive Rain,
  30 FPS, full resolution and 75% speed, with mouse input enabled.
- The desktop video-wallpaper implementation and its installed leftovers have
  already been removed. Do not restore them.
- PLM supports our shader plugin, but **cannot reuse SDDM's arbitrary QML login
  layout**. The new login screen uses PLM's UI with our animated background.
- The lock screen now has its own shader/no-clock appearance settings, applied
  separately from PLM without changing authentication or lock timing.

## 1. Capture The Current State

- [x] Read `git status --short` and preserve all concurrent changes. Existing
  launcher, documentation, and test edits may belong to other work.
- [x] Recheck OS identity, installed versions, active manager, and enabled APT
  sources without changing them.
- [x] Read the actual desktop shader selections/settings through Plasma's
  read-only scripting interface. Do not execute wallpaper setters.
- [x] Compare actual shader/parameters with the approved desktop appearance. Future
  managed background changes apply to all three surfaces by default; never reset
  the desktop to an older effect from the migration record.
- [x] Record package versions and dependency provenance. The user installed the
  dependencies before the full snapshot; the earlier installed inventory is
  explicitly reconstructed from the recorded APT transaction, not a contemporaneous capture.
- [x] Record relevant user configuration and shader/gallery baselines privately,
  outside the repository. Do not collect passwords or wallet contents.
- [x] Inspect `/var/lib/dpkg/info/sddm.config`, `sddm.postinst`, and SDDM's owned
  paths to account for Debian's manager-selection behavior and file collisions.

## 2. Build A Pinned PLM Package

- [x] Add `plasma-login-manager` version `6.7.4` to `manifest/components.tsv`.
  Source: `https://download.kde.org/stable/plasma/6.7.4/plasma-login-manager-6.7.4.tar.xz`.
  SHA-256: `8ba5f9a5b31b2cb09d6846c590d09891dadb9a5625426b8552577299093b67fd`.
- [x] Fetch and verify it with the existing `bin/fetch-components`.
- [x] Simulate build dependencies including Debian packaging tools: 30 new
  packages, no upgrades/removals; the additional `systemd-dev` package also
  resolved without upgrades/removals. The user installed these dependencies.
- [x] Present exact dependency-install commands and reject removals/replacements.
  From now on provide privileged commands to the user, never execute `pkexec`.
- [x] Create `packaging/plasmalogin/debian/` and `bin/build-plm` as specified in
  the implementation plan.
- [x] Build unprivileged into ignored `build/plm/`. Use
  `DEB_BUILD_OPTIONS=nocheck` and `BUILD_TESTING=OFF`; do not run tests.
- [x] Produce `plasmalogin_6.7.4-0arasaka1_amd64.deb`, with real runtime
  dependencies and `Provides: x-display-manager`, without conflicting with SDDM.
- [x] Package Debian PAM files, the greeter account/state definitions, system/user
  services, and a distinct D-Bus policy filename.
- [x] Implement and inspect non-disruptive maintainer scripts: no service start,
  stop, enablement, or selector change. User-run installation readback succeeded.
- [x] Implement debconf registration without selection, preserving the existing
  shared value and seen state. Registration succeeded during user-run installation.
- [x] Inspect package contents, ownership, dependencies, licenses, and maintainer
  scripts before installing anything. Do not claim buildability until it builds.

## 3. Build The Independent Login Wallpaper

- [x] Add `--stage-only DEST` to `bin/apply-shader-wallpaper`, mutually exclusive
  with `--install-only`, without changing either existing desktop mode.
- [x] Reuse the pinned renderer build, Heartfelt patch, PNG generation, and
  license handling. Do not duplicate the shader-build implementation.
- [x] In staging-only mode, skip user-gallery merging, home deployment/backups,
  topology queries, and Plasma calls. Validate output paths and reject symlinks.
- [x] Export the plugin to the staged equivalent of
  `/usr/share/plasma/wallpapers/online.knowmad.shaderwallpaper/`.
- [x] Export the PNGs and `Heartfelt_No_Heart.frag` under the staged equivalent
  of `/usr/share/wallpapers/Arasaka/`.
- [x] Generate gallery metadata with final system URLs, not staging/home paths.
- [x] Have `bin/build-plm` produce `arasaka-login-wallpaper_1.0-1_amd64.deb`.
  Include the embedded native module and its dependencies.
- [x] Package root-owned readable assets without changing the user-local package.
  Actual greeter-account access passed the user-run installation checks.

## 4. Prepare Installation And Rollback

- [x] Implement scoped `bin/apply-plm` and its `--rollback BACKUP` operation.
  Default execution must proceed through installation, configuration, and boot
  selection, not stop at building artifacts.
- [x] Implement a migration lock, clear privilege boundaries, and explicit failure
  handling. Refuse unexpected conflicting PLM installs or a masked/changed manager.
- [x] Before installing login packages or changing manager configuration, create
  a root-owned mode-700 backup under `/var/backups/arasaka-kde/plm-*`.
- [x] Save the default-manager file, service-alias target, debconf value/seen
  state, enablement, package inventory, relevant SDDM configuration, and existing
  PLM configuration/state. Record paths that did not previously exist.
- [x] Include the original captured inventory and explicitly reconstructed
  pre-dependency installed inventory with its APT provenance.
- [x] Create an executable root-owned `rollback.sh` inside the backup **before
  selecting PLM**. It must work from a TTY without the repo or an unlocked home.
- [x] Implement and review standalone selector/configuration rollback without
  user resets, package purges or autoremove. Actual recovery remains unexercised;
  it changes boot selection without stopping a running PLM process.
- [x] Inspect the installation transaction and install the two explicit local
  package files through APT. Leave the running SDDM process alone.
- [x] Confirm PLM's account, state directory, PAM files, services, and resources
  exist with correct ownership and accessible paths.

## 5. Configure The Login Shader

- [x] Write only PLM-owned configuration groups in `/etc/plasmalogin.conf`,
  preserving unrelated existing keys.
- [x] Keep `[Autologin] User=` empty and `Relogin=false`.
- [x] Set `[Greeter] WallpaperPluginId=online.knowmad.shaderwallpaper`.
- [x] Use the complete shader configuration block from Task 4 of the
  implementation plan, with these independent login settings:
  Heartfelt No Heart, 30 FPS, 75% speed, full resolution, `pauseMode=3`, only
  texture channel 0 enabled, and mouse/audio/window/playlist/buffer opt-outs.
- [x] Use system paths for the selected shader and `mikoshi-16x9.png` texture.
  Keep the desktop's per-screen texture choices and window-pause policy unchanged.
- [x] Resolve PLM's actual session identifier for the existing Plasma Wayland
  session. Preselect the existing user/session without enabling autologin.
- [x] Confirm the greeter account can read the shader, artwork, native module,
  and required system resources without accessing the private home.
- [x] Retain existing Qt environment settings. The user confirmed the login
  appearance without an additional OpenGL override.
- [x] Disable the login clock using PLM's native `ShowClock=false` preference,
  preserving the lock screen and the original rollback snapshot.

## 6. Select PLM And Activate It

- [x] Only after installation/configuration succeeds, coordinate all selectors:
  debconf's `shared/default-x-display-manager`,
  `/etc/X11/default-display-manager`, and `display-manager.service`.
- [x] Select the registered `plasmalogin` choice in debconf and require successful
  responses, not merely a zero process exit status.
- [x] Atomically set the default-manager file to `/usr/bin/plasmalogin`.
- [x] Disable SDDM boot selection and enable PLM **without `--now`**; reload
  systemd definitions. Do not stop/restart the live display-manager service.
- [x] Implement and review automatic recovery for partial selection failure.
  Selection succeeded; the failure path was not exercised.
- [x] Read back the default file, alias, debconf selection, and enablement. All
  must agree on PLM for the next boot.
- [x] Print the actual backup path and exact TTY rollback command.
- [x] Leave reboot under user control; the user rebooted and reported completion.
- [x] Report activation pending until reboot; now verified active after reboot.
- [x] After reboot, inspect the actual active manager and logs. Have the user
  confirm that the shader appeared and the existing account entered Plasma.
- [x] User-run installation confirmed desktop shader/file digests matched its
  invocation baseline. Historical audit digests also showed no drift before it.
- [x] Retain standalone TTY recovery rather than resetting user configuration.
  Login succeeded, so no rollback was needed or performed.

## 7. Finish The Handoff

- [x] Update `README.md` and `ATTRIBUTION.md` to the resulting current setup.
- [x] Document local package versions, installation commands, independent shader
  assets, and standalone rollback.
- [x] Record the actual protected backup: `/var/backups/arasaka-kde/plm-q3fl2q9u`.
- [x] State actual status: PLM active after user-run installation and reboot;
  successful Plasma login and login appearance confirmed. Clock setting disabled;
  its next-greeter visual confirmation is still pending.
- [x] Inspect the final diff without running tests. Preserve unrelated edits.
- [x] Mark completed items here and leave any reboot/activation boundary explicit
  so another session can resume safely. Do not commit unless requested.
