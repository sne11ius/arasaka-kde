"""Guest-only deployment of the real managed KDE desktop and PLM packages.

The small shell entrypoints also work from the transport's bootstrap directory,
before Git is installed. Every administrative subprocess goes through sudo()
after the fixture guard. Native builds always run as demo.
"""

import argparse
import hashlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import shlex
import socket
import subprocess
import sys
import tarfile
import time
from urllib.request import urlopen

MARKER = Path("/etc/arasaka-showcase-guest")
HOME = Path("/home/demo")
REPO = HOME / "arasaka-kde"
STATE = HOME / ".local/state/arasaka-showcase"
PLUGIN = "online.knowmad.shaderwallpaper"
NATIVE = f"plasma/wallpapers/{PLUGIN}/contents/ui/shaderwallpaper/libshaderwallpaperplugin.so"
PLUGIN_PATH = HOME / ".local/lib/x86_64-linux-gnu/plugins"


def require_guest():
    try:
        valid = (not MARKER.is_symlink() and MARKER.read_bytes() == b"arasaka-showcase-v1\n")
    except OSError:
        valid = False
    if not valid:
        raise RuntimeError("showcase guest guard: exact fixture marker required")
    try:
        virt = subprocess.check_output(["systemd-detect-virt", "--vm"], text=True).strip()
    except subprocess.CalledProcessError:
        virt = "none"
    if virt not in ("qemu", "kvm"):
        raise RuntimeError("showcase guest guard: QEMU/KVM required")
    if socket.gethostname() != "arasaka-showcase":
        raise RuntimeError("showcase guest guard: fixture hostname required")
    user = pwd.getpwuid(os.getuid())
    if (os.geteuid(), user.pw_name, user.pw_dir) != (1000, "demo", str(HOME)):
        raise RuntimeError("showcase guest guard: run as demo UID1000, never host/root")
    if MARKER.stat().st_uid != 0 or MARKER.stat().st_mode & 0o022:
        raise RuntimeError("showcase guest guard: marker must be root-owned and not writable by demo")


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(*command, capture=False, input=None, env=None):
    if not capture:
        print("+ " + shlex.join(map(str, command)), flush=True)
    result = subprocess.run(list(map(str, command)), check=True, text=True, input=input,
                            stdout=subprocess.PIPE if capture else None, env=env)
    return result.stdout.strip() if capture else None


def sudo(*command, **kwargs):
    require_guest()
    return run("sudo", "-n", "env", "DEBIAN_FRONTEND=noninteractive", "LC_ALL=C.UTF-8",
               "NEEDRESTART_MODE=l", *command, **kwargs)


def system_file(path, text, mode="0644"):
    sudo("install", "-D", "-m", mode, "/dev/stdin", path, input=text)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".pending")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    temporary.replace(path)


def check_bundle_identity(bundle, state):
    checksum = sha256(bundle)
    if state.exists() and json.loads(state.read_text())["source_bundle_sha256"] != checksum:
        raise RuntimeError("source bundle changed: prepare a new disposable guest")
    return checksum


def build_dependencies(control):
    match = re.search(r"^Build-Depends:\s*(.+(?:\n[ \t].+)*)", control, re.MULTILINE)
    if not match:
        raise ValueError("PLM control has no Build-Depends")
    return " ".join(line.strip() for line in match[1].splitlines())


