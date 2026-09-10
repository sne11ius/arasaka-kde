# Launcher

[Docs](README.md) / Launcher

Press **Super** for a compact application search on the **primary display**,
regardless of pointer or active-window location. The managed desktop has no bars,
laptop rail, or hidden edge panels.

## Everyday use

- Each opening starts with an empty search, a **Full Menu** button, and the native
  system tray below.
- Type to reveal up to six rows before scrolling. Arrow keys select a result;
  **Enter** launches it and closes the popup.
- The six-row area stays reserved, so search and tray do not jump as results change.
- Empty search shows no favorites or suggestions.
- **Escape**, **Super** again, or focus loss dismisses the popup.
- **Full Menu** expands into stock Kickoff: favorites, applications, locations,
  and session actions. **Back to Search** restores the compact view and query.
- The native tray stays below both views, including its own submenus.

Compact search uses KDE's application runner (`krunner_services`), including
native app actions. File search, browser history, calculators, and shell-command
providers are not part of this view. Keep the application runner enabled in KDE
Search settings. Its private Kicker API is verified on Plasma 6.7 and needs
rechecking after upgrades.

## Install or reapply

Run as the desktop user in the target Plasma session:

```sh
./bin/apply-launcher
```

Required tools: Python 3, `kpackagetool6`, `qdbus6`, `systemctl`, `kscreen-doctor`,
`jq`, Bash, and standard Unix utilities. Stock Kickoff and System Tray applets
must be installed.

The installer checks inputs and backup paths, validates the source package with
`kpackagetool6`, and pings Plasma's D-Bus service. It installs the tracked
[`com.arasaka.launcher`](../plasma/applets/com.arasaka.launcher) package into the
data home's `plasma/plasmoids/` and stages runtime reconciliation files under
`$HOME/.local/libexec/arasaka-kde/`.

It retries reconciliation for roughly ten seconds and verifies both live host
readiness and managed-panel removal. A saved `ready=true` alone is insufficient:
the loaded host must acknowledge the current session token before panel removal.
Failures are reported as failures, not successful installation.

Standalone application preserves wallpaper choices and desktop-icon policy.
It still reconciles layout and display priority. Unmanaged panels remain; their
launchers may take precedence through Plasma's normal shortcut routing.

## Displays and host identity

The popup keeps its original desktop owner to avoid an embedded-widget migration
bug in Plasma 6.7. On each opening it resolves the primary connector supplied by
the display reconciler, rather than assuming Qt screen order equals KDE priority.
An existing host can be retargeted while Plasma assigns desktops to screens;
creating a new host requires a primary desktop in the current activity.

Physical unplug/replug, suspend, and login with a disconnected owner display are
useful host-specific checks beyond the automated fixture suite.

## Updating loaded QML

**An already-loaded host may require an explicit Plasma restart.** Replacing files
cannot reliably refresh its QML in place. In that case the installer stages and
backs up files, leaves existing bars in place, keeps the watcher paused, and exits
with restart instructions.

Save your work, log out and back in, then rerun `./bin/apply-launcher`. The installer
does not restart Plasma automatically. A private `launcher-restart.json` marker
prevents the same session from mistaking cached code for the new host; successful
convergence clears it and resumes a previously active watcher.

The install process pauses the display watcher and stops its reconcile service.
Normally it resumes the watcher only if it was already active. The scoped command
does not enable or disable units. Full deployment uses `--install-only` to stage
first; that option still requires a live session and does not claim readiness.

## Backups and testing

The printed `launcher-*` backup contains the previous `plasmashellrc`,
`plasma-org.kde.plasma.desktop-appletsrc`, launcher package, and runtime files when
present. Backups are owner-only and may contain personal settings.

Use the [launcher recovery procedure](troubleshooting.md#restore-the-launcher)
with the backup preceding the unwanted change, not a later retry.

Installer fixtures run under `make test`. For the opt-in native integration test,
run inside a working Wayland session:

```sh
python3 tests/launcher_smoke.py
```

It uses isolated settings and a private D-Bus session, briefly displaying real
Kickoff and tray components. It checks search, keyboard/mouse launching, scrolling,
view switching, tray interaction, positioning, readiness, and dismissal. Temporary
desktop entries run marker-file commands; `kbuildsycoca6` indexes them. The
clipboard applet needs a real window system, so Qt's offscreen backend is not
supported. Missing-service warnings on the isolated bus are expected.
