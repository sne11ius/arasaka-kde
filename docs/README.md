# Documentation

[← Arasaka KDE](../README.md)

Pick a path. You can explore the look, install one component, or learn how the
whole desktop is assembled.

## Use the desktop

| Guide | What's inside |
| --- | --- |
| [Installation](installation.md) | Compatibility, prerequisites, first deployment, and command scope |
| [Wallpaper](wallpaper.md) | Interactive Rain, desktop/lock/login parity, settings, and gallery preservation |
| [Launcher](launcher.md) | Search, Kickoff, tray, deployment, and cached-QML recovery |
| [Windows](windows.md) | Tiling, keyboard controls, decorations, effects, and authentication prompts |
| [PLM login](login.md) | Package builds, fresh migration, updates, clock preference, and SDDM recovery |
| [Customization](customization.md) | Palette, fonts, application styling, artwork, and performance |
| [Troubleshooting](troubleshooting.md) | Symptoms, read-only diagnostics, backups, and recovery |

## Work on the project

- [Recorded showcase](showcase.md): generate the real login-to-desktop film locally or in CI.
- [Development](development.md): source map, test dependencies, native checks,
  and the distinction between fixture tests and a real desktop session.
- [Automation](automation.md): every badge's backing service, coverage boundaries,
  local checks, and a short maintainer activation checklist.
- [Contributing](../CONTRIBUTING.md): small, reproducible contributions welcome.
- [Attribution](../ATTRIBUTION.md): pinned upstream ingredients and license scope.
- [Support](../SUPPORT.md) · [Security](../SECURITY.md) · [Code of conduct](../CODE_OF_CONDUCT.md).

## Reading conventions

Commands are run from the repository root unless a guide says otherwise. Desktop
commands run as the normal user in the target Plasma Wayland session. Commands
with `sudo` are explicit system-installation or recovery steps for you to run.

The guides describe the current source tree. The
[release notes](https://github.com/sne11ius/arasaka-kde/releases) describe tagged
snapshots. Files under `docs/superpowers/` are historical design and implementation
records; use these public guides for current instructions.
