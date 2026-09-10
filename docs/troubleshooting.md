# Troubleshooting and recovery

[Docs](README.md) / Troubleshooting

Start with the command's exact error and printed backup path. A failed operation
should be investigated before repeated reapplication produces newer snapshots
of an already-changed configuration.

## Quick diagnosis

| Symptom | What to check |
| --- | --- |
| Required command or CMake package missing | [Installation prerequisites](installation.md#prerequisites); dependencies are not automatically installed |
| Launcher update asks for a restart | Cached QML: log out/in, then rerun `apply-launcher` |
| Super opens another menu | Another launcher on an unmanaged panel may own Plasma's launcher action |
| Empty application results | KDE's application runner must be enabled; stock Kickoff must be installed |
| Rain settings saved but old effect remains | Cached native module/QML or undiscovered package; explicitly start a new Plasma session |
| No hover or splashes | Check selected effect, mouse permission, host role, pause state, and the actual exposed surface |
| Login rain animates but ignores input | Install the known patched PLM package (`6.7.4-0arasaka2`) as well as the wallpaper package |
| Reconnected screen lacks rain | Check installed assets and display-watcher logs; initialization retries as desktops become ready |
| Shader installation refuses an import | Resolve the reported custom/bundled file collision before retrying |
| Windows stop retiling after hotplug | Inspect the native helper's report and current managed package version |
| Login clock preference appears unchanged | The greeter reads it on its next normal start; check file permissions |

## Read-only diagnostics

Run inside the target session:

```sh
plasmashell --version
kwin_wayland --version
kscreen-doctor --json
systemctl --user status arasaka-display-reconcile.path
journalctl --user -u arasaka-display-reconcile.service -n 80 --no-pager
qdbus6 org.kde.KWin /ArasakaWindowPolicy org.arasaka.WindowPolicy1.report
```

For the login manager:

```sh
systemctl status display-manager --no-pager
dpkg-query -W plasmalogin arasaka-login-wallpaper
kreadconfig6 --file /etc/plasmalogin.conf --group Greeter --key WallpaperPluginId
```

Status commands can exit nonzero when a unit is inactive; that output is useful
diagnostic information. Trim logs and redact private values before sharing them.
[What to include in an issue →](../SUPPORT.md)

## Rain and host input

A successful D-Bus/configuration readback proves selected settings, not rendering
or live input. Check the actual desktop, then the next normal lock and login:

1. Interactive Rain is selected and animation is running.
2. Mouse permission is enabled; click a visible drop rather than clear glass.
3. The desktop is exposed and not paused behind a maximized/fullscreen window.
4. The installed native module has been loaded by a fresh host.
5. For PLM, both the native wallpaper and patched frontend packages are current.

The desktop intentionally rejects input while locked. PLM needs its cross-process
bridge; the wallpaper setting alone cannot forward input from the greeter.

Do not force global cursor tracking or alter authentication to diagnose rain.
Use the [native test matrix](development.md#test-matrix) and the scoped host checks.

## Backups and recovery

Most user-local component backups are under:

```text
${XDG_STATE_HOME:-$HOME/.local/state}/arasaka-kde/backups/
```

| Prefix | Typical contents |
| --- | --- |
| `launcher-*` | Plasma settings, previous package, runtime files |
| `shader-wallpaper-*` | Plasma settings, previous wallpaper package, replaced artwork/shaders, layout snapshot |
| `lockscreen-*` | Previous `kscreenlockerrc` or a missing-file marker |
| `window-policy-*` | KWin/Klassy settings and previous managed tiler |
| `window-effects-*` | `kwinrc` and replaced effect packages |
| `auth-window-rules-*` | `kwinrulesrc` and `kwinrc` |

Use the **printed path from the operation you want to undo**. Backups are private
and may contain personal settings. There is no full-desktop transactional rollback.
Full deployment also creates some adjacent `.before-arasaka-*` application backups.

### Restore the launcher

1. Save work and stop `arasaka-display-reconcile.path` and
   `arasaka-display-reconcile.service` using `systemctl --user stop`.
2. Stop Plasma explicitly, or restore from another session while Plasma is not
   running. A running shell can overwrite restored configuration.
3. Restore the saved `plasma-org.kde.plasma.desktop-appletsrc` and `plasmashellrc`
   to the config home. Replace the managed launcher package and affected runtime
   files with the backup's `package/` and `runtime/` contents.
4. If a snapshot is absent, that source did not exist before installation. Remove
   only the newly installed managed package/files, not unrelated runtime content.
5. Remove the associated `arasaka-kde/launcher-restart.json` state marker, start
   Plasma, and resume the watcher only if it was active before the change.

### Restore desktop wallpaper assets

Stop Plasma first. Restore saved Plasma configuration, the affected package, and
replaced artwork/shaders from the backup preceding the unwanted change. Preserve
unrelated artwork and custom files. Restore runtime layout only when undoing a
separate integration change: the scoped shader installer snapshots that file but
does not modify it. Restore the wallpaper template, shared defaults and reconciler
as a matching set from `runtime/` when reverting their background policy. Then
start Plasma again.

### Fall back to a static lock screen

To switch only the locker wallpaper plugin without restoring old lock-policy keys:

```sh
kwriteconfig6 --file kscreenlockerrc --group Greeter --key WallpaperPlugin org.kde.image
```

The next normal lock uses the existing static-image configuration. If restoring
`kscreenlockerrc` wholesale, first account for clock or lock-policy changes made
since the snapshot.

### Restore windows or effects

For tiling, disable the managed `arasaka-polonium` script to stop its enforcement.
Re-enable upstream `polonium` only if it was separately installed, or restore the
saved package/settings and reconfigure KWin.
For transitions, choose Scale and Magic Lamp in System Settings. See
[window-management fallbacks](windows.md).

### Restore login

System background backups and migration snapshots are under
`/var/backups/arasaka-kde/`. Use [the PLM guide](login.md#recover-sddm) for the
standalone SDDM rollback or saved-package background recovery.

**Never restart the display manager from your running desktop as a refresh step.**
A login-manager restart can end the session. Use the next normal greeter start
or reboot when you are ready.
