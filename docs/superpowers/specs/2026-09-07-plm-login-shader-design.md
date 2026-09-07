# PLM Login Shader Design

**User request:** Switch to Plasma Login Manager, retain current user
configuration, activate the animated login background, and hide the login clock.

**Scope:** Complete the migration, retaining the explicit privileged-install and
reboot boundaries. PLM is installed and active after user-run installation and
reboot; successful Plasma login and login appearance are confirmed. SDDM remains
installed but disabled for recovery. See `TODO.md` for the completion record.

## Baseline

- This machine is TUXEDO OS on Debian testing, codename `forky`, amd64.
- Plasma workspace is `4:6.7.2-5`; Plasma libraries are `6.7.4-2`.
- Qt is `6.10.2`; KDE Frameworks is `6.28`; systemd is `261.2`.
- PLM runs the Plasma/Wayland login setup. Autologin is disabled.
- Debian/TUXEDO repositories currently do not provide PLM. Debian packaging is
  still an unreleased draft; importing KDE Neon binaries is not acceptable.
- The three inspected desktops use `online.knowmad.shaderwallpaper`, Heartfelt No Heart,
  30 FPS, full resolution, and 75% speed. Mouse/audio/window-reactive inputs are
  disabled. The primary texture is `mikoshi-16x9.png`.
- Desktop renderer/artwork remain user-local; the greeter has independent
  system-wide assets. The lock screen remains static and unchanged.
- The repository and worktree can contain concurrent user changes. Re-read them
  before execution; do not revert, overwrite, stage, or commit unrelated work.

## Architecture

Build upstream PLM 6.7.4 into a locally maintained Debian package named
`plasmalogin`, version `6.7.4-0arasaka1`. Use the existing desktop stack and normal
Debian development dependencies. Do not use a moving Git branch, Neon packages,
or an untracked privileged `make install`.

Build a separate `arasaka-login-wallpaper` package from the repository's pinned
shader inputs. Reuse the existing shader builder through a staging-only mode,
without installing or reconfiguring the user's desktop package. Its system-wide
plugin and assets are independent of private user directories.

Provide `bin/build-plm` for unprivileged artifact creation and `bin/apply-plm`
for the scoped migration, configuration, selection, and rollback. Installing the
packages must not start PLM or stop SDDM. The explicit selection phase changes the
next boot's display manager only after package and configuration prerequisites
are present.

## Preservation Contract

- Do not run `apply-live`, `apply-launcher`, or the normal shader activation path.
- Do not rewrite user Plasma, KWin, launcher, display, application, shell, wallet,
  or lock-screen configuration. Do not replace the user-local shader package or
  gallery, change ownership of the user's home, or copy the home into PLM's account.
- Keep user accounts, passwords, groups, home directories, and session files.
- Leave `/etc/pam.d/common-*`, SDDM's PAM configuration, `/etc/login.defs`, and
  system-wide authentication policy unchanged.
- Keep SDDM installed, with its configuration and Arasaka theme, for rollback.
- Preserve autologin as disabled. Use the existing Plasma Wayland session.
- Keep display resolution, scale, orientation, layout, and desktop priority
  unchanged. PLM's own greeter may need separate display preferences; do not copy
  complete user KScreen configuration blindly.
- SDDM's arbitrary QML login layout cannot transfer to PLM. Reuse the animated
  artwork with PLM's own authentication UI; do not claim identical greeter styling.
- Do not add, modify, or run tests, test suites, or synthetic greeter previews.
  Package integrity checks, dependency resolution, state inspection, and checking
  the actual migration outcome remain required operational safeguards.
- No automatic commits, service termination, logout, or reboot.

## Login Wallpaper

Install the plugin under
`/usr/share/plasma/wallpapers/online.knowmad.shaderwallpaper/`, including the
embedded native QML module. Install the managed PNGs and adapted shader under
`/usr/share/wallpapers/Arasaka/`. Use root-owned directories with mode 755 and
readable assets with mode 644. Do not make private home directories accessible.

