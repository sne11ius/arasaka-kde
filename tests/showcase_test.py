#!/usr/bin/env python3
"""Host regressions; no Docker, guest, or live desktop required."""

import contextlib
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.showcase.machine import Guest, QMP, QMPError
from scripts.showcase.runner import (
    WorkspaceLock, cloud_config, create_source_bundle, managed_process, verified_download,
)


@contextlib.contextmanager
def qmp_server(path, handler):
    """A real Unix peer, including QEMU's greeting/capabilities exchange."""
    listener = socket.socket(socket.AF_UNIX)
    listener.bind(str(path))
    listener.listen(1)
    errors = []
    stop = threading.Event()

    def serve():
        try:
            with listener.accept()[0] as connection:
                connection.settimeout(2)
                with connection.makefile("rwb", buffering=0) as stream:
                    def send(message):
                        stream.write(json.dumps(message).encode() + b"\r\n")

                    send({"QMP": {"version": {"qemu": {"major": 9, "minor": 2,
                          "micro": 0}, "package": ""}, "capabilities": []}})
                    request = json.loads(stream.readline())
                    if request["execute"] != "qmp_capabilities":
                        raise AssertionError(request)
                    send({"return": {}, "id": request["id"]})
                    handler(stream, send, stop)
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(3)
        listener.close()
        if thread.is_alive():
            raise AssertionError("QMP test peer did not stop")
        if errors:
            raise errors[0]


class DownloadTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "upstream"
        self.destination = self.root / "image.qcow2"

    def test_mismatched_download_cannot_replace_cached_image(self):
        self.source.write_bytes(b"corrupted network bytes")
        self.destination.write_bytes(b"previous cached image")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            verified_download(self.source.as_uri(), self.destination, "sha512", "0" * 128)
        self.assertEqual(self.destination.read_bytes(), b"previous cached image")
        self.assertEqual(sorted(p.name for p in self.root.iterdir()),
                         ["image.qcow2", "upstream"])

    def test_verified_bytes_replace_bad_cache_atomically(self):
        data = b"verified image\n" * 100000
        self.source.write_bytes(data)
        self.destination.write_bytes(b"bad cache")
        old_inode = self.destination.stat().st_ino
        result = verified_download(self.source.as_uri(), self.destination,
                                   "sha512", hashlib.sha512(data).hexdigest())
        self.assertEqual(result, self.destination)
        self.assertEqual(self.destination.read_bytes(), data)
        self.assertNotEqual(self.destination.stat().st_ino, old_inode)

    def test_verified_cache_needs_no_network(self):
        self.destination.write_bytes(b"good")
        verified_download(self.source.as_uri(), self.destination, "sha512",
                          hashlib.sha512(b"good").hexdigest())
        self.assertEqual(self.destination.read_bytes(), b"good")

    def test_network_failure_propagates_without_partial_file(self):
        with self.assertRaises(OSError):
            verified_download(self.source.as_uri(), self.destination, "sha512", "0" * 128)
        self.assertEqual(list(self.root.iterdir()), [])


class QMPTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "qmp.sock"

    def test_events_and_unrelated_ids_are_not_command_results(self):
        def peer(stream, send, stop):
            request = json.loads(stream.readline())
            self.assertEqual(request["execute"], "query-status")
            send({"event": "RESUME", "timestamp": {"seconds": 1, "microseconds": 0}})
            send({"return": {"status": "wrong"}, "id": "unrelated"})
            send({"return": {"status": "running"}, "id": request["id"]})
            second = json.loads(stream.readline())
            self.assertNotEqual(second["id"], request["id"])
            self.assertEqual(second["arguments"], {"device": "video"})
            send({"return": {}, "id": second["id"]})

        with qmp_server(self.path, peer), QMP(self.path) as qmp:
            self.assertEqual(qmp.execute("query-status"), {"status": "running"})
            self.assertEqual(qmp.events[0]["event"], "RESUME")
            self.assertEqual(qmp.execute("device_del", {"device": "video"}), {})

    def test_command_errors_propagate(self):
        def peer(stream, send, stop):
            request = json.loads(stream.readline())
            send({"error": {"class": "CommandNotFound", "desc": "unknown command"},
                  "id": request["id"]})

        with qmp_server(self.path, peer), QMP(self.path) as qmp:
            with self.assertRaisesRegex(QMPError, "CommandNotFound.*unknown command"):
                qmp.execute("not-a-command")

    def test_timeout_is_bounded_even_with_asynchronous_events(self):
        def peer(stream, send, stop):
            json.loads(stream.readline())
            while not stop.wait(0.005):
                try:
                    send({"event": "NOISE"})
                except BrokenPipeError:
                    return

        with qmp_server(self.path, peer), QMP(self.path, timeout=0.1) as qmp:
            start = time.monotonic()
            with self.assertRaises(TimeoutError):
                qmp.execute("query-status")
            self.assertLess(time.monotonic() - start, 1)

    def test_disconnect_is_an_error(self):
        def peer(stream, send, stop):
            json.loads(stream.readline())

        with qmp_server(self.path, peer), QMP(self.path) as qmp:
            with self.assertRaises(ConnectionError):
                qmp.execute("query-status")


