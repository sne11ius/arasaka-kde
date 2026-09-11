"""Acceptance gates and integrity manifest for a powered-off showcase guest."""

import hashlib
import json
from pathlib import Path


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_convergence(first, second, source, bundle_hash):
    for result in (first, second):
        if (result.get("ready") is not True or result.get("source") != source
                or result.get("source_bundle_sha256") != bundle_hash
                or result.get("session_type") != "wayland" or result.get("plasma_ready") is not True
                or result.get("panels") != 0
                or result.get("wallpaper", {}).get("plugin") != "online.knowmad.shaderwallpaper"
                or result.get("wallpaper", {}).get("native_loaded") is not True
                or result.get("window_policy", {}).get("loaded") is not True
                or not result["window_policy"].get("nativeRevision")
                or not all(result.get("plm", {}).get(key) is True for key in
                           ("selected", "autologin_disabled", "pam_verified", "assets_verified"))):
            raise ValueError("real managed Plasma/PLM preparation is not ready for this source")
    if not first.get("managed_fingerprint") or first["managed_fingerprint"] != second.get("managed_fingerprint"):
        raise ValueError("repeat preparation did not converge: managed settings differ")


def verify_greeter(result, setup_boot):
    if (result.get("ready") is not True or result.get("boot_id") in (None, setup_boot)
            or result.get("service") != "plasmalogin.service"
            or result.get("greeter_executable") != "/usr/lib/x86_64-linux-gnu/libexec/plasma-login-greeter"
            or result.get("wallpaper_executable") != "/usr/bin/plasma-login-wallpaper"
            or result.get("demo_graphical_session") is not False
            or not all(result.get(key) is True for key in
                       ("active", "autologin_disabled", "pam_verified", "assets_verified", "native_loaded"))):
        raise ValueError("post-reboot real PLM greeter is not ready")


def verify_frame(path, display):
    from PIL import Image
    with Image.open(path) as image:
        if image.size != (display["width"], display["height"]):
            raise ValueError(f"incorrect showcase framing: {path}: {image.size}")
        image.verify()
    return {key: display[key] for key in ("width", "height")}


def seal(run, source, base, evidence):
    """Called only after acceptance gates and QEMU's clean shutdown have passed."""
    run, base = Path(run), Path(base)
    files = ("guest.qcow2", "id_ed25519", "SOURCE.bundle", "environment.json", "greeter.png")
    record = {"schema": 1, "state": "sealed", "source": source,
              "files": {name: digest(run / name) for name in files},
              "base": {"path": str(base.relative_to(run.parent)), "sha256": digest(base)},
              "acceptance": evidence}
    pending = run / "prepared.pending"
    pending.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n")
    pending.replace(run / "prepared.json")
    return record


def load(run, source):
    """Task 3 can validate a seal before cold-booting its owned disk.

    The disk changes on boot; record into a NEW overlay backed by this sealed
    disk. Paths are workspace-relative so the container mount can move.
    """
    run = Path(run).resolve()
    record = json.loads((run / "prepared.json").read_text())
    if record.get("schema") != 1 or record.get("state") != "sealed" or record.get("source") != source:
        raise ValueError("prepared source identity differs; prepare a new disposable guest")
    required = {"guest.qcow2", "id_ed25519", "SOURCE.bundle", "environment.json", "greeter.png"}
    if set(record["files"]) != required:
        raise ValueError("incomplete prepared guest file inventory")
    for name, expected in record["files"].items():
        path = run / name
        if path.is_symlink() or digest(path) != expected:
            raise ValueError(f"sealed guest integrity differs: {name}")
    base = run.parent / record["base"]["path"]
    if not base.resolve().is_relative_to(run.parent) or digest(base) != record["base"]["sha256"]:
        raise ValueError("sealed guest base image differs")
    return record
