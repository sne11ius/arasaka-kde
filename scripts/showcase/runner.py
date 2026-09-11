"""Owned, disposable VM boot controller. Recording is added by later tasks."""

import argparse
from contextlib import contextmanager, ExitStack
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import tempfile
import time
import traceback
from urllib.request import urlopen

from .machine import Guest, QMP

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_MARKER = "arasaka-showcase-v1\n"


def verified_download(url, path, algorithm, digest):
    """Stream into a sibling temporary file; accept only verified bytes."""
    destination = Path(path)
    if destination.exists():
        with destination.open("rb") as stream:
            if hashlib.file_digest(stream, algorithm).hexdigest() == digest:
                return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".download-",
                                         delete=False, mode="w+b") as stream:
            partial = Path(stream.name)
            with urlopen(url, timeout=60) as response:
                shutil.copyfileobj(response, stream, length=1024 * 1024)
            stream.flush()
            stream.seek(0)
            actual = hashlib.file_digest(stream, algorithm).hexdigest()
            if actual != digest:
                raise ValueError("download checksum mismatch")
            os.fsync(stream.fileno())
        os.replace(partial, destination)
    finally:
        if partial is not None:
            partial.unlink(missing_ok=True)
    return destination


@contextmanager
def WorkspaceLock(workspace):
    """Keep the lock inode stable, including across failed invocations."""
    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True, mode=0o700)
    if workspace.stat().st_uid != os.getuid():
        raise PermissionError("showcase workspace must be owned by the current user")
    workspace.chmod(0o700)
    fd = os.open(workspace / ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("workspace is already controlled by another invocation") from error
        yield workspace
    finally:
        os.close(fd)


@contextmanager
def managed_process(command, *, stop_timeout=10, **kwargs):
    """Reap owned processes and their process group on success, error, or signal."""
    process = subprocess.Popen(command, start_new_session=True, **kwargs)
    try:
        yield process
    finally:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=stop_timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        finally:
            # A leader can exit on TERM while a descendant ignores it.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def create_source_bundle(repository, destination):
    source = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repository, check=True,
                            capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "bundle", "create", str(destination), "HEAD"],
                   cwd=repository, check=True)
    return source


def cloud_config(config, public_key):
    guest = config["guest"]
    return {
        "hostname": guest["hostname"], "manage_etc_hosts": True,
        "users": [{"name": guest["user"], "uid": guest["uid"], "groups": ["sudo"],
                   "shell": "/bin/bash", "lock_passwd": False,
                   "plain_text_passwd": guest["password"],
                   "sudo": "ALL=(ALL) NOPASSWD:ALL", "ssh_authorized_keys": [public_key]}],
        "disable_root": True, "ssh_pwauth": False,
        "chpasswd": {"expire": False, "users": [{"name": guest["user"],
                      "password": guest["password"], "type": "text"}]},
        "package_update": False, "package_upgrade": False,
        "write_files": [{"path": "/etc/arasaka-showcase-guest", "permissions": "0644",
                         "content": FIXTURE_MARKER}],
    }


def create_seed(run, config, log):
    key = run / "id_ed25519"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
                   check=True, stdout=log, stderr=log)
    seed = run / "seed"
    seed.mkdir(mode=0o700)
    (seed / "user-data").write_text("#cloud-config\n" + json.dumps(
        cloud_config(config, key.with_suffix(".pub").read_text().strip()), indent=2) + "\n")
    (seed / "meta-data").write_text(json.dumps({
        "instance-id": run.name, "local-hostname": config["guest"]["hostname"]}) + "\n")
    iso = run / "seed.iso"
    subprocess.run(["genisoimage", "-quiet", "-output", str(iso), "-volid", "cidata",
                    "-joliet", "-rock", "user-data", "meta-data"],
                   cwd=seed, check=True, stdout=log, stderr=log)
    return key, iso


def wait_for(check, processes, timeout, description):
    deadline = time.monotonic() + timeout
    while True:
        for process in processes:
            if process.poll() is not None:
                raise RuntimeError(f"{description}: process exited with {process.returncode}")
        if check():
            return
        if time.monotonic() >= deadline:
            raise TimeoutError(f"timed out waiting for {description}")
        time.sleep(0.5)


