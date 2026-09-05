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