def frozen_apt(config):
    apt = config["apt"]
    if not re.fullmatch(r"https://snapshot\.debian\.org/archive/debian/\d{8}T\d{6}Z/", apt["url"]):
        raise ValueError("a frozen Debian APT snapshot is required")
    sources = ("Types: deb deb-src\nURIs: " + apt["url"] + "\nSuites: " + apt["suite"] +
               "\nComponents: " + " ".join(apt["components"]) +
               "\nSigned-By: /usr/share/keyrings/debian-archive-keyring.gpg\nCheck-Valid-Until: no\n")
    target = Path("/etc/apt/sources.list.d/arasaka-showcase.sources")
    if not target.exists():
        sudo("mkdir", "-p", "/etc/apt/arasaka-showcase-original")
        candidates = [Path("/etc/apt/sources.list"), *Path("/etc/apt/sources.list.d").glob("*.list"),
                      *Path("/etc/apt/sources.list.d").glob("*.sources")]
        for source in candidates:
            if source.exists():
                sudo("mv", source, "/etc/apt/arasaka-showcase-original/" + source.name)
        system_file(target, sources)
    if target.read_text() != sources:
        raise RuntimeError("fixture APT snapshot changed; use a new disposable guest")
    active = [p for pattern in ("*.sources", "*.list") for p in target.parent.glob(pattern)]
    if active != [target] or Path("/etc/apt/sources.list").exists():
        raise RuntimeError("unexpected non-frozen APT source")
    sudo("apt-get", "-o", "Acquire::Retries=3", "update")


def clone_source(bundle, checksum):
    heads = run("git", "bundle", "list-heads", bundle, "HEAD", capture=True).split()
    if len(heads) != 2 or heads[1] != "HEAD" or not re.fullmatch(r"[0-9a-f]{40}", heads[0]):
        raise ValueError("source bundle must advertise a unique HEAD")
    if not REPO.exists():
        run("git", "clone", bundle, REPO)
    source = run("git", "-C", REPO, "rev-parse", "HEAD", capture=True)
    if source != heads[0] or run("git", "-C", REPO, "status", "--porcelain", capture=True):
        raise RuntimeError("guest repository changed: prepare a new disposable guest")
    identity = {"source": source, "source_bundle_sha256": checksum}
    save(STATE / "source.json", identity)
    return identity


def install_dependencies():
    control = REPO / "packaging/plasmalogin/debian/control"
    dependencies = build_dependencies(control.read_text())
    # Let APT enforce the exact version relations in the authoritative control.
    sudo("apt-get", "--simulate", "--no-install-recommends", "satisfy", dependencies)
    sudo("apt-get", "--yes", "--no-install-recommends", "satisfy", dependencies)
    packages = """
        build-essential ninja-build gettext patch pkgconf dpkg-dev
        plasma-desktop plasma-workspace kwin-wayland sddm xserver-xorg
        konsole dolphin systemsettings plasma-nm plasma-pa powerdevil
        polkit-kde-agent-1 kscreen qdbus-qt6 libkf6config-bin kpackagetool6
        jq dbus-user-session qt6-wayland qt6-style-kvantum qt-style-kvantum-themes
        fonts-inter fonts-jetbrains-mono fontconfig librsvg2-bin
        zsh btop fastfetch bat git curl ca-certificates
        qt6-multimedia-dev qt6-svg-dev qt6-base-private-dev libqt6opengl6-dev
        kwin-dev libkdecorations3-dev libkf6configwidgets-dev libkf6colorscheme-dev
        libkf6guiaddons-dev libkf6iconthemes-dev libkf6widgetsaddons-dev
        libkf6crash-dev libkf6globalaccel-dev libkf6notifications-dev libkf6service-dev
        libkf6style-dev libepoxy-dev libdrm-dev libgbm-dev libinput-dev
        libwayland-dev libxkbcommon-dev libxcb-composite0-dev libxcb-randr0-dev
        libxcb-shm0-dev libxcb-res0-dev libxcb-sync-dev libxcb-damage0-dev
        libxcb-xfixes0-dev libxcb-render0-dev libxcb-shape0-dev libxcb-keysyms1-dev
        libxcb-icccm4-dev libxcb-cursor-dev libxcb-xinput-dev libxcb-util-dev
        qml6-module-qtmultimedia qml6-module-qt-labs-folderlistmodel
        qml6-module-qtquick-dialogs qml6-module-qtquick-localstorage
        qml6-module-qt5compat-graphicaleffects qml6-module-org-kde-kirigami
        qml6-module-org-kde-kcmutils qml6-module-org-kde-kitemmodels
        qml6-module-org-kde-plasma-workspace qml6-module-org-kde-breeze-components
        plasma-keyboard plasma-desktoptheme
    """.split()
    sudo("debconf-set-selections", input="sddm shared/default-x-display-manager select sddm\n")
    sudo("apt-get", "--simulate", "--no-install-recommends", "install", *packages)
    sudo("apt-get", "--yes", "--no-install-recommends", "install", *packages)
    run("dpkg-checkbuilddeps", control)
    (STATE / "packages.tsv").write_text(run("dpkg-query", "-W", "-f=${binary:Package}\t${Version}\n", capture=True) + "\n")


