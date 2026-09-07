# PLM Login Shader Implementation Plan

> **Execution status:** Implemented, installed by the user, and active after
> reboot. Successful Plasma login and the login appearance are confirmed.
> `TODO.md` records completed steps and the remaining clock-appearance observation.
> Do not rerun the one-shot migration on this already migrated machine.

**Goal:** Switch this machine from SDDM to PLM with Heartfelt No Heart on the login
screen, retaining current user settings and a usable SDDM rollback path.

**Architecture:** Build pinned PLM and shader artifacts into two local Debian
packages. Install them without changing the active display-manager process, then
configure PLM and select it coherently through Debian's display-manager mechanisms.
Keep the user-local shader installation and all desktop settings separate.

**Tech Stack:** Debian testing/forky amd64, Python 3, Bash, CMake, C++20, Qt 6,
KDE Frameworks/Plasma 6, OpenGL, PAM, systemd, debhelper, dpkg, KConfig.

**Spec:** `docs/superpowers/specs/2026-09-07-plm-login-shader-design.md`

## Global Constraints

- Preserve the complete migration: packages, configuration, selectors and recovery.
- Preserve the user configuration and authentication boundaries in the spec.
- Keep SDDM installed and do not stop the current session.
- No Neon repository/package imports, moving upstream branches, or privileged
  source builds. No `sudo make install` into the live filesystem.
- Do not add, modify, or run tests or synthetic greeter previews. Set
  `DEB_BUILD_OPTIONS=nocheck` and `BUILD_TESTING=OFF` for builds. Keep package
  checksums, dependency/ownership checks, error handling, and actual state readback.
- Use `apply_patch` for manual edits. Do not touch concurrent changes, user tests,
  screenshots, or launcher work. Do not commit unless the user requests it.
- Do not run full-theme or desktop-wallpaper application commands for this task.
- Update current documentation directly; remove dead instructions rather than
  adding supersession notes.
- A reboot needs explicit confirmation that the user is ready to end the session.
  Boot selection alone is not evidence of a working PLM login.

## File Responsibilities

- Modify `manifest/components.tsv`: pin the official PLM source archive.
- Create `packaging/plasmalogin/debian/`: maintain the local PLM binary package,
  its dependencies, PAM/service installation, and non-disruptive maintainer scripts.
- Modify `bin/apply-shader-wallpaper`: add a staging-only artifact export without
  changing the existing desktop install/activation modes.
- Create `bin/build-plm`: build both local packages as the desktop user, retaining
  generated files under ignored `build/plm/` and source downloads in the cache.
- Create `bin/apply-plm`: capture migration state, install the packages with scoped
  privilege, configure the login shader, select the manager, and support rollback.
- Modify `README.md` and `ATTRIBUTION.md`: document the resulting PLM setup,
  prerequisites, package ownership, backup paths, and actual activation status.
- Leave `bin/apply-live`, `plasma/layout.js`, `plasma/shader-wallpaper.js`, user
  applets, `theme/lockscreen`, and `tests/` unchanged unless a concrete migration
  conflict requires a separately explained change.

## Task 1: Capture State And Pin The Build

**Interfaces:** Establish the immutable PLM input and the pre-migration state that
`bin/apply-plm` must preserve. No package installation or manager selection yet.

- [ ] Read the spec, `git status --short`, current `bin/apply-shader-wallpaper`,
  `bin/fetch-components`, and the current manifest. Retain all existing changes.
- [ ] Read `/etc/os-release`, relevant APT sources, package versions, SDDM config,
  and the active display-manager selector. Do not assume Ubuntu-based TUXEDO OS.
- [ ] Inspect the desktop wallpaper through read-only Plasma scripting. Capture
  the active plugin, selected shader, texture URLs, FPS, speed, and enabled inputs
  from both desktops. Do not execute wallpaper setters.
- [ ] Add this tab-separated manifest entry, verifying the fetched bytes before
  extraction through the existing fetcher:

```text
plasma-login-manager	6.7.4	https://download.kde.org/stable/plasma/6.7.4/plasma-login-manager-6.7.4.tar.xz	8ba5f9a5b31b2cb09d6846c590d09891dadb9a5625426b8552577299093b67fd	plasma-login-manager-6.7.4.tar.xz
```

- [ ] Inspect `/var/lib/dpkg/info/sddm.config` and `sddm.postinst` for the local
  Debian selector behavior. Currently the default file is `/usr/bin/sddm` and the
  alias points to `sddm.service`. Inspect package-owned destinations with
  `dpkg-query -L sddm` before choosing PLM paths.