def prepare(workspace, run, config):
    """Cold boot, verify the fixture over SSH, transfer HEAD, and retain evidence."""
    image = config["image"]
    print("Verifying the pinned Debian generic image...", flush=True)
    base = verified_download(image["url"], workspace / "cache" / "debian.qcow2",
                             image["algorithm"], image["digest"])
    with ExitStack() as stack:
        log = stack.enter_context((run / "transport.log").open("w"))
        key, iso = create_seed(run, config, log)
        overlay = run / "guest.qcow2"
        subprocess.run(["qemu-img", "create", "-f", "qcow2", "-F", "qcow2", "-b", str(base),
                        str(overlay), config["vm"]["disk_size"]],
                       check=True, stdout=log, stderr=log)
        width, height = config["display"]["width"], config["display"]["height"]
        authority = run / "Xauthority"
        authority.touch(mode=0o600)
        subprocess.run(["xauth", "-f", str(authority), "add", ":99", ".", secrets.token_hex(16)],
                       check=True, stdout=log, stderr=log)
        env = dict(os.environ, DISPLAY=":99", XAUTHORITY=str(authority),
                   GDK_BACKEND="x11", LIBGL_ALWAYS_SOFTWARE="1", GSETTINGS_BACKEND="memory")
        xvfb_log = stack.enter_context((run / "xvfb.log").open("w"))
        xvfb = stack.enter_context(managed_process(
            ["Xvfb", ":99", "-screen", "0", f"{width}x{height}x24", "-nolisten", "tcp",
             "-auth", str(authority)], stdout=xvfb_log, stderr=xvfb_log))
        wait_for(lambda: subprocess.run(["xdpyinfo"], env=env, stdout=log, stderr=log,
                                        timeout=5).returncode == 0, [xvfb], 30, "private Xvfb")
        # QEMU binds immediately in this private container network namespace. A
        # competing bind fails startup and is retained in qemu.log, never redirected.
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        qmp_path = run / "qmp.sock"
        command = [
            "qemu-system-x86_64", "-name", "arasaka-showcase", "-accel", "kvm", "-cpu", "host",
            "-smp", str(config["vm"]["vcpus"]), "-m", str(config["vm"]["memory_mib"]),
            "-drive", f"file={overlay},if=virtio,format=qcow2",
            "-drive", f"file={iso},media=cdrom,readonly=on", "-boot", "order=c",
            "-vga", "none", "-device", f"virtio-vga,xres={width},yres={height}",
            "-device", "qemu-xhci", "-device", "usb-tablet",
            "-display", "gtk,gl=off,show-cursor=on", "-full-screen",
            "-netdev", f"user,id=net0,hostfwd=tcp:127.0.0.1:{port}-:22",
            "-device", "virtio-net-pci,netdev=net0",
            "-qmp", f"unix:{qmp_path},server=on,wait=off",
            "-serial", f"file:{run / 'console.log'}", "-monitor", "none",
        ]
        (run / "qemu-command.json").write_text(json.dumps(command, indent=2) + "\n")
        qemu_log = stack.enter_context((run / "qemu.log").open("w"))
        qemu = stack.enter_context(managed_process(command, env=env, stdout=qemu_log, stderr=qemu_log))
        wait_for(qmp_path.exists, [qemu, xvfb], 30, "QMP socket")
        qmp = stack.enter_context(QMP(qmp_path))
        status = qmp.execute("query-status")
        if not status["running"]:
            raise RuntimeError(f"QEMU is not running: {status}")
        (run / "qmp-status.json").write_text(json.dumps(status, indent=2) + "\n")
        guest = Guest(port, key)

        def ssh_ready():
            try:
                guest.run("true", timeout=10)
                return True
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                return False

        print("Cold VM started; waiting for fixture SSH and cloud-init...", flush=True)
        wait_for(ssh_ready, [qemu, xvfb], config["vm"]["boot_timeout"], "guest SSH")
        result = guest.run("sudo cloud-init status --wait --long", timeout=config["vm"]["boot_timeout"])
        (run / "cloud-init-status.txt").write_text(result.stdout + result.stderr)
        marker = guest.run("cat /etc/arasaka-showcase-guest").stdout
        if marker != FIXTURE_MARKER:
            raise RuntimeError("SSH endpoint is not the showcase fixture")
        os_release = guest.run("cat /etc/os-release").stdout
        (run / "os-release").write_text(os_release)
        (run / "guest-identity.txt").write_text(guest.run(
            "id && hostname && systemd-detect-virt && sudo passwd -S demo").stdout)
        (run / "sshd-config.txt").write_text(guest.run("sudo sshd -T").stdout)
        # The generic image need not have git yet. Later provisioning consumes
        # this committed-source bundle to create /home/demo/arasaka-kde.
        with (run / "SOURCE.bundle").open("rb") as bundle:
            guest.run("cat > /home/demo/SOURCE.bundle", timeout=120, stdin=bundle)
        with (run / "SOURCE.bundle").open("rb") as bundle:
            expected = hashlib.file_digest(bundle, "sha256").hexdigest()
        actual = guest.run("sha256sum /home/demo/SOURCE.bundle").stdout.split()[0]
        if actual != expected:
            raise ValueError("guest source bundle checksum mismatch")
        (run / "boot-evidence.json").write_text(json.dumps({
            "phase": "prepare", "ready": "boot-and-ssh", "source": (run / "source-sha").read_text().strip(),
            "image_digest": image["digest"], "source_bundle_sha256": actual,
            "ssh_port": port, "fixture_marker": marker.strip(),
        }, indent=2) + "\n")
        print(os_release, end="", flush=True)
    print(f"Boot verified; VM and Xvfb stopped. Evidence: {run}", flush=True)