def install_fonts():
    # The exact pins and OFL used in .github/ci/Dockerfile, not moving font URLs.
    dockerfile = (REPO / ".github/ci/Dockerfile").read_text()
    pins = re.findall(r"ADD --checksum=sha256:([0-9a-f]{64}) --chmod=644\s*\\\n\s*(https://\S+)\s*\\\n\s*(/\S+)", dockerfile)
    if len(pins) != 2 or not any(url.endswith("/OFL.txt") for _, url, _ in pins):
        raise ValueError("Rajdhani font/OFL pins not found in CI Dockerfile")
    for checksum, url, destination in pins:
        with urlopen(url, timeout=120) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != checksum:
            raise ValueError("Rajdhani download checksum mismatch")
        local = STATE / url.rsplit("/", 1)[1]
        local.write_bytes(data)
        sudo("install", "-D", "-m", "0644", local, destination)
    sudo("fc-cache", "-f")
    if "Rajdhani-SemiBold.ttf" not in run("fc-match", "-f", "%{file}", "Rajdhani", capture=True):
        raise RuntimeError("pinned Rajdhani font was not selected")


def install_inventory(names, prefix):
    result = {}
    for name in names:
        path = Path(name)
        if not path.is_relative_to(prefix) or not path.resolve().is_relative_to(prefix):
            raise ValueError(f"native install outside fixture prefix: {path}")
        if path.is_symlink():
            result[name] = {"symlink": os.readlink(path)}
        elif path.is_file():
            result[name] = {"sha256": sha256(path)}
        elif path.is_dir():
            result[name] = {"directory": True}
        else:
            raise ValueError(f"native install missing: {path}")
    return result


def build_visuals(identity):
    for component in ("klassy", "better-blur-dx"):
        stamp = STATE / (component + ".json")
        if stamp.exists():
            previous = json.loads(stamp.read_text())
            if (previous["source"] != identity["source"] or
                    install_inventory(previous["installed"], HOME / ".local") != previous["installed"]):
                raise RuntimeError(f"{component} installed identity changed; use a new guest")
            continue
        archive = Path(run(REPO / "bin/fetch-components", component, capture=True))
        work = REPO / "build/showcase-native" / component
        work.mkdir(parents=True, exist_ok=True)
        source = work / "source"
        source.mkdir(exist_ok=True)
        with tarfile.open(archive) as tar:
            tar.extractall(source, filter="data")
        roots = list(source.iterdir())
        if len(roots) != 1 or not (roots[0] / "CMakeLists.txt").is_file():
            raise ValueError(f"invalid {component} source archive")
        build = work / "build"
        run("cmake", "-S", roots[0], "-B", build, "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release",
            f"-DCMAKE_INSTALL_PREFIX={HOME / '.local'}", "-DBUILD_TESTING=OFF",
            "-DKDE_INSTALL_LIBDIR=lib/x86_64-linux-gnu", f"-DKDE_INSTALL_PLUGINDIR={PLUGIN_PATH}",
            *(["-DBUILD_QT5=OFF", "-DBUILD_QT6=ON"] if component == "klassy" else []))
        run("cmake", "--build", build, "--parallel", "4")
        run("cmake", "--install", build)
        installed = (build / "install_manifest.txt").read_text().splitlines()
        if not installed or any(not Path(p).is_relative_to(HOME / ".local") for p in installed):
            raise ValueError(f"unexpected {component} install prefix")
        save(stamp, {"source": identity["source"], "archive_sha256": sha256(archive),
                     "source_notices": str(roots[0]),
                     "installed": install_inventory(installed, HOME / ".local")})