- [ ] Record read-only baselines for relevant user configuration files and the
  user-local shader package/gallery. Store any private snapshots outside the repo.
  Distinguish expected runtime changes to readiness tokens or recent-window state
  from configuration changes made by the migration.

## Task 2: Build The PLM Debian Package

**Files:** `packaging/plasmalogin/debian/control`, `changelog`, `copyright`,
`rules`, `source/format`, `plasmalogin.install`, `plasmalogin.templates`,
`plasmalogin.config`, `plasmalogin.postinst`, `plasmalogin.postrm`, and
`bin/build-plm`.

**Interfaces:** `./bin/build-plm` produces
`build/plm/plasmalogin_6.7.4-0arasaka1_amd64.deb` and a build/package inventory.
It must not install packages, start services, or select a display manager.

- [ ] Re-evaluate missing build and packaging dependencies with APT simulation.
  The previously identified native dependencies were:

```sh
apt-get --simulate --no-install-recommends install \
  qt6-shadertools-dev libkf6dbusaddons-dev libkf6auth-dev \
  liblayershellqtinterface-dev plasma-workspace-dev libkscreen-dev \
  libpam0g-dev libsystemd-dev
```

That simulation proposed 15 new packages, zero upgrades/removals. Also account
for `debhelper`, `dpkg-dev`, and source-declared dependencies, including ECM,
Qt tools, libXau, and the already-installed KDE development packages. If the new
resolution removes/replaces desktop packages, stop and report it. Present the
actual privileged dependency-install command before executing it.

- [ ] Implement unprivileged source extraction with traversal/link rejection.
  Copy tracked Debian packaging into the extracted tree; keep generated artifacts
  in `build/plm/`, not the source checkout or live system.
- [ ] Set binary package name `plasmalogin`, version `6.7.4-0arasaka1`, and
  `Provides: x-display-manager`. Use `${shlibs:Depends}` and `${misc:Depends}`;
  account explicitly for runtime QML modules/services that ELF dependency scanning
  cannot discover. Do not declare a conflict with or replacement of SDDM.
- [ ] Configure the upstream build with these installation boundaries:

```sh
cmake -S "$source" -B "$build" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX=/usr \
  -DCMAKE_INSTALL_SYSCONFDIR=/etc \
  -DCMAKE_INSTALL_LOCALSTATEDIR=/var \
  -DPAM_CONFIG_DIR=/etc/pam.d \
  -DPAM_OS_CONFIGURATION=debian \
  -DINSTALL_PAM_CONFIGURATION=ON \
  -DDBUS_CONFIG_FILENAME=plasmalogin_org.freedesktop.DisplayManager.conf \
  -DBUILD_TESTING=OFF
```

Use the equivalent arguments in `debian/rules`; installation must target the
Debian staging tree through debhelper/DESTDIR. Include upstream license material.
The distinct D-Bus filename must not overwrite SDDM's
`sddm_org.freedesktop.DisplayManager.conf`.

- [ ] Install the upstream `plasmalogin` sysusers/tmpfiles definitions and the
  root/user services, with `/var/lib/plasmalogin` as the greeter state directory.
  Package configuration creates only the PLM account/state and reloads systemd
  definitions; it must not start PLM, stop SDDM, or change the default manager.
  Suppress automatic service enable/start and restart-on-upgrade behavior.
- [ ] Integrate debconf using `shared/default-x-display-manager` and
  `plasmalogin/daemon_name=/usr/bin/plasmalogin`. Register PLM as a valid choice
  without selecting it on package installation. Preserve the current default file
  and selected manager during configuration/upgrades. If adapting Debian's SDDM
  maintainer scripts, retain their GPL notices and explicitly remove any automatic
  selection/start behavior inappropriate for the preparation phase.
- [ ] Build with `DEB_BUILD_OPTIONS=nocheck dpkg-buildpackage -b -us -uc` from
  the staged source. No test, lint, or preview command is part of this task.
- [ ] Inspect the artifact with `dpkg-deb --info` and `dpkg-deb --contents`.
  Reject collisions with existing non-PLM package-owned files, unintended home
  paths, development-only payload, and maintainer scripts that switch services.
  Package presence does not prove that authentication works.

## Task 3: Produce System-Wide Shader Artifacts

**Files:** `bin/apply-shader-wallpaper`, `bin/build-plm`.

**Interfaces:** `apply-shader-wallpaper --stage-only DEST` produces a fresh,
installable filesystem tree below an empty absolute `DEST`, with final URLs
rooted at `/usr/share`. `build-plm` turns that tree into
`build/plm/arasaka-login-wallpaper_1.0-1_amd64.deb`.

