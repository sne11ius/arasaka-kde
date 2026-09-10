# PLM login

[Docs](README.md) / PLM login

Plasma Login Manager (PLM) uses its own login UI with the same Interactive Rain
background as the desktop and locker. Its root-owned artwork and native module
live under `/usr/share`, so the greeter needs no access to a private home directory.

Choose the procedure for your situation:

- [Build packages](#build-the-packages): unprivileged, no installation.
- [First migration from SDDM](#first-migration-from-sddm): one-time setup.
- [Update an existing PLM installation](#update-an-existing-plm-installation):
  package update and shared background configuration.
- [Recover SDDM](#recover-sddm): use your own migration's printed backup path.

## Build the packages

The target is Debian-based TUXEDO OS, amd64, Qt 6.10.2, Frameworks 6.28, and
Plasma 6.7. The authoritative versioned build dependencies are in
[`packaging/plasmalogin/debian/control`](../packaging/plasmalogin/debian/control).
Also install `build-essential`, `dpkg-dev`, and the
[shader prerequisites](installation.md#shader-build). `systemd-dev` is needed in
addition to `libsystemd-dev`.

Build tools do not install dependencies. Simulate dependency transactions before
applying them, and inspect any proposed desktop upgrades or removals. This setup
does not import Neon repositories or packages.

Run as the desktop user, without sudo:

```sh
./bin/build-plm
```

Current outputs:

```text
build/plm/plasmalogin_6.7.4-0arasaka2_amd64.deb
build/plm/arasaka-login-wallpaper_1.0-1_amd64.deb
build/plm/inventory.json
```

The official PLM 6.7.4 archive is SHA-256-pinned. The builder applies the tracked
pointer bridge, stages the shader through `--stage-only`, inspects ownership,
dependencies, package file collisions, and maintainer scripts, and saves metadata
and build logs alongside the packages. `--plm-only` omits the wallpaper build.

PLM packaging uses `DEB_BUILD_OPTIONS=nocheck` and `BUILD_TESTING=OFF`; a package
build is not an authentication test. Native rain/input tests are separate.
Package maintainer scripts do not start, stop, enable, or select a display manager.

## First migration from SDDM

This controller is for a **fresh, inspected SDDM-to-PLM migration**. An existing or
partially installed PLM setup requires inspection rather than rerunning migration.
Keep SDDM and its theme installed for recovery.

After building, run this yourself **inside Plasma Wayland as the desktop user,
without a leading sudo**:

```sh
./bin/apply-plm --skip-build
```

Without `--skip-build`, the controller rebuilds both packages first. Existing
artifacts are re-inspected and their hashes checked. The optional `--baseline PATH`
preserves a prior private audit record; a fresh invocation captures its own state.

The controller prepares unprivileged, then prints and invokes a scoped sudo
installation step. Before installation it creates an owner-only backup under
`/var/backups/arasaka-kde/plm-*` containing configuration, selector state, package
inventories, and an executable standalone `rollback.sh`.

It checks the APT transaction, installs protected copies of the two packages,
verifies account/PAM/assets/settings, and coordinates:

- debconf's `shared/default-x-display-manager` selection;
- `/etc/X11/default-display-manager`;
- the systemd `display-manager.service` alias.

Selection is for the **next boot**. The controller does not stop the running
manager or reboot the session. Autologin stays disabled. A fresh migration uses
the project's clock-free login preference; later background-only refreshes
preserve the current clock setting.

Keep the printed backup path. Reboot when you are ready, then check the actual
login appearance, rain interaction, and successful entry into Plasma. Configuration
readback before reboot does not establish those results.

## Update an existing PLM installation

Current login interaction requires both the updated wallpaper native module and
the PLM pointer bridge. The updater accepts the known patched package **6.7.4-0arasaka2**;
a higher upstream version without the local bridge is rejected.
The old `0arasaka1` package cannot deliver clicks merely by enabling mouse input.

1. Save the previously installed `.deb` artifacts somewhere outside `build/plm/`
   before rebuilding. Keep their version/hash records so you can restore the
   actual previous pair if needed.
2. Build as your normal user:

   ```sh
   ./bin/build-plm
   ```

3. Simulate the explicit local-package update:

   ```sh
   apt-get --simulate --reinstall --no-remove --no-install-recommends install \
     ./build/plm/plasmalogin_6.7.4-0arasaka2_amd64.deb \
     ./build/plm/arasaka-login-wallpaper_1.0-1_amd64.deb
   ```

4. After reviewing the proposed transaction, run the privileged installation
   yourself. An ordinary refresh should affect only the intended packages;
   investigate unexpected dependencies or desktop changes first.

   ```sh
   sudo apt-get --reinstall --no-remove --no-install-recommends install \
     ./build/plm/plasmalogin_6.7.4-0arasaka2_amd64.deb \
     ./build/plm/arasaka-login-wallpaper_1.0-1_amd64.deb
   sudo ./bin/apply-lockscreen --login
   ```

The last command validates the installed bridge version and native renderer,
backs up `/etc/plasmalogin.conf`, and applies shared background defaults while
preserving clock preference and authentication. Its backup is printed under
`/var/backups/arasaka-kde/login-wallpaper-*`.

`--reinstall` is necessary because the wallpaper package version remains `1.0-1`.
No display-manager restart is performed. The updated processes load at the next
normal greeter start, normally after reboot. **Do not restart the display manager
from your running desktop.**

Once the required PLM bridge is installed, a later artwork-only refresh can
reinstall just `arasaka-login-wallpaper`, followed by the scoped `--login` command
if shared settings changed. A bridge change requires updating PLM as well.
User-local desktop/locker assets must also be updated as described in
[the wallpaper guide](wallpaper.md#apply-the-shared-background).

## Clock preference

Background updates preserve the user's clock preference. PLM uses `[Greeter]
`ShowClock`; the session locker has its own look-and-feel settings.

If you specifically want to hide the login clock, run:

```sh
sudo kwriteconfig6 --file /etc/plasmalogin.conf \
  --group Greeter --key ShowClock --type bool false
sudo chmod 0644 /etc/plasmalogin.conf
```

Use `true` to show it. Edit this key in the main file: PLM gives an explicit value
in `/etc/plasmalogin.conf` precedence over additional drop-in sources, and migration
writes it there. A conflicting drop-in cannot override that value. The final
permission step keeps the file readable to the greeter. The change appears on its
next normal start.

## Recover SDDM

Use **your own migration's printed backup path**, not a path from another host.
From a TTY, run its standalone script:

```sh
sudo /var/backups/arasaka-kde/plm-YOUR-BACKUP/rollback.sh
```

Replace `plm-YOUR-BACKUP` with the directory created during your migration. With
the checkout available, `./bin/apply-plm --rollback BACKUP` accepts the same path.

Recovery restores selectors and migration-owned configuration, leaves packages
installed, and selects SDDM for the next boot. It does not change the currently
running service. Reboot yourself when ready. Standalone recovery is provided,
but has not been exercised on the documented deployment.

For a background-only regression, restore the saved previous package(s) and
relevant background settings rather than rolling back the original migration.
Save local modifications to package-owned assets separately; reinstalling a
package replaces those files.