def fixture_environment():
    target = HOME / ".config/environment.d/arasaka.conf"
    target.parent.mkdir(parents=True, exist_ok=True)
    values = f"QT_PLUGIN_PATH={PLUGIN_PATH}\nKWIN_EFFECTS_FORCE_ANIMATIONS=1\n"
    target.write_text(values)
    # The SSH user manager predates package installation on the first boot;
    # startplasma must also import these before KWin/plugin discovery starts.
    startup = HOME / ".config/plasma-workspace/env/arasaka-showcase.sh"
    startup.parent.mkdir(parents=True, exist_ok=True)
    startup.write_text("#!/bin/sh\n" + "".join("export " + line + "\n" for line in values.splitlines()))


def session_environment():
    sessions = json.loads(run("loginctl", "list-sessions", "--json=short", capture=True))
    session = None
    for item in sessions:
        properties = run("loginctl", "show-session", str(item["session"]),
                         "-p", "Name", "-p", "Type", "-p", "Active", capture=True)
        values = dict(line.split("=", 1) for line in properties.splitlines())
        if values == {"Name": "demo", "Type": "wayland", "Active": "yes"}:
            session = str(item["session"])
            break
    if session is None:
        raise RuntimeError("no active demo Plasma Wayland session")
    pids = run("pgrep", "-u", "1000", "-x", "plasmashell", capture=True).split()
    if len(pids) != 1:
        raise RuntimeError("expected exactly one demo plasmashell")
    process = Path("/proc") / pids[0]
    entries = (process / "environ").read_bytes().split(b"\0")
    environment = dict(entry.decode().split("=", 1) for entry in entries if b"=" in entry)
    if environment.get("XDG_RUNTIME_DIR") != "/run/user/1000":
        raise RuntimeError("Plasma runtime is not owned by demo")
    wayland = environment.get("WAYLAND_DISPLAY", "")
    if not wayland or not (Path("/run/user/1000") / wayland).is_socket():
        raise RuntimeError("Plasma's real Wayland socket is unavailable")
    env = dict(os.environ, HOME=str(HOME), USER="demo", LOGNAME="demo", LC_ALL="C.UTF-8",
               XDG_SESSION_TYPE="wayland", XDG_SESSION_ID=session, QT_PLUGIN_PATH=str(PLUGIN_PATH))
    for key in ("DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS",
                "XDG_CONFIG_DIRS", "XDG_DATA_DIRS", "XDG_CURRENT_DESKTOP", "XDG_MENU_PREFIX"):
        if key in environment:
            env[key] = environment[key]
    # On the first boot dbus-user-session was installed after SSH created the
    # user manager. Plasma can legitimately own a private Unix session bus until
    # the next login. Follow the live process, and prove that bus owns this PID.
    if not env.get("DBUS_SESSION_BUS_ADDRESS", "").startswith("unix:"):
        raise RuntimeError("Plasma has no local Unix session bus")
    bus_pid = run("qdbus6", "org.freedesktop.DBus", "/org/freedesktop/DBus",
                  "org.freedesktop.DBus.GetConnectionUnixProcessID", "org.kde.plasmashell",
                  capture=True, env=env)
    if bus_pid != pids[0]:
        raise RuntimeError("session bus does not own the live demo plasmashell")
    run("qdbus6", "org.kde.plasmashell", "/PlasmaShell", "org.freedesktop.DBus.Peer.Ping", capture=True, env=env)
    run("qdbus6", "org.kde.KWin", "/KWin", "org.freedesktop.DBus.Peer.Ping", capture=True, env=env)
    return env


