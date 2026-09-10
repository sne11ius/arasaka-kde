# Windows, tiling, and effects

[Docs](README.md) / Windows

## Automatic tiling

The managed Polonium adaptation uses forced **Binary Tree / Shallow** insertion,
**Swap Insert Side**, and **8 logical px padding**. New windows split the
least-deep branch: the third splits the right half, the fourth the left. Placement
is independent of focus; rotation and active-tile insertion are disabled.

Application windows and dialogs tile automatically. Drag by the title bar or use
**Super + left-drag** to move between displays. A dragged window is temporarily
released, then joins the destination layout on drop. Same-display drops retile;
cancelling restores the original display.

| Shortcut | Result |
| --- | --- |
| Super + H/J/K/L | Focus adjacent tiles |
| Super + Shift + H/J/K/L | Rearrange windows |
| Super + Ctrl + H/J/K/L | Resize shared tile boundaries |

Mouse resizing is cancelled. Maximize, fullscreen, manual untiling, and the old
floating toggle cannot leave ordinary windows outside the layout. Minimize,
restore, and close remain available. Alternative engines and per-output settings
are disabled for the managed policy.

### Deliberate exceptions

- **GeForce NOW:** its `GeForceNOW` application window may enter fullscreen and
  rejoins the layout when fullscreen ends.
- **Stream Deck Quake Konsole:** the native helper validates the ownership and
  running Konsole executable behind `/tmp/konsole-quake.pid`, then selects one
  non-transient top-level window from that process. This is the sole floating
  application exception. Ordinary Konsole windows and dialogs still tile.
- Menus, tooltips, desktop surfaces, and other non-application surfaces are not tiles.

The helper uses process identity, not title matching or a blanket Konsole-class
exclusion. The Quake terminal retains its existing borderless, keep-above toggle.

### Decorations and display changes

Applications keep their native decoration preference. Client-decorated apps keep
their own controls; apps such as Dolphin receive a KDE title bar. The retired
catch-all `arasaka-frame` rule and Klassy titlebar-hiding exception are disabled.
Thin outlines remain off.

Fixed-size dialogs get enough maximum-size allowance to join tiles, while their
minimum content sizes remain respected. Display removal/reconnection rebuilds
trees from current membership, checks KWin's live output identities, and disconnects
retired callbacks. One failed rebuild cannot permanently hold the event gate.

### Apply and inspect

```sh
./bin/apply-window-policy
```

Run in the target Plasma session without sudo. The command fetches the pinned
Polonium v1.2.1 package, applies `lib/arasaka_polonium.py`, builds the native helper,
and installs `kwin/scripts/arasaka-polonium` under the data home. A previously
installed upstream Polonium package is retained but disabled; the command does
not install a separate upstream package. Settings live in `[Script-arasaka-polonium]` in
`kwinrc`; upstream exclusions do not override this policy.

Build dependencies are listed in [installation](installation.md#window-policy-build).
Before replacement it saves `kwinrc`, `kwinrulesrc`, `klassy/klassyrc`, and the prior
managed package in a private `window-policy-*` backup.

The tiler reloads without restarting KWin, Plasma, or applications. Versioned
module paths avoid stale QML/plugin caches. Success requires the live helper to
report the expected source versions and visible application-window state.

Read its report without changing settings:

```sh
qdbus6 org.kde.KWin /ArasakaWindowPolicy org.arasaka.WindowPolicy1.report
```

Fallback: disable `arasaka-polonium` in **KWin Scripts** to stop managed tiling.
You can re-enable upstream `polonium` if you previously installed it. Alternatively,
restore the saved settings/package and reconfigure KWin. Restoring the old frame
rule also restores its duplicate-decoration behavior.

## Window effects

Open, close, minimize, and restore use **TV Glitch at 700 ms**. Launcher, tray,
menus, dropdowns, and tooltips use **300 ms** transitions. Plasma's global animation
speed scales these durations.

```sh
./bin/apply-window-effects
```

The command fetches the SHA-256-pinned Burn-My-Windows v48 TV Glitch package and
creates two effects:

| Effect | Role |
| --- | --- |
| `kwin6_effect_tv_glitch` | Upstream open/close shader effect |
| `arasaka_tv_glitch_minimize` | Local minimize/restore and popup adaptation |

The local overlay reuses upstream assets; it is not a standalone complete package.
It supports interrupted-animation reversal and cleanup. Popup handling applies
to separate KWin windows, not menus drawn inside another application's window.
Lock-screen surfaces and outlines are excluded.

Magic Lamp, Squash, Scale, Popup Fade, and Sliding Popups are disabled to avoid
competing transitions. The standalone command leaves Better Blur DX alone.
Packages install under the data home's `kwin/effects/`, with prior packages and
`kwinrc` saved to `window-effects-*` before replacement.

Read loaded state:

```sh
qdbus6 org.kde.KWin /Effects org.kde.kwin.Effects.isEffectLoaded kwin6_effect_tv_glitch
qdbus6 org.kde.KWin /Effects org.kde.kwin.Effects.isEffectLoaded arasaka_tv_glitch_minimize
```

For a quick fallback, choose **Scale** for Window Open/Close and **Magic Lamp** for
Window Minimize in **System Settings → Animations**. Reapplying the rice selects
TV Glitch again. Recheck third-party effects after Plasma upgrades.

## Authentication prompts

GPG PIN/passphrase (`pinentry-qt`) and SSH (`ksshaskpass`) prompts stay in KWin's
keep-above layer. Matching covers their Wayland app IDs and XWayland classes,
including normal windows and dialogs. Prompts can appear above the Quake terminal
without changing its keep-above behavior.

```sh
./bin/apply-auth-window-rules
```

The scoped command preserves existing rules, saves `kwinrulesrc` and `kwinrc` in
an `auth-window-rules-*` backup, and reloads KWin rules. It does not restart
applications, change focus policy, or modify credentials, key agents, SSH/GPG
configuration, or credential storage.

Under managed forced tiling these prompts **tile like other dialogs**. The
standalone authentication command only manages stacking rules, not tiling.

## Testing

The controller regressions run against the adapted pinned engine under Node.js
as part of `make test`. The [development guide](development.md#native-and-live-integration)
also documents a private virtual-KWin suite for decorations, real tile membership,
dragging, fixed-size dialogs, PID validation, output recreation, and reloads.
Physical suspend/resume and real monitor hotplug still require host observation.
