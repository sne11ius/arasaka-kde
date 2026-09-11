"""Small, synchronous transports for the disposable showcase guest."""

from collections import deque
import json
from pathlib import Path
import socket
import subprocess
import threading
import time


class QMPError(RuntimeError):
    """A QEMU command was rejected."""


class QMP:
    """Serialize commands, match reply IDs, and retain asynchronous events.

    Each exchange has one deadline, including time spent receiving events. A
    timed-out/broken connection is closed rather than reused with stale replies.
    """

    def __init__(self, socket_path, timeout=10):
        self.timeout = timeout
        self.events = deque(maxlen=256)
        self._id = 0
        self._lock = threading.Lock()
        self._buffer = b""
        self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self._socket.settimeout(timeout)
            self._socket.connect(str(socket_path))
            greeting = self._receive(time.monotonic() + timeout)
            if "QMP" not in greeting:
                raise ConnectionError("missing QMP greeting")
            self.execute("qmp_capabilities")
        except BaseException:
            self.close()
            raise

    def _receive(self, deadline):
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("QMP reply deadline exceeded")
            if b"\n" in self._buffer:
                line, self._buffer = self._buffer.split(b"\n", 1)
                return json.loads(line)
            self._socket.settimeout(remaining)
            data = self._socket.recv(65536)
            if not data:
                raise ConnectionError("QMP disconnected before replying")
            self._buffer += data

    def execute(self, command, arguments=None):
        with self._lock:
            self._id += 1
            request = {"execute": command, "id": self._id}
            if arguments is not None:
                request["arguments"] = arguments
            deadline = time.monotonic() + self.timeout
            try:
                self._socket.settimeout(self.timeout)
                self._socket.sendall(json.dumps(request).encode() + b"\n")
                while True:
                    reply = self._receive(deadline)
                    if "event" in reply:
                        self.events.append(reply)
                        continue
                    if reply.get("id") != self._id:
                        continue
                    if "error" in reply:
                        error = reply["error"]
                        raise QMPError(f"{error['class']}: {error['desc']}")
                    return reply["return"]
            except (OSError, ValueError, KeyError):
                self.close()
                raise

    def close(self):
        self._socket.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class Guest:
    """Key-only SSH to one loopback fixture port, independent of host SSH config."""

    def __init__(self, port, key):
        if not isinstance(port, int) or not 1 <= port <= 65535:
            raise ValueError("invalid fixture SSH port")
        self.port = port
        self.key = Path(key).resolve()

    def run(self, command, timeout=60, *, stdin=None):
        args = [
            "ssh", "-F", "/dev/null", "-T", "-p", str(self.port), "-i", str(self.key),
            "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "IdentityAgent=none",
            "-o", "PreferredAuthentications=publickey", "-o", "ConnectTimeout=5",
            "-o", "ConnectionAttempts=1", "-o", "ServerAliveInterval=10",
            "-o", "ServerAliveCountMax=3", "-o", "StrictHostKeyChecking=accept-new",
            "-o", "GlobalKnownHostsFile=/dev/null",
            "-o", f"UserKnownHostsFile={self.key.parent / 'known_hosts'}",
            "demo@127.0.0.1", command,
        ]
        with (self.key.parent / "ssh.log").open("a", encoding="utf-8") as log:
            log.write(f"$ {command}\n")
            try:
                result = subprocess.run(args, stdin=stdin if stdin is not None else subprocess.DEVNULL,
                                        capture_output=True, text=True, check=True, timeout=timeout)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
                log.write(f"{error}\nstdout: {error.stdout!r}\nstderr: {error.stderr!r}\n")
                raise
            log.write(result.stderr)
            return result
