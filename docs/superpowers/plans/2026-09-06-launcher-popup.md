# Launcher Popup Implementation Plan

> **For agentic workers:** Use executing-plans to implement these tasks in order.

**Goal:** Replace both managed bars with a centered, Super-triggered KDE menu and tray.

**Architecture:** A desktop-hosted QML embedded containment owns stock Kickoff and
System Tray applets. Its separate Plasma dialog handles centering and dismissal;
the layout and scoped deployment own installation and persistent placement.

**Tech Stack:** Plasma 6.7, Qt Quick, JavaScript, Bash, Python/Node tests.

**Spec:** `docs/superpowers/specs/2026-09-06-launcher-popup-design.md`

## Global Constraints

- Target the installed Plasma 6.7 Wayland session.
- No copied Kickoff or tray internals, patched KDE packages, telemetry, or hidden edge panel.
- Preserve unmanaged panels, wallpapers, and display configuration.
- Do not commit personal configuration or make unrequested commits.

## Task 1: Native Popup Host

Files: `plasma/applets/com.arasaka.launcher/metadata.json`,
`plasma/applets/com.arasaka.launcher/contents/ui/main.qml`, and QML integration tests.

- [x] Establish a failing real-component smoke test for the missing package.
- [x] Add launcher metadata with `CustomEmbedded` and `org.kde.plasma.launchermenu`.
- [x] Restore/create stock applets using `Containment.applets`, `processMimeData`, and
  `itemFor`; force Kickoff's full representation, keeping tray native.
- [x] Implement a centered Plasma dialog and synchronize activation/dismissal.
- [x] Test loading in an isolated configuration before changing the live layout.

## Task 2: Panel-Free Layout and Deployment

Files: `plasma/layout.js`, `bin/apply-launcher`, `bin/apply-live`,
`tests/plasma_layout_harness.js`, `tests/plasma_layout_test.py`, deployment tests.

- [x] Change the layout tests to require no managed panels and one persistent
  desktop launcher across repeated runs. Run `python3 tests/plasma_layout_test.py`
  and observe failures against the old layout.
- [x] Install/check the host before removing only managed panels. Preserve its ID
  and configuration on reconciliation; do not change wallpaper policy.
- [x] Add a scoped installer with local backups and package/layout preflight,
  and integrate package installation into `apply-live`.
- [x] Test installer effects with isolated HOME and stubbed session commands.

## Task 3: Review and Live Validation

Files: `README.md` and any implementation corrections established by testing.

- [x] Run `make test`, native QML checks, and `git diff --check`.
- [x] Review lifecycle, persistence, native submenu focus, and hotplug handling.
- [x] Deploy using the scoped command only after native components load.
- [x] Exercise Meta open/close, Escape, search, tray submenus, and screen placement
  where automation permits. Record any remaining manual checks honestly.
- [x] Document the command, behavior, backup location, and recovery procedure.

Physical hotplug and fresh login with the original display disconnected were not
exercised. The live shortcut check invoked the KGlobalAccel action bound to Super;
typing, Escape, and tray interaction used real Qt key events/native applets in the
isolated Wayland process. No personal configuration or commits were added.
