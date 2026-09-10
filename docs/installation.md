# Installation

[Docs](README.md) / Installation

Arasaka KDE is an opinionated, source-built Plasma setup. Start by checking the
target stack, then prepare dependencies before applying live configuration.

## Compatibility

| Layer | Documented deployment |
| --- | --- |
| Operating system | TUXEDO OS on **Debian testing/forky** |
| Architecture | amd64 |
| Session | KDE Plasma **Wayland** |
| Plasma / KWin | 6.7; live integration exercised on 6.7.2 with 6.7.4 libraries |
| Qt | 6.10.2 on the documented host |
| KDE Frameworks | 6.28 on the documented host |
| Wallpaper renderer | OpenGL required |

This target is specifically the Debian-based setup above, not a claim about every
TUXEDO OS release. Other distributions, X11 desktop sessions, and different Plasma
versions need their own validation. Native KWin plugins and private Plasma APIs
should be rechecked after upgrades.

Public CI uses an isolated Debian 13 environment for repository and native-rain
checks. It does not install or certify the full desktop or PLM. See
[the test matrix](development.md#test-matrix).

## Get the source

```sh
git clone https://github.com/sne11ius/arasaka-kde.git
cd arasaka-kde
```

Current instructions follow `main`. To reproduce a tagged release, use its source
and release notes together. The initial `v0.1.0` source release has no binary assets
and does not contain all current rain and window-management features.

## Prerequisites

Full dependency provisioning is not implemented. Install the following through
your distribution's package manager before deployment; package names and native
plugin availability depend on the exact KDE stack.

### Desktop tools and visual components

- Python **3.12+**, Bash, `curl`, `sha256sum`, `patch`, `jq`, and standard Unix tools.
- KDE KConfig tools: `kreadconfig6` and `kwriteconfig6`.
- `qdbus6`, `kpackagetool6`, `kscreen-doctor`, and `kbuildsycoca6`.
- Plasma's `plasma-apply-colorscheme`, `plasma-apply-desktoptheme`, and
  `plasma-apply-cursortheme`; user-session `systemctl` and D-Bus tools.
- Plasma's stock **Kickoff** and **System Tray** applets; the application runner
  (`krunner_services`) enabled in KDE Search settings.
- **Klassy**, **Kvantum** with **KvFlatRed**, and Breeze cursors.
- Fonts: **Inter**, **JetBrains Mono**, and **Rajdhani SemiBold**.
- Better Blur DX is optional: the deployment falls back to Plasma's Blur when the
  native effect is unavailable. It is not automatically built by `apply-live`.

The component manifest also records retained upstream components. Being listed in
the manifest does not mean every component is installed or active by default.

### Shader build

- CMake **3.22+**, a **C++20** compiler, `pkg-config`, and KDE Extra CMake Modules.
- Qt **6.6+** development packages for Core, Gui, Quick, Qml, OpenGL, Network,
  Multimedia, and DBus.
- Frameworks 6 development packages for Config, I18n, and Package.
- Plasma and PlasmaQuick development packages.
- `rsvg-convert` for rendering the original SVG artwork.

The build follows upstream CMake checks for optional dependencies. By default it
uses at most four parallel jobs; reduce memory use with:

```sh
ARASAKA_SHADER_BUILD_JOBS=2 ./bin/apply-shader-wallpaper --install-only
```

### Window-policy build

The managed tiler also needs KWin development headers/library, Qt Quick/DBus/Widgets,
and Frameworks 6 Config and WindowSystem development packages. Its C++20 helper
is built against your KWin installation.

### Login packages

PLM has additional, newer version requirements. Use the
[login build guide](login.md#build-the-packages) and the authoritative
[`packaging/plasmalogin/debian/control`](../packaging/plasmalogin/debian/control).
Do not substitute Neon repositories for missing dependencies.

## Apply the complete desktop

Run **without sudo**, inside the target Plasma session:

```sh
./bin/apply-live
```

The command stages the launcher first, installs artwork and visual components,
builds and activates Interactive Rain, applies colors/fonts/application styling,
configures window policy and effects, applies the lock-screen background, and
enables display reconciliation.

It expects dependencies to exist. It does not offer a full-desktop `--dry-run`,
automatic dependency installation, or transactional rollback. Keep your own
desktop backup before first deployment. The [recovery guide](troubleshooting.md)
explains the available per-component backups.

The **PLM login screen is a separate system deployment**. Complete its
[installation or update procedure](login.md) to carry the shared background to
the greeter after reboot.

## Scoped commands

| Command | Changes |
| --- | --- |
| `./bin/apply-launcher` | Launcher package/runtime and layout/display-priority reconciliation |
| `./bin/apply-shader-wallpaper --install-only` | Build and install user-local shader assets, without session calls |
| `./bin/apply-shader-wallpaper` | Build/install assets and explicitly activate desktop rain defaults |
| `./bin/apply-lockscreen` | Installed shared background settings for the session locker |
| `./bin/apply-window-policy` | Managed Polonium adaptation, native helper, and tiling configuration |
| `./bin/apply-window-effects` | TV Glitch packages and effect settings |
| `./bin/apply-auth-window-rules` | Keep-above rules for pinentry and SSH prompts |
| `./bin/build-plm` | Build and inspect two local login packages; no installation |

Launcher-only deployment preserves wallpaper and desktop-icon choices. Full
deployment's display watcher opts into hiding desktop icons and initializing rain
on desktops that are not already using the shader plugin.

## After applying

Read each command's output and keep its printed backup path. A successful
configuration readback confirms saved settings; the next real host start verifies
rendering and interaction. Cached QML/native modules can require an explicit
logout/login or Plasma restart, as described in [troubleshooting](troubleshooting.md).

At your next normal lock and reboot, check that rain animates and receives hover
and click input on each intended screen. Clock preference and authentication/lock
policy are preserved by background-only updates.

## Updating

Review source changes, update your checkout, and reapply the relevant scoped
commands. Background changes cover all three surfaces: update user-local assets
and locker configuration, then build/install the system packages required by PLM.
See [wallpaper updates](wallpaper.md#apply-the-shared-background) and
[existing PLM installations](login.md#update-an-existing-plm-installation).
