"""Encode the captured film for GitHub and extract its real poster frame."""

from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


def inspect_video(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-show_streams", "-show_format",
         "-of", "json", str(Path(path).resolve())],
        check=True, capture_output=True, text=True, timeout=300)
    data = json.loads(result.stdout)
    video = next(stream for stream in data["streams"] if stream["codec_type"] == "video")
    info = {
        "codec": video["codec_name"], "pixel_format": video["pix_fmt"],
        "width": video["width"], "height": video["height"],
        "fps": float(Fraction(video["avg_frame_rate"])),
        "duration": float(video.get("duration", data["format"]["duration"])),
        "frame_count": int(video.get("nb_read_frames", video.get("nb_frames", 0))),
    }
    if info["duration"] <= 0 or info["frame_count"] <= 0:
        raise RuntimeError("the recorded film is empty")
    return info


def encode_inline(master, target, max_bytes=9_500_000):
    master, target = Path(master).resolve(), Path(target).resolve()
    if master == target:
        raise ValueError("keep the master and inline film separate")
    source = inspect_video(master)
    bitrate = int(max_bytes * .90 * 8 / source["duration"])
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".encode-", dir=target.parent) as temporary:
        temporary = Path(temporary)
        staged = temporary / "inline.mp4"
        common = ["ffmpeg", "-v", "error", "-y", "-i", str(master), "-an",
                  "-c:v", "libx264", "-preset", "fast", "-threads", "2",
                  "-b:v", str(bitrate), "-pix_fmt", "yuv420p",
                  "-passlogfile", str(temporary / "pass")]
        for command in (common + ["-pass", "1", "-f", "null", "/dev/null"],
                        common + ["-pass", "2", "-movflags", "+faststart", str(staged)]):
            subprocess.run(command, check=True, timeout=max(300, source["duration"] * 15))
        info = inspect_video(staged)
        if (staged.stat().st_size > max_bytes or info["frame_count"] != source["frame_count"]
                or abs(info["duration"] - source["duration"]) > .1):
            raise RuntimeError("inline encoding exceeded its budget or lost part of the film")
        os.replace(staged, target)
    return {"video": info, "size_bytes": target.stat().st_size}


def make_poster(video, target, seconds):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(seconds),
                    "-i", str(video), "-frames:v", "1", "-threads", "1", str(target)],
                   check=True, timeout=120)


def file_sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()