def bootstrap_session():
    fixture_environment()
    if not (STATE / "plm-selected.json").exists():
        system_file("/etc/sddm.conf.d/90-arasaka-showcase-bootstrap.conf",
                    "[Autologin]\nUser=demo\nSession=plasma.desktop\nRelogin=false\n")
        sudo("systemctl", "set-default", "graphical.target")
        sudo("systemctl", "enable", "sddm.service")
        sudo("systemctl", "restart", "sddm.service")
    deadline = time.monotonic() + 180
    while True:
        try:
            return session_environment()
        except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Plasma bootstrap timed out: {error}") from error
            time.sleep(2)


def terminal_profile(env):
    profile = HOME / ".local/share/konsole/Showcase.profile"
    profile.parent.mkdir(parents=True, exist_ok=True)
    profile.write_text("[General]\nName=Arasaka Showcase\nParent=FALLBACK/\nCommand=/bin/zsh\n"
                       "Directory=/home/demo/arasaka-kde\n[Appearance]\nColorScheme=Arasaka\n"
                       "Font=JetBrains Mono,11,-1,5,400,0,0,0,0,0\n[Scrolling]\nHistoryMode=1\nHistorySize=10000\n")
    (HOME / ".zshrc").write_text("# Disposable showcase profile; all terminal output is real.\n"
                                "autoload -Uz colors vcs_info; colors\nsetopt PROMPT_SUBST\n"
                                "zstyle ':vcs_info:git:*' formats ' [%b]'\nprecmd() { vcs_info; }\n"
                                "PROMPT='%F{red}%n@%m%f %F{cyan}%~%f${vcs_info_msg_0_} %# '\n"
                                "alias ll='ls -lah --color=auto'\nalias bat='batcat'\n")
    run("kwriteconfig6", "--file", "konsolerc", "--group", "Desktop Entry", "--key", "DefaultProfile",
        "Showcase.profile", env=env)


