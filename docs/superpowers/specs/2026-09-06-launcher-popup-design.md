# Panel-Free Launcher

## Approved Interaction

Remove both Arasaka-managed panels: the top command strip and laptop telemetry
rail. Super opens an already-expanded native KDE application menu, with search
ready for typing and the native system tray underneath. Center the popup on the
main output, regardless of pointer or active-window location. Super, Escape,
clicking outside, or launching an application
closes it. Native tray subpopups must remain usable. Preserve the dark/red theme,
unmanaged panels, wallpapers, and display configuration.

## Architecture

Target the installed Plasma 6.7 Wayland session. A QML CustomEmbedded containment
hosts real Kickoff and System Tray applets in a centered Plasma dialog. Advertise
the launcher capability to integrate with Plasma's existing Meta action. Keep
applet instances persistent across layout reconciliation. No copied Kickoff or
tray internals, patched KDE packages, telemetry, or hidden edge panel.

The host lives on the desktop with no normal visible representation. Prefer a
single instance and resolve the primary connector supplied by the display
reconciler when opening. Native tray details
remain secondary KDE popups rather than being reimplemented inline.

Create missing native children through Plasma's public widget-drop API, not its
private createApplet slot. Keep the original owner: Plasma 6.7 corrupts nested
configuration when transferring a CustomEmbedded applet between desktops. KDE's
native launcher routing can prefer an unmanaged panel launcher; do not silently
overwrite the user's shortcut configuration to resolve that case.

## Deployment and Failure Handling

Provide a scoped deployment command, backing up the affected Plasma configuration
and managed package before modification. Validate package availability before
removing bars. Retain an accessible terminal during live validation and leave the
old bars intact if the replacement cannot load. Reconciliation must not recreate
the removed bars or duplicate popup hosts. Do not commit personal configuration.
Require a fresh bus/shell-owner token acknowledgement from the loaded QML before
panel removal. Wallpaper/icon updates are opt-in for full-theme deployment only.

## Verification

Run layout convergence tests and the existing suite. Exercise the real QML host,
including component loading, opening, closing, and placement. Verify native
launcher activation, search, and tray focus in the live session where tooling
permits; clearly identify interactions that still require user confirmation.
