"""Record the real PLM/Plasma guest and a short, repeatable desktop tour."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import shlex
import subprocess
import time

from PIL import Image, ImageFilter

from .media import encode_inline, file_sha256, inspect_video, make_poster


def record_tour(guest, qmp, directory, config, env):
    directory = Path(directory)
    width, height = config["display"]["width"], config["display"]["height"]
    chapters = []

    def xdo(*args):
        return subprocess.run(["xdotool", *map(str, args)], env=env, check=True,
                              capture_output=True, text=True, timeout=15).stdout.strip()

    def key(keys):
        xdo("key", "--clearmodifiers", keys)

    def type_text(text):
        xdo("type", "--clearmodifiers", "--delay", "35", "--", text)

    def move(x, y, seconds=.6):
        position = dict(line.split("=", 1) for line in xdo("getmouselocation", "--shell").splitlines())
        start_x, start_y = int(position["X"]), int(position["Y"])
        count = max(1, round(seconds * 25))
        for step in range(1, count + 1):
            amount = (1 - math.cos(math.pi * step / count)) / 2
            xdo("mousemove", round(start_x + (x - start_x) * amount),
                round(start_y + (y - start_y) * amount))
            time.sleep(seconds / count)

    def screenshot(name):
        path = directory / (name + ".png")
        qmp.execute("screendump", {"filename": str(path), "format": "png"})
        return path

    def session(code, timeout=30):
        prelude = ("import os,sys,json,subprocess; "
                   "sys.path.insert(0,'/home/demo/arasaka-kde/scripts/showcase'); "
                   "from guest_setup import session_environment; "
                   "env=session_environment(); os.environ.update(env); ")
        return guest.run("python3 -c " + shlex.quote(prelude + code), timeout=timeout).stdout.strip()

    def desktop_command(args):
        return session("r=subprocess.run(" + repr(args) + ",env=env,check=True,capture_output=True,text=True); print(r.stdout)")

    def wait_session(timeout=120):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                session("print('ready')", timeout=15)
                return
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                time.sleep(1)
        raise RuntimeError("the real Plasma session did not become ready")

    def window_action(body):
        code = ("from pathlib import Path; "
                "p=Path('/home/demo/.local/state/showcase-window-action.js'); "
                "p.write_text(" + repr(body) + "); "
                "subprocess.run(['qdbus6','org.kde.KWin','/Scripting',"
                "'org.kde.kwin.Scripting.unloadScript','showcase-action'],env=env,capture_output=True); "
                "subprocess.run(['qdbus6','org.kde.KWin','/Scripting',"
                "'org.kde.kwin.Scripting.loadScript',str(p),'showcase-action'],env=env,check=True,capture_output=True); "
                "subprocess.run(['qdbus6','org.kde.KWin','/Scripting',"
                "'org.kde.kwin.Scripting.start'],env=env,check=True,capture_output=True)")
        session(code)

    def rain_clicks(label):
        # Find compact drop outlines in the actual frame, away from the login
        # form/emblem. This keeps the clicks on water as the live simulation moves.
        frame = screenshot(label)
        with Image.open(frame) as image:
            edges = image.convert("L").filter(ImageFilter.FIND_EDGES)
            edges = edges.point(lambda value: 255 if value > 20 else 0).filter(ImageFilter.MaxFilter(3))
            pixels = {i for i, value in enumerate(edges.getdata()) if value}
        candidates = []
        while pixels:
            first = pixels.pop()
            component, pending = [first], [first]
            while pending:
                point = pending.pop()
                for other in (point - width, point + width,
                              point - 1 if point % width else -1,
                              point + 1 if point % width < width - 1 else -1):
                    if other in pixels:
                        pixels.remove(other)
                        pending.append(other)
                        component.append(other)
            if not 12 <= len(component) <= 1200:
                continue
            xs, ys = [p % width for p in component], [p // width for p in component]
            left, right, top, bottom = min(xs), max(xs), min(ys), max(ys)
            x, y = (left + right) // 2, (top + bottom) // 2
            if (9 <= right - left <= 45 and 9 <= bottom - top <= 55
                    and .08 * width < x < .92 * width and .12 * height < y < .86 * height
                    and (x < .35 * width or x > .65 * width)):
                candidates.append((len(component), x, y))
        if not candidates:
            raise RuntimeError("no visible drops found for the click demonstration")
        print(f"Clicking {min(3, len(candidates))} visible drop targets", flush=True)
        for _, x, y in sorted(candidates, reverse=True)[:3]:
            move(x, y, .4)
            xdo("click", "1")
            time.sleep(.6)
        move(width * .22, height * .32, .8)
        move(width * .78, height * .68, 1.8)

    def open_quake():
        session("from pathlib import Path; p=Path('/home/demo/.zshrc'); "
                "p.write_text(p.read_text()+\"\\nPROMPT='%F{red}%1~%f %# '\\n\")")
        desktop_command(["kwriteconfig6", "--file", "/home/demo/.local/share/konsole/Showcase.profile",
                         "--group", "Appearance", "--key", "Font", "JetBrains Mono,9,-1,5,400,0,0,0,0,0"])
        style = (Path(__file__).resolve().parents[2] / "showcase/streamdeck/quake.qss").read_text()
        directory_name = "/home/demo/.local/share/konsole"
        style_path = directory_name + "/quake.qss"
        layout_path = "/home/demo/.local/state/showcase-quake.json"

        def pane(number, lines):
            return {"SessionRestoreId": number, "Columns": 85, "Lines": lines,
                    "WorkingDirectory": "/home/demo/arasaka-kde"}

        layout = {"Orientation": "Horizontal", "Widgets": [
            pane(1, 38),
            {"Orientation": "Vertical", "Widgets": [
                pane(2, 18),
                pane(3, 18),
            ]},
        ]}
        session("from pathlib import Path; "
                f"Path({style_path!r}).write_text({style!r}); "
                f"Path({layout_path!r}).write_text({json.dumps(layout)!r})")
        for group, key_name, value in (
                ("SplitView", "SplitViewVisibility", "AlwaysHideSplitHeader"),
                ("SplitView", "SplitDragHandleSize", "SplitDragHandleMedium"),
                ("TabBar", "TabBarPosition", "Bottom")):
            desktop_command(["kwriteconfig6", "--file", "konsolerc", "--group", group,
                             "--key", key_name, value])
        args = ["konsole", "--separate", "--profile", "Showcase", "--hide-menubar",
                "--hide-toolbars", "--show-tabbar", "--stylesheet", style_path, "--layout", layout_path]
        pid = int(session("from pathlib import Path; p=subprocess.Popen(" + repr(args) + ",env=env,"
                          "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,"
                          "start_new_session=True); Path('/tmp/konsole-quake.pid').write_text(str(p.pid)+'\\n'); print(p.pid)"))
        bus = f"org.kde.konsole-{pid}"
        deadline = time.monotonic() + 15
        while True:
            try:
                active = desktop_command(["qdbus6", bus, "/Windows/1", "currentSession"])
                if active.isdigit() and int(active) > 0:
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError("the Quake Konsole did not create its panes")
                time.sleep(.2)
            except subprocess.CalledProcessError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("the Quake Konsole did not open")
                time.sleep(.2)
        window_action(f"const w=workspace.windowList().find(w=>w.pid==={pid}); "
                      "const g=workspace.activeScreen.geometry; w.noBorder=true; w.keepAbove=true; "
                      "w.keepBelow=false; w.skipTaskbar=true; w.skipPager=true; w.skipSwitcher=true; "
                      "w.frameGeometry={x:g.x,y:g.y,width:g.width,height:Math.round(g.height*.755)}; "
                      "workspace.activeWindow=w;")
        return pid, bus, active

    def pane_command(x, y, command, hold=3):
        move(width * x, height * y, .5)
        xdo("click", "1")
        type_text(command)
        key("Return")
        time.sleep(hold)

    windows = xdo("search", "--onlyvisible", "--name", "arasaka-showcase").splitlines()
    if not windows:
        raise RuntimeError("QEMU's recording window is unavailable")
    xdo("windowactivate", "--sync", windows[0])
    move(width * .12, height * .5, .2)
    # A normal key wakes PLM. Escape would switch its outputs off through DPMS.
    key("Shift_L")
    time.sleep(2)
    master = directory / "showcase.mp4"
    command = ["ffmpeg", "-y", "-f", "x11grab", "-framerate", "30", "-video_size",
               f"{width}x{height}", "-draw_mouse", "0", "-i", env["DISPLAY"], "-an",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-threads", "2",
               "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(master)]
    with (directory / "recording.log").open("w") as log:
        recorder = subprocess.Popen(command, env=env, stdin=subprocess.PIPE, stdout=log, stderr=log)
        started = time.monotonic()

        @contextmanager
        def chapter(name):
            print("Recording: " + name, flush=True)
            item = {"name": name, "start": time.monotonic() - started}
            yield
            item.update(end=time.monotonic() - started, verified=True)
            chapters.append(item)
            screenshot(name + "-end")
            (directory / "chapters.json").write_text(json.dumps(chapters, indent=2) + "\n")

        try:
            with chapter("login"):
                time.sleep(5)
                move(width / 2, height * .60, .7)
                xdo("click", "1")
                time.sleep(1)
                key("ctrl+a")
                type_text(config["guest"]["password"])
                key("Return")
                wait_session()
                time.sleep(4)
            with chapter("desktop-rain"):
                rain_clicks("desktop-rain")
                time.sleep(8)
            with chapter("quake-konsole"):
                quake_pid, quake_bus, layout_session = open_quake()
                time.sleep(2)
            with chapter("commands"):
                pane_command(.25, .20, "btop", 4)
                pane_command(.78, .12, "fastfetch --logo small --structure OS:DE:WM:Theme:Icons", 4)
                pane_command(.78, .48, "git log -6 --oneline -- native/rain", 4)
                pane_command(.78, .48,
                             "clear; batcat --paging=never --color=always --line-range=1:12 native/rain/dropletsimulation.h", 5)
            with chapter("tabs-and-splits"):
                desktop_command(["qdbus6", quake_bus, "/Windows/1", "newSession",
                                 "Arasaka Showcase", "/home/demo/arasaka-kde"])
                time.sleep(1)
                type_text("pwd")
                key("Return")
                time.sleep(1)
                type_text("ls --color=auto")
                key("Return")
                time.sleep(3)
                desktop_command(["qdbus6", quake_bus, "/Windows/1", "setCurrentSession", layout_session])
                move(width * .5, height * .27, .5)
                time.sleep(.6)
                xdo("mousedown", "1")
                move(width * .56, height * .27, .8)
                xdo("mouseup", "1")
                time.sleep(2)
                screenshot("quake-splits")
            with chapter("menu"):
                key("Super_L")
                time.sleep(2)
                key("Tab")
                key("space")
                time.sleep(4)
                screenshot("launcher-menu")
                key("Escape")
                time.sleep(1)
            with chapter("quake-toggle"):
                window_action(f"workspace.windowList().find(w=>w.pid==={quake_pid}).minimized=true;")
                time.sleep(2)
                window_action(f"const w=workspace.windowList().find(w=>w.pid==={quake_pid}); w.minimized=false; workspace.activeWindow=w;")
                time.sleep(3)
            with chapter("final"):
                move(width - 15, height - 15, .8)
                time.sleep(10)
        finally:
            recorder.communicate(b"q\n", timeout=60)
        if recorder.returncode:
            raise RuntimeError("FFmpeg recording failed; see recording.log")

    info = inspect_video(master)
    if info["width"] != width or info["height"] != height or info["duration"] < 60:
        raise RuntimeError("recording has incorrect dimensions or is incomplete")
    inline = directory / "showcase-inline.mp4"
    encode_inline(master, inline)
    make_poster(master, directory / "poster.png", chapters[-1]["start"] + 2)
    provenance = {
        "schema": 1, "source": (directory / "source-sha").read_text().strip(),
        "generated_at": datetime.now(timezone.utc).isoformat(), "environment": config,
        "video": info, "chapters": chapters,
        "files": {name: file_sha256(directory / name) for name in
                  ("showcase.mp4", "showcase-inline.mp4", "poster.png", "chapters.json")},
    }
    ci = directory / "ci.json"
    if ci.exists():
        provenance["ci"] = json.loads(ci.read_text())
    (directory / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print(f"Film ready: {master} ({info['duration']:.1f}s)", flush=True)