def project_plm():
    loader = importlib.machinery.SourceFileLoader("showcase_project_plm", str(REPO / "bin/apply-plm"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def plm_state():
    plm = project_plm()
    config = Path("/etc/plasmalogin.conf")
    groups = plm.config_groups("demo")
    text = config.read_text()
    _, present = plm.kconfig(text, groups)
    expected = {(group, key) for group, values in groups.items() for key in values}
    if not expected <= present:
        raise RuntimeError("PLM managed configuration is incomplete")
    plm.check_config_sources(groups)
    plm.check_session()
    for name, checksum in plm.PAM_HASHES.items():
        if sha256(Path("/etc/pam.d") / name) != checksum:
            raise RuntimeError(f"installed real PLM PAM differs: {name}")
    for package, version in plm.PACKAGES.items():
        if run("dpkg-query", "-W", "-f=${Version}", package, capture=True) != version:
            raise RuntimeError(f"PLM package version differs: {package}")
        if sudo("dpkg", "--verify", package, capture=True):
            raise RuntimeError(f"PLM package payload changed: {package}")
    native = Path("/usr/share") / NATIVE
    if "not found" in run("ldd", native, capture=True):
        raise RuntimeError("unresolved system shader plugin")
    selected = (Path("/etc/X11/default-display-manager").read_text() == "/usr/bin/plasmalogin\n"
                and Path("/etc/systemd/system/display-manager.service").resolve() ==
                Path("/usr/lib/systemd/system/plasmalogin.service"))
    bootstrap_removed = not Path("/etc/sddm.conf.d/90-arasaka-showcase-bootstrap.conf").exists()
    return {"selected": selected, "autologin_disabled": bootstrap_removed,
            "pam_verified": True, "assets_verified": True}


def mapped_plugin(pid, path):
    return str(path) in sudo("cat", f"/proc/{pid}/maps", capture=True)


def managed_settings(env):
    # Semantic configuration plus source/artwork hashes: no transient PIDs,
    # timestamps, caches or backup-directory names enter convergence checks.
    files = ("kdeglobals", "kwinrc", "kwinrulesrc", "klassy/klassyrc", "kscreenlockerrc",
             "ksplashrc", "Kvantum/kvantum.kvconfig", "environment.d/arasaka.conf",
             "plasma-workspace/env/arasaka-showcase.sh")
    values = {name: (HOME / ".config" / name).read_text() for name in files}
    values["plm"] = Path("/etc/plasmalogin.conf").read_text()
    values["profile"] = (HOME / ".local/share/konsole/Showcase.profile").read_text()
    values["prompt"] = (HOME / ".zshrc").read_text()
    for path in (HOME / ".local/share/wallpapers/Arasaka").rglob("*"):
        if path.is_file():
            values[str(path.relative_to(HOME))] = sha256(path)
    # apply-plm performs real live wallpaper readback against the shared values.
    values["desktops"] = project_plm().desktop_state(HOME)
    return values


def status(env):
    identity = json.loads((STATE / "source.json").read_text())
    if run("git", "-C", REPO, "rev-parse", "HEAD", capture=True) != identity["source"]:
        raise RuntimeError("guest source revision changed")
    policy = json.loads(run("qdbus6", "org.kde.KWin", "/ArasakaWindowPolicy",
                            "org.arasaka.WindowPolicy1.report", capture=True, env=env))
    runtime = json.loads((HOME / ".local/share/kwin/scripts/arasaka-polonium/runtime.json").read_text())
    if any(policy.get(key) != runtime[key] for key in ("version", "nativeRevision")):
        raise RuntimeError("live native window policy does not match installed revision")
    effects = ("better_blur_dx", "kwin6_effect_tv_glitch", "arasaka_tv_glitch_minimize")
    for effect in effects:
        if run("qdbus6", "org.kde.KWin", "/Effects", "org.kde.kwin.Effects.isEffectLoaded", effect,
               capture=True, env=env) != "true":
            raise RuntimeError(f"managed effect not loaded: {effect}")
    pid = run("pgrep", "-u", "1000", "-x", "plasmashell", capture=True)
    loaded = mapped_plugin(pid, HOME / ".local/share" / NATIVE)
    values = managed_settings(env)
    plm = plm_state()
    result = dict(identity, ready=loaded and all(plm.values()), session_type="wayland", plasma_ready=True,
                  wallpaper={"plugin": PLUGIN, "native_loaded": loaded, "desktops": values["desktops"]},
                  window_policy=dict(policy, loaded=True), effects=list(effects), plm=plm,
                  boot_id=Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
                  managed_fingerprint=hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest())
    save(STATE / "managed-settings.json", values)
    return result


def prepare_session(env):
    os.environ.update(env)
    run(REPO / "bin/apply-live", "--desktop-only", env=env)
    fixture_environment()  # apply-live's legacy environment file is user-specific.
    terminal_profile(env)
    if not (STATE / "plm-selected.json").exists():
        run(REPO / "bin/build-plm", env=env)
        run(REPO / "bin/apply-plm", "--skip-build", env=env)
        save(STATE / "plm-selected.json", json.loads((STATE / "source.json").read_text()))
    sudo(REPO / "bin/apply-lockscreen", "--login")
    sudo("rm", "-f", "/etc/sddm.conf.d/90-arasaka-showcase-bootstrap.conf")
    return status(env)


def greeter_status():
    configured = plm_state()
    service = "plasmalogin.service"
    active = run("systemctl", "is-active", service, capture=True) == "active"
    account = pwd.getpwnam("plasmalogin")
    processes = json.loads(sudo("python3", "-c", """
import json, pathlib
result = {}
for p in pathlib.Path('/proc').glob('[0-9]*'):
    try:
        if p.stat().st_uid == int(__import__('sys').argv[1]):
            result[p.name] = str((p / 'exe').readlink())
    except (FileNotFoundError, PermissionError):
        pass
print(json.dumps(result))
""", str(account.pw_uid), capture=True))
    greeter = "/usr/lib/x86_64-linux-gnu/libexec/plasma-login-greeter"
    wallpaper = "/usr/bin/plasma-login-wallpaper"
    wallpaper_pids = [pid for pid, path in processes.items() if path == wallpaper]
    native_loaded = len(wallpaper_pids) == 1 and mapped_plugin(wallpaper_pids[0], Path("/usr/share") / NATIVE)
    demo_graphical = False
    for item in json.loads(run("loginctl", "list-sessions", "--json=short", capture=True)):
        if item.get("user") == "demo":
            kind = run("loginctl", "show-session", str(item["session"]), "-p", "Type", "--value", capture=True)
            demo_graphical |= kind in ("wayland", "x11")
    return dict(configured, service=service, active=active,
                boot_id=Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
                greeter_executable=greeter if greeter in processes.values() else None,
                wallpaper_executable=wallpaper if wallpaper_pids else None,
                native_loaded=native_loaded, demo_graphical_session=demo_graphical,
                processes=processes,
                ready=all(configured.values()) and active and greeter in processes.values()
                      and native_loaded and not demo_graphical)


def provision(bundle):
    bundle = Path(bundle)
    if bundle != HOME / "SOURCE.bundle" or bundle.is_symlink():
        raise ValueError("use the transported /home/demo/SOURCE.bundle")
    checksum = check_bundle_identity(bundle, STATE / "source.json")
    config_path = Path(__file__).with_name("environment.json")
    if not config_path.exists():
        config_path = REPO / "showcase/environment.json"
    config = json.loads(config_path.read_text())
    frozen_apt(config)
    sudo("apt-get", "--yes", "--no-install-recommends", "install", "git", "ca-certificates", "curl")
    identity = clone_source(bundle, checksum)
    if json.loads((REPO / "showcase/environment.json").read_text()) != config:
        raise RuntimeError("bootstrap environment and bundled source disagree")
    for name in ("guest_setup.py", "guest-prepare.sh", "guest-session.sh"):
        if sha256(Path(__file__).with_name(name)) != sha256(REPO / "scripts/showcase" / name):
            raise RuntimeError(f"bootstrap script differs from bundled source: {name}")
    install_dependencies()
    install_fonts()
    build_visuals(identity)
    result = prepare_session(bootstrap_session())
    save(STATE / "readiness.json", result)
    print(json.dumps(result, sort_keys=True))


def main():
    # Guard even malformed invocations before filesystem or administrative work.
    require_guest()
    os.umask(0o022)
    os.environ.update(HOME=str(HOME), LC_ALL="C.UTF-8", QT_PLUGIN_PATH=str(PLUGIN_PATH))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("provision", "session", "greeter-status"))
    parser.add_argument("argument", nargs="?")
    args = parser.parse_args()
    if args.mode == "provision":
        if args.argument is None:
            parser.error("provision requires SOURCE_BUNDLE")
        provision(args.argument)
    elif args.mode == "greeter-status":
        print(json.dumps(greeter_status(), sort_keys=True))
    else:
        if args.argument not in ("prepare", "status", "reset"):
            parser.error("session requires prepare|status|reset")
        env = session_environment()
        os.environ.update(env)
        if args.argument == "prepare":
            result = prepare_session(env)
        elif args.argument == "reset":
            # Only fixture-owned demo tour windows; never reset KDE policy/auth.
            subprocess.run(["pkill", "-u", "1000", "-x", "konsole"], check=False)
            result = status(env)
        else:
            result = status(env)
        print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        sys.exit(f"showcase guest: {error}")