- [ ] Make `--stage-only` mutually exclusive with `--install-only`. Validate an
  absolute, empty/nonexistent output location and refuse symlinked destinations.
  Preserve the existing CLI and behavior when the new option is absent.
- [ ] Reuse the existing verified compilation, Heartfelt patching, PNG rendering,
  native-module validation, and attribution code. Do not duplicate the renderer
  build in `build-plm`. In staging-only mode, skip merging the user's installed
  gallery and skip user deployment backups, topology queries, Plasma calls, and
  writes to the home installation.
- [ ] Set final data URLs before generating gallery metadata. Export the finished
  package and artwork, then return before the live replacement/activation branch:

```text
DEST/usr/share/plasma/wallpapers/online.knowmad.shaderwallpaper/
DEST/usr/share/wallpapers/Arasaka/mikoshi-16x9.png
DEST/usr/share/wallpapers/Arasaka/mikoshi-16x10.png
DEST/usr/share/wallpapers/Arasaka/shaders/Heartfelt_No_Heart.frag
```

The package's custom Heartfelt gallery entry must reference the final system
shader URL, not a staging directory or user home. Retain the embedded native
module under `contents/ui/shaderwallpaper/`.

- [ ] Compare the managed shader appearance inputs with the execution-time
  desktop snapshot. If the user has changed shader selection or parameters, do
  not silently apply this plan's old defaults; ask which login appearance to use.
- [ ] Package the staged files with native-library dependencies derived from
  the compiled module and explicit required QML dependencies. Make the system
  files root-owned and readable by `plasmalogin`. Include the engine's license,
  Heartfelt's original header/license, and local adaptation attribution.
- [ ] Inspect the package file list and metadata. No home paths may be required
  by the selected login shader. The user-local package remains untouched and
  retains precedence for the user's existing desktop.

## Task 4: Install, Back Up, And Configure PLM

**File:** `bin/apply-plm`.

**Interfaces:** Default `./bin/apply-plm` performs preparation, scoped package
installation, configuration, and next-boot selection. It does not reboot.
`./bin/apply-plm --rollback BACKUP` restores the recorded manager selection and
migration-owned configuration without modifying the user desktop.

- [ ] Implement argument validation, explicit privilege boundaries, and a single
  migration lock. Build/capture user settings as the desktop user; use privilege
  only for package installation, protected snapshots/configuration, and service
  selection. Reject unexpected symlinks and conflicting pre-existing PLM installs.
  Refuse a masked display-manager alias or a newly selected non-SDDM manager
  instead of forcing a different selection over an unexpected local change.
- [ ] Before installing login packages or changing manager settings, create
  `/var/backups/arasaka-kde/plm-*`
  with mode 700. Record the default-manager file, service-alias link, debconf
  default/seen state, enablement, package inventory, relevant SDDM configuration,
  and any existing PLM configuration/drop-ins/state. Record missing paths so
  rollback does not invent previous files. Do not back up passwords or wallets.
  Include the initial package inventory captured before build-dependency installs.
- [ ] Store a root-owned executable `rollback.sh` in the backup. It must use only
  installed system tools and snapshot files, not the repo or user home. Implement
  rollback before running the default-manager selection phase.
- [ ] Inspect the local package installation transaction, then install the two
  explicit artifact paths through APT. Package scripts must leave the running
  SDDM process and current manager selection unchanged. Do not add repositories.
- [ ] Confirm PLM's account, PAM files, service definitions, and referenced
  native/QML assets exist with expected ownership. Keep `/etc/pam.d/common-*`
  unchanged; use the separate upstream Debian PLM PAM services with KWallet hooks.
- [ ] Configure only PLM-owned groups in `/etc/plasmalogin.conf`, preserving any
  unrelated existing keys. Keep autologin disabled and configure the wallpaper:

```ini
[Autologin]
User=
Relogin=false

[Greeter]
WallpaperPluginId=online.knowmad.shaderwallpaper
ShowClock=false

[Greeter][Wallpaper][online.knowmad.shaderwallpaper][General]
selectedShaderPath=file:///usr/share/wallpapers/Arasaka/shaders/Heartfelt_No_Heart.frag
selectedShaderCode=
commonCode=
running=true
shaderSpeed=0.75
targetFps=30
resolutionScale=1
pauseMode=3
checkActiveScreen=true
excludeWindows=
mouseEnabled=false
audioEnabled=false
windowsEnabled=false
playlistEnabled=false
enableShaderTweaks=false
watchSourceFile=false
useBufferA=false
useBufferB=false
useBufferC=false
useBufferD=false
iChannel0Enabled=true
iChannel0=file:///usr/share/wallpapers/Arasaka/mikoshi-16x9.png
imageChannel0=0
iChannel1Enabled=false
iChannel2Enabled=false
iChannel3Enabled=false
imageChannel1=-1
imageChannel2=-1
imageChannel3=-1
```

