# Project expectations

## Wallpaper parity

The desktop, idle/session lock screen, and PLM login screen after reboot are one
managed background experience. A request to change the background applies to all
three by default, including artwork, shader/physics, animation quality/speed,
pointer hover and click effects. Do not ask the user to repeat this scope or to
confirm that interaction is included. Surface-specific differences require an
explicit user request or a concrete host limitation that must be resolved/reported.

Keep the shared defaults and parity tests current. Verify actual input delivery:
PLM's greeter and wallpaper are separate processes, so enabling a shader setting
alone is insufficient. Use the same native rain simulation and passive observer;
forward only screen-local pointer activity across PLM's existing session bus.
The obscured desktop must still reject input while its session is locked.

For background changes, update the user-local assets used by desktop/locker and
build the system packages used by PLM. Clearly report any outstanding privileged
installation or next-session visual check. The user executes privileged commands;
do not invoke pkexec or restart the display manager from the running desktop.

Preserve authentication, lock policy, and the user's clock preference when changing
backgrounds. The greeters animate while visible; desktop window-based pausing is
a host-specific lifecycle rule, not a different visual effect.