def run_container(workspace, config):
    if not os.access("/dev/kvm", os.R_OK | os.W_OK):
        raise RuntimeError("read/write /dev/kvm access is required")
    subprocess.run(["docker", "info"], check=True, stdout=subprocess.DEVNULL)
    run = Path(tempfile.mkdtemp(prefix="run-", dir=workspace))
    print(f"Showcase workspace: {run}", flush=True)
    (run / "environment.json").write_text(json.dumps(config, indent=2) + "\n")
    (run / "source-sha").write_text(create_source_bundle(REPO_ROOT, run / "SOURCE.bundle") + "\n")
    image = f"arasaka-showcase:{os.getuid()}-{os.getgid()}"
    with (run / "container-build.log").open("w") as log:
        print("Building the recorder container (container-build.log)...", flush=True)
        subprocess.run(["docker", "build", "--build-arg", f"SHOWCASE_UID={os.getuid()}",
                        "--build-arg", f"SHOWCASE_GID={os.getgid()}", "--tag", image,
                        str(REPO_ROOT / ".github/showcase")], check=True, stdout=log, stderr=log)
    name = f"arasaka-showcase-{os.getuid()}-{run.name}"
    command = ["docker", "run", "--rm", "--init", "--name", name,
               "--device", "/dev/kvm", "--group-add", str(os.stat("/dev/kvm").st_gid),
               "--mount", f"type=bind,src={REPO_ROOT},dst=/src,readonly",
               "--mount", f"type=bind,src={workspace},dst=/workspace",
               image, "prepare", "--worker-run", f"/workspace/{run.name}"]
    try:
        with (run / "container.log").open("w") as log:
            with managed_process(command, stdout=log, stderr=subprocess.STDOUT) as process:
                if process.wait() != 0:
                    raise RuntimeError(f"container boot failed; see {run / 'container.log'}")
    finally:
        # The Docker client is not the VM's parent. Reap the container explicitly
        # if the caller was interrupted; --init forwards signals/reaps orphans.
        subprocess.run(["docker", "stop", "--time", "15", name],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    print(f"Boot verified; container removed. Evidence: {run}", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "record", "all"))
    parser.add_argument("--workspace", type=Path, default=REPO_ROOT / "build/showcase")
    parser.add_argument("--worker-run", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.phase != "prepare":
        parser.error(f"{args.phase}: recording is not implemented yet; use prepare for boot verification")
    os.umask(0o077)

    def interrupted(signum, frame):
        raise KeyboardInterrupt(f"received signal {signum}")

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    workspace = args.worker_run if args.worker_run else args.workspace.resolve()
    try:
        with WorkspaceLock(workspace):
            if args.worker_run:
                config = json.loads((workspace / "environment.json").read_text())
                try:
                    prepare(workspace.parent, workspace, config)
                except BaseException:
                    (workspace / "error.log").write_text(traceback.format_exc())
                    raise
            else:
                config = json.loads((REPO_ROOT / "showcase/environment.json").read_text())
                run_container(workspace, config)
    except (Exception, KeyboardInterrupt) as error:
        parser.exit(1, f"showcase: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
