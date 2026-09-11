#!/usr/bin/env python3
"""Host regressions; no Docker, guest, or live desktop required."""

import contextlib
import hashlib
import io
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
from scripts.showcase import runner
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

    @patch.dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1")
    def test_source_revision_matches_bundle_when_head_advances_during_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            real_run = subprocess.run

            def git(*args):
                return real_run(["git", *args], cwd=source, check=True,
                                capture_output=True, text=True).stdout.strip()

            def commit(content):
                (source / "content").write_text(content)
                git("add", "content")
                git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                    "commit", "-m", content)
                return git("rev-parse", "HEAD")

            git("init", "--initial-branch=fixture")
            initial = commit("initial source\n")
            bundled = None

            def advance_around_bundle(command, *args, **kwargs):
                nonlocal bundled
                if command[:3] == ["git", "bundle", "create"]:
                    # Execute real commits and the real bundle command at a
                    # deterministic boundary; neither Git result is fabricated.
                    bundled = commit("source included in bundle\n")
                    result = real_run(command, *args, **kwargs)
                    commit("source after bundle\n")
                    return result
                return real_run(command, *args, **kwargs)

            bundle = root / "SOURCE.bundle"
            with patch("scripts.showcase.runner.subprocess.run", side_effect=advance_around_bundle):
                recorded = create_source_bundle(source, bundle)
            self.assertIsNotNone(bundled)
            self.assertNotEqual(initial, bundled)
            self.assertNotEqual(git("rev-parse", "HEAD"), bundled)
            real_run(["git", "clone", str(bundle), str(root / "clone")],
                     check=True, capture_output=True)
            clone_head = real_run(["git", "rev-parse", "HEAD"], cwd=root / "clone",
                                  check=True, capture_output=True, text=True).stdout.strip()
            self.assertEqual(clone_head, bundled)
            self.assertEqual((root / "clone/content").read_text(), "source included in bundle\n")
            self.assertEqual(recorded, clone_head, "recorded revision must describe the transferred bundle")

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


class DockerCleanupTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        docker = self.root / "docker"
        # Only the external Docker CLI is replaced; the controller still creates
        # its real source bundle, runs/reaps processes, and writes diagnostics.
        docker.write_text(
            "#!/usr/bin/env python3\nimport os,sys,time\n"
            "if sys.argv[1] == 'stop' and sys.argv[2] in ('--time', '--timeout') and sys.argv[3] == '15':\n"
            " print(os.environ['STOP_STDOUT'], flush=True)\n"
            " print(os.environ['STOP_STDERR'].replace('{name}', sys.argv[4]), file=sys.stderr, flush=True)\n"
            " time.sleep(float(os.environ.get('STOP_DELAY', '0')))\n"
            " sys.exit(int(os.environ['STOP_STATUS']))\n"
            "if sys.argv[1] not in ('info', 'build', 'run'): sys.exit(99)\n")
        docker.chmod(0o755)
        self.enterContext(patch.dict(os.environ, PATH=f"{self.root}:{os.environ['PATH']}",
                                     GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1",
                                     STOP_STDOUT="stop stdout", STOP_STDERR="stop stderr",
                                     STOP_STATUS="0", STOP_DELAY="0"))
        (self.source / "content").write_text("source\n")
        for args in (["init", "--initial-branch=fixture"], ["add", "."],
                     ["-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                      "commit", "-m", "fixture"]):
            subprocess.run(["git", *args], cwd=self.source, check=True, capture_output=True)
        self.enterContext(patch.object(runner, "REPO_ROOT", self.source))
        # KVM access/group lookup is a host prerequisite, independent of cleanup.
        self.enterContext(patch("scripts.showcase.runner.os.access", return_value=True))
        real_stat = os.stat
        self.enterContext(patch("scripts.showcase.runner.os.stat", side_effect=lambda path, *a, **kw:
                                real_stat(self.root if str(path) == "/dev/kvm" else path, *a, **kw)))
        self.output = self.enterContext(contextlib.redirect_stdout(io.StringIO()))

    def cleanup_log(self):
        return next(self.root.glob("run-*/container-cleanup.log")).read_text()

    def test_successful_stop_retains_both_output_streams_and_exit_status(self):
        runner.run_container(self.root, {})
        log = self.cleanup_log()
        for expected in ("stop stdout", "stop stderr", "exit status: 0", "cleanup outcome: stopped"):
            self.assertIn(expected, log)

    def test_already_removed_container_is_expected_but_diagnostic_is_retained(self):
        os.environ.update(STOP_STATUS="1", STOP_STDOUT="",
                          STOP_STDERR="Error response from daemon: No such container: {name}")
        runner.run_container(self.root, {})
        log = self.cleanup_log()
        self.assertIn("No such container: arasaka-showcase-", log)
        self.assertIn("exit status: 1", log)
        self.assertIn("cleanup outcome: already-removed", log)

    def test_already_removed_container_with_stdout_notice_is_still_expected(self):
        # Docker 28 emitted this real stdout notice alongside its missing-container error.
        notice = "Flag --time has been deprecated, use --timeout instead"
        os.environ.update(STOP_STATUS="1", STOP_STDOUT=notice,
                          STOP_STDERR="Error response from daemon: No such container: {name}")
        runner.run_container(self.root, {})
        self.assertIn(notice, self.cleanup_log())
        self.assertIn("cleanup outcome: already-removed", self.cleanup_log())

    def test_unexpected_cleanup_error_prevents_success_and_retains_diagnostics(self):
        os.environ.update(STOP_STATUS="1", STOP_STDERR="Cannot connect to the Docker daemon")
        with self.assertRaisesRegex(RuntimeError, "container cleanup failed"):
            runner.run_container(self.root, {})
        log = self.cleanup_log()
        self.assertIn("Cannot connect to the Docker daemon", log)
        self.assertIn("stop stdout", log)
        self.assertIn("exit status: 1", log)
        self.assertIn("cleanup outcome: failed", log)
        self.assertNotIn("Boot verified", self.output.getvalue())

    def test_missing_container_diagnostic_must_match_the_owned_container(self):
        os.environ.update(STOP_STATUS="1", STOP_STDOUT="",
                          STOP_STDERR="Error response from daemon: No such container: unrelated")
        with self.assertRaisesRegex(RuntimeError, "container cleanup failed"):
            runner.run_container(self.root, {})
        self.assertIn("cleanup outcome: failed", self.cleanup_log())

    def test_cleanup_timeout_retains_partial_output_and_propagates(self):
        os.environ["STOP_DELAY"] = "60"
        real_run = subprocess.run

        def short_stop_timeout(command, *args, **kwargs):
            if command[:2] == ["docker", "stop"]:
                kwargs["timeout"] = 0.1
            return real_run(command, *args, **kwargs)

        with patch("scripts.showcase.runner.subprocess.run", side_effect=short_stop_timeout):
            with self.assertRaises(subprocess.TimeoutExpired):
                runner.run_container(self.root, {})
        log = self.cleanup_log()
        self.assertIn("timed out", log)
        self.assertIn("stop stdout", log)
        self.assertIn("stop stderr", log)


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


class GuestPreparationTest(unittest.TestCase):
    def test_fixture_startup_exports_real_native_plugin_path_and_software_animations(self):
        from scripts.showcase import guest_setup
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(guest_setup, "HOME", root), patch.object(guest_setup, "PLUGIN_PATH", root / "plugins"):
                guest_setup.fixture_environment()
                startup = root / ".config/plasma-workspace/env/arasaka-showcase.sh"
                result = subprocess.run(["bash", "-c", 'source "$1"; env', "test", str(startup)],
                                        capture_output=True, text=True, check=True)
                environment = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
                self.assertEqual(environment.get("QT_PLUGIN_PATH"), str(root / "plugins"))
                self.assertEqual(environment.get("KWIN_EFFECTS_FORCE_ANIMATIONS"), "1")

    def test_native_install_inventory_preserves_cmake_directory_links(self):
        from scripts.showcase import guest_setup
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            icons = root / "16"
            icons.mkdir()
            icon = icons / "folder.svg"
            icon.write_bytes(b"icon")
            link = root / "16@3x"
            link.symlink_to("16", target_is_directory=True)
            inventory = guest_setup.install_inventory([str(icons), str(icon), str(link)], root)
            self.assertEqual(inventory[str(link)], {"symlink": "16"})
            self.assertEqual(inventory[str(icons)], {"directory": True})
            icon.write_bytes(b"changed icon")
            self.assertNotEqual(guest_setup.install_inventory(list(inventory), root), inventory)
            link.unlink()
            link.symlink_to("/etc")
            with self.assertRaisesRegex(ValueError, "prefix"):
                guest_setup.install_inventory([str(link)], root)

    @patch.dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1")
    def test_guest_clone_uses_advertised_head_and_keeps_history_on_repeat(self):
        from scripts.showcase import guest_setup
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            for args in (("init", "--initial-branch=fixture"),):
                subprocess.run(["git", *args], cwd=source, check=True, capture_output=True)
            for index in (1, 2):
                (source / "content").write_text(str(index))
                subprocess.run(["git", "add", "content"], cwd=source, check=True, capture_output=True)
                subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                                "commit", "-m", f"revision {index}"], cwd=source, check=True, capture_output=True)
            bundle = root / "SOURCE.bundle"
            expected = create_source_bundle(source, bundle)
            with patch.object(guest_setup, "REPO", root / "clone"), \
                    patch.object(guest_setup, "STATE", root / "state"):
                result = guest_setup.clone_source(bundle, hashlib.sha256(bundle.read_bytes()).hexdigest())
                self.assertEqual(result["source"], expected)
                self.assertEqual(guest_setup.clone_source(bundle, result["source_bundle_sha256"]), result)
                commits = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=root / "clone",
                                         check=True, capture_output=True, text=True).stdout.strip()
                self.assertEqual(commits, "2")
                (root / "clone/content").write_text("private change")
                with self.assertRaisesRegex(RuntimeError, "repository changed"):
                    guest_setup.clone_source(bundle, result["source_bundle_sha256"])

    def test_apply_live_rejects_unknown_scope_before_deploying(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "bin").mkdir()
            (root / "bin/apply-live").write_bytes((REPO_ROOT / "bin/apply-live").read_bytes())
            launcher = root / "bin/apply-launcher"
            launcher.write_text("#!/bin/sh\ntouch \"$HOME/changed\"\nexit 99\n")
            launcher.chmod(0o755)
            result = subprocess.run(["bash", str(root / "bin/apply-live"), "--unknown"],
                                    env=dict(os.environ, HOME=str(root)), capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((root / "changed").exists(), "invalid scope began deploying launcher")

    def test_guest_entrypoints_refuse_operator_before_any_administrative_command(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sudo = root / "sudo"
            sudo.write_text("#!/bin/sh\ntouch \"$ADMIN_CALLED\"\nexit 99\n")
            sudo.chmod(0o755)
            with patch.dict(os.environ, PATH=f"{root}:{os.environ['PATH']}",
                            ADMIN_CALLED=str(root / "admin-called")):
                for name, argument in (("guest-prepare.sh", "/home/demo/SOURCE.bundle"),
                                       ("guest-session.sh", "prepare"),
                                       ("guest-session.sh", "reset")):
                    result = subprocess.run(["bash", str(REPO_ROOT / "scripts/showcase" / name), argument],
                                            capture_output=True, text=True)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("showcase guest guard", result.stderr)
                    self.assertFalse((root / "admin-called").exists())

    def test_marker_alone_cannot_authorize_non_qemu_or_wrong_hostname(self):
        from scripts.showcase import guest_setup
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "marker"
            marker.write_bytes(b"arasaka-showcase-v1\n")
            with patch.object(guest_setup, "MARKER", marker), \
                    patch("scripts.showcase.guest_setup.socket.gethostname", return_value="arasaka-showcase"), \
                    patch("scripts.showcase.guest_setup.subprocess.check_output", return_value="none\n"):
                with self.assertRaisesRegex(RuntimeError, "showcase guest guard.*QEMU/KVM"):
                    guest_setup.require_guest()
            with patch.object(guest_setup, "MARKER", marker), \
                    patch("scripts.showcase.guest_setup.socket.gethostname", return_value="operator-desktop"), \
                    patch("scripts.showcase.guest_setup.subprocess.check_output", return_value="kvm\n"):
                with self.assertRaisesRegex(RuntimeError, "showcase guest guard.*hostname"):
                    guest_setup.require_guest()

    def test_source_identity_rejects_changed_bundle_before_reprovisioning(self):
        from scripts.showcase import guest_setup
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / "SOURCE.bundle"
            state = root / "source.json"
            bundle.write_bytes(b"old committed bundle")
            state.write_text(json.dumps({"source_bundle_sha256": hashlib.sha256(bundle.read_bytes()).hexdigest()}))
            guest_setup.check_bundle_identity(bundle, state)
            bundle.write_bytes(b"new committed bundle")
            with self.assertRaisesRegex(RuntimeError, "new disposable guest"):
                guest_setup.check_bundle_identity(bundle, state)

    def test_plm_dependencies_preserve_version_constraints_and_continuations(self):
        from scripts.showcase import guest_setup
        text = "Source: plm\nBuild-Depends: cmake (>= 3.22),\n qt6-base-dev (>= 6.10),\n libplasma-dev (>= 6.7)\nStandards-Version: 4.7.2\n\nPackage: plm\nDepends: other\n"
        self.assertEqual(guest_setup.build_dependencies(text),
                         "cmake (>= 3.22), qt6-base-dev (>= 6.10), libplasma-dev (>= 6.7)")
        with self.assertRaisesRegex(ValueError, "Build-Depends"):
            guest_setup.build_dependencies("Source: missing\n")


class PreparedGuestTest(unittest.TestCase):
    def readiness(self):
        return {"ready": True, "source": "a" * 40, "source_bundle_sha256": "b" * 64,
                "session_type": "wayland", "plasma_ready": True,
                "wallpaper": {"plugin": "online.knowmad.shaderwallpaper", "native_loaded": True},
                "window_policy": {"version": "policy", "nativeRevision": "native", "loaded": True},
                "managed_fingerprint": "c" * 64,
                "plm": {"selected": True, "autologin_disabled": True, "pam_verified": True,
                        "assets_verified": True}}

    def test_repeat_preparation_rejects_drift_and_false_readiness(self):
        from scripts.showcase import prepared
        first = self.readiness()
        prepared.verify_convergence(first, dict(first), "a" * 40, "b" * 64)
        for field, value in (("managed_fingerprint", "d" * 64), ("source", "e" * 40),
                             ("ready", False), ("session_type", "x11")):
            with self.subTest(field=field), self.assertRaises(ValueError):
                prepared.verify_convergence(first, dict(first, **{field: value}), "a" * 40, "b" * 64)
        broken = self.readiness()
        broken["window_policy"]["loaded"] = False
        with self.assertRaises(ValueError):
            prepared.verify_convergence(broken, broken, "a" * 40, "b" * 64)

    def test_default_greeter_or_same_boot_cannot_be_sealed(self):
        from scripts.showcase import prepared
        greeter = {"ready": True, "boot_id": "new-boot", "service": "plasmalogin.service",
                   "active": True, "autologin_disabled": True, "pam_verified": True,
                   "assets_verified": True, "greeter_executable": "/usr/lib/x86_64-linux-gnu/libexec/plasma-login-greeter",
                   "wallpaper_executable": "/usr/bin/plasma-login-wallpaper", "native_loaded": True,
                   "demo_graphical_session": False}
        prepared.verify_greeter(greeter, "old-boot")
        for field, value in (("service", "sddm.service"), ("boot_id", "old-boot"),
                             ("native_loaded", False), ("autologin_disabled", False),
                             ("demo_graphical_session", True)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                prepared.verify_greeter(dict(greeter, **{field: value}), "old-boot")

    def test_sealed_disk_and_source_are_verified_when_reopened(self):
        from scripts.showcase import prepared
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            for name, content in (("guest.qcow2", b"owned disk"), ("id_ed25519", b"private fixture key"),
                                  ("SOURCE.bundle", b"source"), ("greeter.png", b"captured pixels"),
                                  ("environment.json", b"{}"), ("base.qcow2", b"pinned base")):
                (run / name).write_bytes(content)
            prepared.seal(run, "a" * 40, run / "base.qcow2", {"accepted": True})
            record = prepared.load(run, "a" * 40)
            self.assertEqual(record["source"], "a" * 40)
            with self.assertRaisesRegex(ValueError, "source"):
                prepared.load(run, "b" * 40)
            (run / "guest.qcow2").write_bytes(b"changed disk")
            with self.assertRaisesRegex(ValueError, "guest.qcow2"):
                prepared.load(run, "a" * 40)


if __name__ == "__main__":
    unittest.main()
