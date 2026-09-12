"""Resumable large-image acquisition; Python alone accepts the final bytes."""

import hashlib
import os
from pathlib import Path
import shlex
import subprocess


def verified_image_download(url, path, algorithm, digest, *, log_path, timeout=1800):
    """Return verified cache bytes or atomically replace them after aria2 completes.

    The caller holds the workspace lock. Partial/control files live under its
    owned cache, keyed by the expected digest, and survive failures/interruption.
    A total transfer deadline is followed by at most five seconds for aria2 to
    save its resume state and exit. Completed checksum failures discard only the
    rejected partial state, allowing a fresh retry without touching the target.
    """
    algorithm = hashlib.new(algorithm).name
    digest = digest.lower()
    if (len(digest) != hashlib.new(algorithm).digest_size * 2 or not digest
            or any(character not in "0123456789abcdef" for character in digest)):
        raise ValueError("expected a full hexadecimal image digest")
    if timeout <= 0:
        raise ValueError("image transfer timeout must be positive")
    destination = Path(path)
    with Path(log_path).open("a") as log:
        if destination.exists():
            with destination.open("rb") as stream:
                actual = hashlib.file_digest(stream, algorithm).hexdigest()
            log.write(f"Cached {destination}: {algorithm}={actual}\n")
            if actual == digest:
                log.write("Verified cache; no network required.\n")
                return destination

        state = destination.parent / ".downloads" / f"{algorithm}-{digest}"
        state.mkdir(parents=True, exist_ok=True, mode=0o700)
        partial = state / "image.part"
        control = state / "image.part.aria2"
        command = [
            "aria2c", "--no-conf", "--continue=true", "--auto-file-renaming=false",
            "--allow-overwrite=false", "--file-allocation=none", "--disk-cache=0",
            "--split=8", "--max-connection-per-server=8", "--min-split-size=1M",
            "--connect-timeout=15", "--timeout=30", "--max-tries=5", "--retry-wait=5",
            "--auto-save-interval=1", "--summary-interval=30", "--enable-color=false",
            "--console-log-level=notice", "--download-result=full",
            f"--dir={state}", f"--out={partial.name}", "--", url,
        ]
        log.write(f"Expected {algorithm}={digest}; transfer deadline={timeout}s\n"
                  f"Resume state: {partial}\n$ {shlex.join(command)}\n")
        log.flush()
        try:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
            try:
                try:
                    returncode = process.wait(timeout=timeout)
                except subprocess.TimeoutExpired as error:
                    raise TimeoutError(f"image transfer timed out after {timeout}s") from error
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
            log.write(f"aria2 exit status: {returncode}\n")
            if returncode != 0:
                raise RuntimeError(f"aria2 image transfer failed ({returncode}); see {log_path}")

            # Successful transport is not acceptance. Read the actual full file
            # independently, including any resumed bytes, before atomic promotion.
            with partial.open("rb") as stream:
                actual = hashlib.file_digest(stream, algorithm).hexdigest()
                log.write(f"Downloaded {os.fstat(stream.fileno()).st_size} bytes: "
                          f"{algorithm}={actual}\n")
                if actual != digest:
                    partial.unlink()
                    control.unlink(missing_ok=True)
                    raise ValueError("image download checksum mismatch")
                os.fsync(stream.fileno())
            os.replace(partial, destination)
            control.unlink(missing_ok=True)
            log.write(f"Verified image atomically promoted to {destination}\n")
        except BaseException as error:
            log.write(f"{type(error).__name__}: {error}\n")
            raise
    return destination
