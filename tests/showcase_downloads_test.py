#!/usr/bin/env python3
"""Local HTTP + real aria2 regressions; requires the recorder or CI image.

Run in the recorder image with --entrypoint python3 and a read-only /src mount:
    tests/showcase_downloads_test.py -v
Missing aria2 is an explicit suite failure, never a skipped/passing transfer test.
These synthetic bytes are not evidence for the pinned Debian image.
"""

import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.showcase import downloads


class ImageHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        data = self.server.data
        header = self.headers.get("Range")
        start, end = 0, len(data) - 1
        if header:
            first, last = header.removeprefix("bytes=").split("-", 1)
            start = int(first)
            if last:
                end = min(int(last), end)
        with self.server.guard:
            self.server.ranges.append((start, end, header))
            self.server.active += 1
            self.server.peak_active = max(self.server.active, self.server.peak_active)
        try:
            if self.server.status != 200:
                self.send_error(self.server.status)
                return
            if start >= len(data):
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{len(data)}")
                self.end_headers()
                return
            self.send_response(206 if header else 200)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            if header:
                self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
            self.end_headers()
            sent = 0
            for offset in range(start, end + 1, 64 * 1024):
                if self.server.stall and sent >= 1024 * 1024:
                    self.server.release.wait(15)
                    return
                chunk = data[offset:min(offset + 64 * 1024, end + 1)]
                self.wfile.write(chunk)
                self.wfile.flush()
                sent += len(chunk)
                with self.server.guard:
                    self.server.bytes_sent += len(chunk)
                # Leave time for real concurrent range requests, without a
                # mocked downloader or an external/slow Internet dependency.
                time.sleep(0.002)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            with self.server.guard:
                self.server.active -= 1


class ImageServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, data):
        super().__init__(("127.0.0.1", 0), ImageHandler)
        self.data = data
        self.guard = threading.Lock()
        self.ranges = []
        self.active = self.peak_active = self.bytes_sent = 0
        self.stall = False
        self.status = 200
        self.closed = False
        self.release = threading.Event()
        self.thread = threading.Thread(target=self.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server_port}/image.qcow2"

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.release.set()
        self.shutdown()
        self.server_close()
        self.thread.join(3)


class ImageDownloadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if shutil.which("aria2c") is None:
            raise RuntimeError("real aria2c required: run in the recorder or CI image")
        cls.data = os.urandom(16 * 1024 * 1024)
        cls.digest = hashlib.sha512(cls.data).hexdigest()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.destination = self.root / "cache" / "debian.qcow2"
        self.destination.parent.mkdir()
        self.log = self.root / "image-download.log"
        self.partial = (self.destination.parent / ".downloads" /
                        f"sha512-{self.digest}" / "image.part")
        self.control = self.partial.with_name("image.part.aria2")

    def serve(self):
        server = ImageServer(self.data)
        self.addCleanup(server.close)
        return server

    def download(self, url, **kwargs):
        return downloads.verified_image_download(
            url, self.destination, "sha512", self.digest, log_path=self.log, **kwargs)

    def test_exact_multiconnection_bytes_atomically_replace_invalid_cache(self):
        server = self.serve()
        self.destination.write_bytes(b"previous invalid cache")
        with self.destination.open("rb") as previous:
            inode = os.fstat(previous.fileno()).st_ino
            self.assertEqual(self.download(server.url), self.destination)
            self.assertEqual(previous.read(), b"previous invalid cache")
        self.assertEqual(self.destination.read_bytes(), self.data)
        self.assertNotEqual(self.destination.stat().st_ino, inode)
        self.assertGreater(server.peak_active, 1)
        self.assertTrue(any(start > 0 for start, _, _ in server.ranges))
        self.assertFalse(self.partial.exists())
        self.assertFalse(self.control.exists())
        self.assertIn(self.digest, self.log.read_text())

    def test_bad_checksum_preserves_target_and_can_retry_fresh_bytes(self):
        server = self.serve()
        server.data = b"wrong bytes" + self.data[11:]
        self.destination.write_bytes(b"previous cached image")
        inode = self.destination.stat().st_ino
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            self.download(server.url)
        self.assertEqual(self.destination.read_bytes(), b"previous cached image")
        self.assertEqual(self.destination.stat().st_ino, inode)
        self.assertIn(hashlib.sha512(server.data).hexdigest(), self.log.read_text())
        server.data = self.data
        self.download(server.url)
        self.assertEqual(self.destination.read_bytes(), self.data)

    def test_interruption_retains_state_then_resumes_without_full_redownload(self):
        server = self.serve()
        server.stall = True
        started = time.monotonic()
        with self.assertRaises(TimeoutError):
            self.download(server.url, timeout=3)
        self.assertLess(time.monotonic() - started, 12)
        self.assertFalse(self.destination.exists())
        self.assertTrue(self.partial.exists())
        self.assertGreater(self.control.stat().st_size, 0)
        self.assertGreater(server.bytes_sent, 1024 * 1024)
        self.assertIn("timed out", self.log.read_text())
        # Close the first peer so traffic accounting measures only the resume.
        server.close()
        resumed = self.serve()
        self.download(resumed.url)
        self.assertEqual(self.destination.read_bytes(), self.data)
        self.assertTrue(any(start > 0 for start, _, _ in resumed.ranges))
        self.assertLess(resumed.bytes_sent, len(self.data))
        self.assertFalse(self.control.exists())

    def test_verified_cache_reuse_hashes_content_without_network(self):
        server = self.serve()
        self.destination.write_bytes(self.data)
        inode = self.destination.stat().st_ino
        self.download(server.url)
        self.assertEqual(server.ranges, [])
        self.assertEqual(self.destination.stat().st_ino, inode)
        # A present-but-corrupted file must not get the same cache fast path.
        with self.destination.open("r+b") as stream:
            stream.write(b"corrupt")
        self.download(server.url)
        self.assertTrue(server.ranges)
        self.assertEqual(self.destination.read_bytes(), self.data)

    def test_existing_sequential_prefix_uses_normal_aria2_resume(self):
        server = self.serve()
        self.partial.parent.mkdir(parents=True)
        prefix_size = 5 * 1024 * 1024
        self.partial.write_bytes(self.data[:prefix_size])
        self.download(server.url)
        self.assertEqual(self.destination.read_bytes(), self.data)
        self.assertTrue(any(start >= prefix_size for start, _, _ in server.ranges))
        self.assertLess(server.bytes_sent, len(self.data))

    def test_failed_http_transfer_preserves_cache_and_records_tool_diagnostics(self):
        server = self.serve()
        server.status = 404
        self.destination.write_bytes(b"previous cached image")
        with self.assertRaisesRegex(RuntimeError, "aria2 image transfer failed"):
            self.download(server.url)
        self.assertEqual(self.destination.read_bytes(), b"previous cached image")
        self.assertIn("Resource not found", self.log.read_text())
        self.assertIn("aria2 exit status:", self.log.read_text())


if __name__ == "__main__":
    unittest.main()