`pauseMode=3` is the independent greeter policy; the desktop's existing window
pause policy must remain unchanged. The plugin also bypasses window pausing in
its restricted login mode.

- [ ] Preserve the existing user/session preference through PLM's
  `Greeter/PreselectedUser` and `PreselectedSession` only when supported by its
  session model. Read the pinned model/schema to use its actual session identifier;
  resolve `/usr/share/wayland-sessions/plasma.desktop`, not a guessed SDDM index.
  Do not populate `Autologin/User` to preselect a user.
- [ ] Confirm the greeter account can read the selected shader, texture, native
  module, and required system resources. Set an OpenGL backend only in PLM's
  wallpaper service environment if required; leave user/global Qt environment
  settings alone. Do not grant access to the private user home.

## Task 5: Select PLM And Complete Activation

**Interfaces:** A coherent next-boot manager selection plus a protected rollback
artifact, followed by actual activation across a user-approved reboot.

- [ ] Require successful package/configuration steps before selection. Use the
  installed Debian debconf interface to select `plasmalogin`, atomically write
  `/usr/bin/plasmalogin` to `/etc/X11/default-display-manager`, and change the
  systemd alias. Match the package's debconf owner/daemon-name registration.
  Preserve the previous values in the rollback snapshot.

```sh
printf '%s\n' \
  'SET shared/default-x-display-manager plasmalogin' \
  'FSET shared/default-x-display-manager seen true' \
  | sudo debconf-communicate plasmalogin
```

Require a success response for each debconf command, not just a zero shell exit
status. Write the default-manager file through the privileged migration helper,
using a sibling temporary file and atomic rename after the backup is complete.

- [ ] The service selection operations must omit `--now`:

```sh
sudo systemctl disable sddm.service
sudo systemctl enable --force plasmalogin.service
sudo systemctl daemon-reload
```

Run these only inside the backed-up selection transaction, not as a substitute
for its debconf/default-file updates. If selection fails part-way, restore all
three selectors from the snapshot without terminating the current session.

- [ ] Read back the alias, default file, debconf value, and enablement. Verify
  that they agree on PLM for next boot. The running process may correctly remain
  SDDM until reboot; do not report that as a failed migration or stop it.
- [ ] Print the actual backup path and the exact recovery command from the
  generated backup directory. Ensure recovery works without the user home.

```sh
printf 'sudo %q\n' "$backup/rollback.sh"
```

- [ ] Ask whether the user is ready for a reboot. After explicit confirmation,
  use `sudo systemctl reboot`. Never restart `display-manager.service` from the
  running graphical session. If confirmation is deferred, state clearly:
  "PLM and shader configured, selected for next boot; activation pending reboot."
- [ ] Resume after reboot. Inspect the actual active manager and PLM logs, and
  have the user confirm that the shader was visible and the existing account
  entered Plasma. Confirm expected wallpaper selection and retained user settings
  without rewriting them. This is actual deployment acceptance, not an automated
  test suite or synthetic greeter preview.
- [ ] If login is broken, use the prepared rollback from a TTY and reboot into
  SDDM. Do not delete or reset user configuration to repair PLM. Do not purge SDDM,
  remove shared dependencies, or claim shader/login success without observation.

## Task 6: Record The Result

**Files:** `README.md`, `ATTRIBUTION.md`.

- [ ] Document the active login manager, local package versions, scoped command,
  independent system-wide shader assets, preservation guarantees, and the real
  backup/rollback locations. Describe pending reboot honestly if execution stops
  at that boundary. Do not claim the retained SDDM QML theme is the PLM UI.
- [ ] Attribute PLM and retain its upstream licenses. Update current instructions
  in place; do not append historical/supersession blocks or remove the separately
  useful SDDM rollback assets.
- [ ] Inspect the final diff and actual installation/selection state without
  running tests. Leave test files and all unrelated user changes untouched.
- [ ] Report exactly what was installed, whether PLM is merely selected or
  actually active, whether login/shader appearance was observed, which user
  settings were preserved, and how to revert. No automatic commit.
