"""Cold-boot a prepared guest and film it without changing the prepared disk."""

from contextlib import ExitStack
import json
import os
from pathlib import Path
import secrets
import subprocess

from .machine import Guest, QMP
from .prepared import load
from .tour import record_tour


def record_prepared(workspace, run, config, previous):
    from .runner import managed_process, wait_for

    previous = Path(previous).resolve()
    if not previous.is_relative_to(workspace.resolve()):
        raise ValueError("prepared guest must belong to this showcase workspace")
    source = (run / "source-sha").read_text().strip()
    load(previous, source)
    with ExitStack() as stack:
        log = stack.enter_context((run / "transport.log").open("w"))
        overlay = run / "movie.qcow2"
        subprocess.run(["qemu-img", "create", "-f", "qcow2", "-F", "qcow2", "-b",
                        str(previous / "guest.qcow2"), str(overlay)], check=True, stdout=log, stderr=log)
        authority = run / "Xauthority"
        authority.touch(mode=0o600)
        subprocess.run(["xauth", "-f", str(authority), "add", ":99", ".", secrets.token_hex(16)],
                       check=True, stdout=log, stderr=log)
        env = dict(os.environ, DISPLAY=":99", XAUTHORITY=str(authority), GDK_BACKEND="x11",
                   LIBGL_ALWAYS_SOFTWARE="1", GSETTINGS_BACKEND="memory")
        width, height = config["display"]["width"], config["display"]["height"]
        xvfb = stack.enter_context(managed_process(
            ["Xvfb", ":99", "-screen", "0", f"{width}x{height}x24", "-nolisten", "tcp", "-auth", str(authority)],
            stdout=log, stderr=log))
        wait_for(lambda: subprocess.run(["xdpyinfo"], env=env, stdout=log, stderr=log).returncode == 0,
                 [xvfb], 30, "recorder display")
        wm = stack.enter_context(managed_process(["openbox", "--sm-disable"], env=env, stdout=log, stderr=log))
        wait_for(lambda: "window id #" in subprocess.run(
            ["xprop", "-root", "_NET_SUPPORTING_WM_CHECK"], env=env, capture_output=True, text=True).stdout,
                 [xvfb, wm], 30, "fullscreen window manager")
        command = json.loads((previous / "qemu-command.json").read_text())
        command = [argument.replace(str(previous / "guest.qcow2"), str(overlay))
                   .replace(str(previous / "qmp.sock"), str(run / "qmp.sock"))
                   .replace(str(previous / "console.log"), str(run / "console.log")) for argument in command]
        (run / "qemu-command.json").write_text(json.dumps(command, indent=2) + "\n")
        qemu = stack.enter_context(managed_process(command, env=env, stdout=log, stderr=log))
        processes = [qemu, xvfb, wm]
        wait_for((run / "qmp.sock").exists, processes, 30, "recording VM")
        qmp = stack.enter_context(QMP(run / "qmp.sock"))
        port = json.loads((previous / "boot-evidence.json").read_text())["ssh_port"]
        guest = Guest(port, previous / "id_ed25519")
        previous_boot = None

        def ready():
            try:
                result = guest.run("python3 /home/demo/arasaka-kde/scripts/showcase/guest_setup.py greeter-status",
                                   timeout=20)
                status = json.loads(result.stdout)
                return status.get("ready") is True and status.get("boot_id") != previous_boot
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError):
                return False

        wait_for(ready, processes, 240, "real PLM greeter")
        cursor_config = "/etc/environment.d/90-arasaka-showcase-cursor.conf"
        configured = guest.run(f"if test -f {cursor_config}; then cat {cursor_config}; fi").stdout
        if configured != "KWIN_FORCE_SW_CURSOR=1\n":
            guest.run("sudo install -d /etc/environment.d && "
                      f"printf 'KWIN_FORCE_SW_CURSOR=1\\n' | sudo tee {cursor_config} >/dev/null")
            previous_boot = guest.run("cat /proc/sys/kernel/random/boot_id").stdout.strip()
            guest.run("sudo -n systemctl reboot --no-block")
            wait_for(ready, processes, 240, "single-cursor greeter")
        qmp.execute("screendump", {"filename": str(run / "greeter-start.png"), "format": "png"})
        try:
            record_tour(guest, qmp, run, config, env)
        except BaseException:
            qmp.execute("screendump", {"filename": str(run / "failed-scene.png"), "format": "png"})
            try:
                (run / "guest-journal.log").write_text(guest.run("sudo journalctl -b --no-pager", timeout=30).stdout)
            except Exception:
                pass
            raise
        guest.run("sudo -n systemctl poweroff --no-block")
        qemu.wait(timeout=120)
