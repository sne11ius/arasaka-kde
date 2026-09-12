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

    def open_terminal(command):
        args = ["konsole", "--separate", "--hide-menubar", "--profile", "Showcase",
                "-e", "zsh", "-ic", command + "; exec zsh"]
        session("p=subprocess.Popen(" + repr(args) + ",env=env,stdin=subprocess.DEVNULL,"
                "stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True); print(p.pid)")
        time.sleep(2)

    windows = xdo("search", "--onlyvisible", "--name", "arasaka-showcase").splitlines()
    if not windows:
        raise RuntimeError("QEMU's recording window is unavailable")
    xdo("windowactivate", "--sync", windows[0])
    move(width * .12, height * .5, .2)
    # PLM normally blurs the wallpaper while its password form is active.
    # Begin with its ordinary idle view, then reveal and use the real form.
    key("Escape")
    time.sleep(2)
    master = directory / "showcase.mp4"
    command = ["ffmpeg", "-y", "-f", "x11grab", "-framerate", "30", "-video_size",
               f"{width}x{height}", "-draw_mouse", "1", "-i", env["DISPLAY"], "-an",
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
            with chapter("launcher"):
                session("from pathlib import Path; p=Path('/home/demo/.zshrc'); "
                        "p.write_text(p.read_text()+\"\\nPROMPT='%F{red}%1~%f %# '\\n\")")
                desktop_command(["kwriteconfig6", "--file", "/home/demo/.local/share/konsole/Showcase.profile",
                                 "--group", "Appearance", "--key", "Font", "JetBrains Mono,9,-1,5,400,0,0,0,0,0"])
                desktop_command(["kwriteconfig6", "--file", "konsolerc", "--group", "MainWindow",
                                 "--group", "Toolbar mainToolBar", "--key", "Hidden", "--type", "bool", "true"])
                key("Super_L")
                time.sleep(2)
                type_text("Konsole")
                time.sleep(1)
                key("Return")
                time.sleep(3)
                type_text("fastfetch")
                key("Return")
                time.sleep(4)
                first_terminal = int(desktop_command(["pgrep", "-u", "1000", "-x", "konsole"]).splitlines()[0])
            with chapter("terminals"):
                open_terminal("batcat --color=always --paging=never --line-range=1:16 native/rain/dropletsimulation.h")
                open_terminal("git log -6 --oneline -- native/rain")
                window_action(f"workspace.activeWindow = workspace.windowList().find(w => w.pid === {first_terminal});")
                time.sleep(.5)
                key("ctrl+l")
                type_text("fastfetch --logo small --structure OS:DE:WM:Theme:Icons")
                key("Return")
                time.sleep(2)
                window_action("workspace.activeWindow = workspace.windowList().filter(w => w.resourceClass === 'org.kde.konsole').sort((a,b) => b.frameGeometry.height - a.frameGeometry.height)[0];")
                time.sleep(.5)
                key("ctrl+l")
                type_text("btop")
                key("Return")
                time.sleep(9)
            with chapter("effects"):
                window_action(f"const w = workspace.windowList().find(w => w.pid === {first_terminal}); workspace.activeWindow = w; w.minimized = true;")
                time.sleep(3)
                window_action(f"const w = workspace.windowList().find(w => w.pid === {first_terminal}); w.minimized = false; workspace.activeWindow = w;")
                time.sleep(3)
                time.sleep(2)
            with chapter("menu"):
                key("Super_L")
                time.sleep(2)
                key("Tab")
                key("space")
                time.sleep(4)
                screenshot("launcher-menu")
                key("Escape")
                time.sleep(1)
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