class HostLifecycleTest(unittest.TestCase):
    # A synthetic repository must not invoke the operator's signing setup.
    @patch.dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1")
    def test_source_bundle_contains_head_without_working_tree_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()

            def git(*args):
                result = subprocess.run(["git", *args], cwd=source,
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                return result.stdout.strip()

            git("init", "--initial-branch=fixture")
            (source / "content").write_text("committed source\n")
            git("add", "content")
            git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                "commit", "-m", "fixture")
            (source / "content").write_text("private uncommitted edit\n")
            bundle = root / "SOURCE.bundle"
            self.assertEqual(create_source_bundle(source, bundle), git("rev-parse", "HEAD"))
            subprocess.run(["git", "clone", str(bundle), str(root / "clone")],
                           check=True, capture_output=True)
            self.assertEqual((root / "clone/content").read_text(), "committed source\n")

    def test_cloud_init_allows_graphical_password_but_key_only_ssh(self):
        config = {"guest": {"user": "demo", "uid": 1000,
                            "hostname": "arasaka-showcase", "password": "ArasakaDemo2026"}}
        data = cloud_config(config, "ssh-ed25519 AAAA fixture")
        user = data["users"][0]
        self.assertEqual((user["name"], user["uid"]), ("demo", 1000))
        self.assertFalse(user["lock_passwd"])
        # cloud-init 26 validates unlocking during user creation, before chpasswd.
        self.assertEqual(user["plain_text_passwd"], "ArasakaDemo2026")
        self.assertEqual(user["ssh_authorized_keys"], ["ssh-ed25519 AAAA fixture"])
        self.assertEqual(user["sudo"], "ALL=(ALL) NOPASSWD:ALL")
        self.assertFalse(data["ssh_pwauth"])
        self.assertFalse(data["chpasswd"]["expire"])
        self.assertEqual(data["chpasswd"]["users"],
                         [{"name": "demo", "password": "ArasakaDemo2026", "type": "text"}])
        marker = next(item for item in data["write_files"]
                      if item["path"] == "/etc/arasaka-showcase-guest")
        self.assertEqual(marker["content"], "arasaka-showcase-v1\n")

    def test_workspace_lock_excludes_another_process_and_releases_on_error(self):
        with tempfile.TemporaryDirectory() as directory:
            code = ("from scripts.showcase.runner import WorkspaceLock; "
                    "import sys; "
                    "\nwith WorkspaceLock(sys.argv[1]): pass")
            with self.assertRaisesRegex(RuntimeError, "test interruption"):
                with WorkspaceLock(Path(directory)):
                    result = subprocess.run([sys.executable, "-c", code, directory],
                                            cwd=REPO_ROOT, capture_output=True, text=True)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("workspace is already controlled", result.stderr)
                    raise RuntimeError("test interruption")
            result = subprocess.run([sys.executable, "-c", code, directory],
                                    cwd=REPO_ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_process_cleanup_on_exception_escalates_and_reaps(self):
        with tempfile.TemporaryFile() as log:
            with self.assertRaisesRegex(RuntimeError, "boot failed"):
                with managed_process([sys.executable, "-c",
                                      "import signal,time; "
                                      "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                                      "print('ready', flush=True); time.sleep(60)"],
                                     stdout=subprocess.PIPE, stderr=log,
                                     stop_timeout=0.1) as process:
                    self.assertEqual(process.stdout.readline(), b"ready\n")
                    raise RuntimeError("boot failed")
            self.assertIsNotNone(process.poll())
            process.stdout.close()

    def test_cleanup_kills_descendants_even_when_group_leader_exits_first(self):
        child = None
        process = None
        try:
            with managed_process([sys.executable, "-c",
                                  "import os,signal,time\n"
                                  "if os.fork() == 0:\n"
                                  " signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                                  " print(os.getpid(), flush=True)\n"
                                  "time.sleep(60)\n"],
                                 stdout=subprocess.PIPE, stop_timeout=0.1) as process:
                child = int(process.stdout.readline())
            # The child holds stdout open until it exits, even after its parent dies.
            readable, _, _ = select.select([process.stdout], [], [], 1)
            self.assertTrue(readable, "orphaned descendant survived controller cleanup")
            self.assertEqual(process.stdout.read(), b"")
        finally:
            if child is not None:
                try:
                    os.kill(child, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if process is not None:
                process.stdout.close()

    def test_unimplemented_phases_fail_without_creating_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "unused"
            for phase in ("record", "all"):
                result = subprocess.run([sys.executable, "-m", "scripts.showcase.runner",
                                         phase, "--workspace", str(workspace)],
                                        cwd=REPO_ROOT, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("not implemented", result.stderr)
                self.assertFalse(workspace.exists())


class GuestTest(unittest.TestCase):
    def test_ssh_is_confined_to_fixture_transport_and_returns_output(self):
        # Replace only the external SSH executable; exercise real process/argv handling.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ssh = root / "ssh"
            ssh.write_text("#!/usr/bin/env python3\nimport json, sys\n"
                           "print(json.dumps(sys.argv[1:]))\n")
            ssh.chmod(0o755)
            with patch.dict(os.environ, PATH=f"{root}:{os.environ['PATH']}"):
                result = Guest(2229, root / "id_ed25519").run("printf 'guest only'")
            args = json.loads(result.stdout)
            self.assertEqual(args[-2:], ["demo@127.0.0.1", "printf 'guest only'"])
            self.assertEqual(args[args.index("-p") + 1], "2229")
            self.assertEqual(args[args.index("-i") + 1], str(root / "id_ed25519"))
            self.assertEqual(args[args.index("-F") + 1], "/dev/null")
            for setting in ("BatchMode=yes", "IdentitiesOnly=yes", "IdentityAgent=none",
                            "StrictHostKeyChecking=accept-new", "GlobalKnownHostsFile=/dev/null"):
                self.assertIn(setting, args)
            self.assertIn(f"UserKnownHostsFile={root / 'known_hosts'}", args)

    def test_ssh_errors_and_timeouts_propagate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ssh = root / "ssh"
            ssh.write_text("#!/usr/bin/env python3\nimport sys, time\n"
                           "if sys.argv[-1] == 'slow': time.sleep(60)\n"
                           "sys.stderr.write('guest command failed\\n')\nsys.exit(17)\n")
            ssh.chmod(0o755)
            with patch.dict(os.environ, PATH=f"{root}:{os.environ['PATH']}"):
                guest = Guest(2229, root / "key")
                with self.assertRaises(subprocess.CalledProcessError) as error:
                    guest.run("false")
                self.assertEqual(error.exception.returncode, 17)
                self.assertIn("guest command failed", error.exception.stderr)
                with self.assertRaises(subprocess.TimeoutExpired):
                    guest.run("slow", timeout=0.1)


if __name__ == "__main__":
    unittest.main()