Configure PLM's `Greeter/WallpaperPluginId` and its plugin-specific `General`
group in `/etc/plasmalogin.conf`. Copy the approved wallpaper parameters into
this separate namespace with system paths. Do not copy unrelated desktop keys,
credentials, gallery files, or session state.

Hide the login clock with `[Greeter] ShowClock=false`. New migrations write this
key in the managed configuration. The existing installation uses the separate
root-owned mode-644 `/etc/plasmalogin.conf.d/arasaka-clock.conf`, keeping the
original migration configuration byte-for-byte intact for standalone rollback.
Do not change the lock-screen clock or restart a live display manager to apply it.

Use Heartfelt No Heart, 30 FPS, 75% speed, full resolution, and the primary 16:9
texture on PLM's greeter surfaces. Keep the same input/buffer/playlist opt-outs.
PLM's settings do not change the desktop's per-screen 16:9/16:10 choices.

At execution, read the current desktop wallpaper configuration first. If it has
changed from this requested shader/parameters, ask which appearance should be
used for login rather than resetting the desktop or silently ignoring the change.

PLM 6.7 explicitly allowlists this plugin. Its greeter uses an independent
`plasmalogin` account; files only in `~/.local` are insufficient. Avoid manually
managed assets under `/var/lib/plasmalogin/wallpapers/`, which the settings helper
can replace. Use OpenGL for the native renderer, scoped to PLM's wallpaper process
if an explicit backend setting is necessary; do not alter global Qt settings.

## Authentication And Selection

Use upstream's Debian PAM stack for PLM, including optional KWallet hooks. It
detects this OS through `ID_LIKE=debian`. Install PLM's distinct PAM service files
without modifying common authentication or copying all SDDM settings.

Package the `plasmalogin` system account, state directory, system/user services,
and D-Bus policy. Coordinate all three Debian display-manager selectors:
`shared/default-x-display-manager` in debconf,
`/etc/X11/default-display-manager`, and the systemd `display-manager.service`
alias. Do not change only the alias or rely on `update-alternatives`.

Before installing login packages or changing manager configuration, record a
private root-owned backup under
`/var/backups/arasaka-kde/plm-*`, including pre-existing PLM files, selector state,
service enablement, package versions, and missing-path markers. Back up only
configuration relevant to the migration, never credential stores.
Record the package inventory before installing build dependencies as well; those
development packages must not trigger desktop removal or an implicit upgrade.

Selecting PLM for boot is not the same as running it. Keep SDDM and the current
desktop session running until the user explicitly confirms a controlled reboot.
After reboot, establish whether PLM actually runs, displays the shader, and allows
the existing account to enter the same Plasma session. If execution pauses before
reboot or user confirmation, report activation as pending, not complete.

## Recovery

Implement `bin/apply-plm --rollback BACKUP` before selecting PLM. Restore the
saved default-manager file, debconf value, service alias/enablement, and any PLM
configuration changed by this migration. Leave user configuration and SDDM's theme
alone. Packages installed solely for PLM may remain installed but inactive; do
not automatically remove dependencies or run autoremove.

Keep a root-readable rollback script in the backup so it can be invoked from a
TTY without the repository or an unlocked user home. Before reboot, give the user
the actual backup and rollback paths. A broken PLM login must not require a
successful PLM login to undo the selection.

## Sources

- [PLM 6.7.4 requirements](https://github.com/KDE/plasma-login-manager/blob/v6.7.4/CMakeLists.txt)
- [Official source checksum](https://download.kde.org/stable/plasma/6.7.4/plasma-login-manager-6.7.4.tar.xz.sha256)
- [Debian PAM selection](https://github.com/KDE/plasma-login-manager/blob/v6.7.4/data/CMakeLists.txt)
- [PLM wallpaper allowlist](https://github.com/KDE/plasma-login-manager/blob/v6.7.4/src/frontend/settings/plasmaloginsettings.cpp)
- [PLM greeter settings schema](https://github.com/KDE/plasma-login-manager/blob/v6.7.4/src/frontend/settings/plasmaloginsettingsbase.kcfg)
- [Debian packaging status](https://salsa.debian.org/qt-kde-team/kde/plasma-login-manager)
