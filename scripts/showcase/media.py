"""Measured media operations for the real showcase tour (FFmpeg + Pillow).

Nothing here supplies scene verification: the tour must provide that evidence.
All output replacement is atomic, and two-pass work belongs to a private directory.
"""

from fractions import Fraction
import hashlib
import io
import json
import math
from pathlib import Path
import shlex
import subprocess
import tempfile

from PIL import Image, ImageChops, ImageStat


REQUIRED_CHAPTERS = ("login", "desktop-rain", "launcher", "terminals", "effects", "lock", "final")
RAIN_CHAPTERS = ("login", "desktop-rain", "lock")
BOUNDARY_TOLERANCE = 0.5


class MediaError(RuntimeError):
    """Unreadable, invalid or unencodable media, including tool diagnostics."""


def _diagnostic(value):
    return value.decode(errors="replace") if isinstance(value, bytes) else (value or "")


def _run(command, timeout=120):
    command = [str(arg) for arg in command]
    description = shlex.join(command)
    try:
        result = subprocess.run(command, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise MediaError(f"Timed out after {timeout}s: {description}\n"
                         f"{_diagnostic(error.stderr)}") from error
    except OSError as error:
        raise MediaError(f"Cannot run {description}: {error}") from error
    # All commands use error-level logging. Decode errors can otherwise be reported
    # on stderr while FFmpeg/ffprobe still exit successfully with partial output.
    if result.returncode or result.stderr.strip():
        raise MediaError(f"Media command exited {result.returncode}: {description}\n"
                         f"{_diagnostic(result.stderr)}")
    return result.stdout


def inspect_video(path):
    """Return codec, pixel_format, width, height, fps, duration, frame_count,
    audio_streams. Frame count is decoded by ffprobe, not guessed from duration.
    Duration and FPS are finite positive floats; dimensions/counts are integers.
    """
    path = Path(path).resolve()
    raw = _run(["ffprobe", "-v", "error", "-threads", "2", "-count_frames",
                "-show_streams", "-show_format", "-of", "json", path])
    try:
        probe = json.loads(raw)
        streams = probe["streams"]
        video = next(stream for stream in streams if stream["codec_type"] == "video")
        rate = video.get("avg_frame_rate", "0/0")
        if rate in ("0/0", "0", "N/A"):
            rate = video["r_frame_rate"]
        duration = video.get("duration", "N/A")
        if duration == "N/A":
            duration = probe["format"]["duration"]
        result = {
            "codec": video["codec_name"],
            "pixel_format": video["pix_fmt"],
            "width": int(video["width"]),
            "height": int(video["height"]),
            "fps": float(Fraction(rate)),
            "duration": float(duration),
            "frame_count": int(video["nb_read_frames"]),
            "audio_streams": sum(stream["codec_type"] == "audio" for stream in streams),
        }
        for field in ("width", "height", "fps", "duration", "frame_count"):
            if not math.isfinite(result[field]) or result[field] <= 0:
                raise ValueError(f"invalid {field}: {result[field]}")
    except (ValueError, TypeError, KeyError, StopIteration, ZeroDivisionError) as error:
        raise MediaError(f"Unreadable or empty video {path}: {error}\n"
                         f"ffprobe: {_diagnostic(raw)}") from error
    return result


def extract_frame(path, seconds):
    """Decode the frame at video-relative seconds to an independent RGB image."""
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError("frame seconds must be finite and nonnegative")
    path = Path(path).resolve()
    raw = _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
                "-threads", "2", "-ss", str(seconds), "-i", path, "-map", "0:v:0",
                "-frames:v", "1", "-an", "-c:v", "png", "-threads", "1",
                "-pix_fmt", "rgb24", "-f", "image2pipe", "pipe:1"])
    if not raw:
        raise MediaError(f"No decoded frame output from {path} at {seconds}s")
    try:
        with Image.open(io.BytesIO(raw)) as image:
            return image.convert("RGB")
    except OSError as error:
        raise MediaError(f"Unreadable decoded frame from {path} at {seconds}s: {error}") from error


def _check_video(info, width, height, fps):
    if info["codec"] != "h264" or info["pixel_format"] != "yuv420p":
        raise MediaError(f"Expected H.264/yuv420p, got {info['codec']}/{info['pixel_format']}")
    if (info["width"], info["height"]) != (width, height):
        raise MediaError(f"Expected dimensions {width}x{height}, got "
                         f"{info['width']}x{info['height']}")
    if not math.isclose(info["fps"], fps, rel_tol=0, abs_tol=0.01):
        raise MediaError(f"Expected {fps} FPS, got {info['fps']}")
    expected_frames = info["duration"] * fps
    if abs(info["frame_count"] - expected_frames) > max(2, expected_frames * 0.01):
        raise MediaError(f"Implausible frame count {info['frame_count']} for "
                         f"{info['duration']}s at {fps} FPS")


def _chapter_timings(chapters, duration):
    if not isinstance(chapters, list) or not chapters:
        raise MediaError("chapters must be a nonempty ordered list")
    try:
        names = [chapter["name"] for chapter in chapters]
        if (any(not isinstance(name, str) for name in names)
                or len(set(names)) != len(names)
                or [name for name in names if name in REQUIRED_CHAPTERS] != list(REQUIRED_CHAPTERS)):
            raise MediaError(f"Required chapters must occur once in order: {REQUIRED_CHAPTERS}")
        previous_end = -BOUNDARY_TOLERANCE
        normalized = []
        for chapter in chapters:
            name, start, end = chapter["name"], chapter["start"], chapter["end"]
            if chapter["verified"] is not True:
                raise MediaError(f"chapter {name} must be verified=True by the real tour")
            if (any(isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) for value in (start, end))
                    or start < -BOUNDARY_TOLERANCE or end > duration + BOUNDARY_TOLERANCE
                    or end <= start or end <= 0 or start >= duration):
                raise MediaError(f"Invalid chapter timing for {name}: {start}..{end}")
            if start < previous_end:
                raise MediaError(f"Overlapping chapter timing for {name}: {start} < {previous_end}")
            previous_end = end
            normalized.append({"name": name, "start": float(start), "end": float(end),
                               "verified": True})
        return normalized
    except (KeyError, TypeError) as error:
        raise MediaError(f"Malformed chapter: {error}") from error


def _background_boxes(width, height):
    # Inset side corners avoid the middle form, top clock/panel and screen edges.
    return [(name, tuple(int(round(value)) for value in box)) for name, box in (
        ("upper-left", (width * .08, height * .15, width * .30, height * .40)),
        ("upper-right", (width * .70, height * .15, width * .92, height * .40)),
        ("lower-left", (width * .08, height * .60, width * .30, height * .85)),
        ("lower-right", (width * .70, height * .60, width * .92, height * .85)),
    )]


def validate_media(path, chapters, width, height, fps=30, min_duration=60, max_duration=150):
    """Validate measured media and return video/chapters/thresholds evidence.

    Three interior frames per chapter must be visible. Rain needs sustained
    changes across both sample intervals in at least two inset background crops.
    Up to 0.5s film-boundary skew is clamped for sampling; overlaps are rejected.
    This detects distributed animation, not the semantic identity of rain/UI.
    """
    if (width < 16 or height < 16 or not math.isfinite(fps) or fps <= 0
            or not math.isfinite(min_duration) or not math.isfinite(max_duration)
            or min_duration < 0 or max_duration < min_duration):
        raise ValueError("invalid dimensions, FPS or duration bounds")
    info = inspect_video(path)
    _check_video(info, width, height, fps)
    if not min_duration <= info["duration"] <= max_duration:
        raise MediaError(f"Video duration {info['duration']} outside {min_duration}..{max_duration}s")
    evidence = _chapter_timings(chapters, info["duration"])
    thresholds = {"boundary_tolerance": BOUNDARY_TOLERANCE, "nonblack_luma": 8,
                  "min_nonblack_fraction": 0.01, "changed_channel_delta": 3,
                  "min_changed_fraction": 0.02, "min_mean_abs_delta": 0.2}
    for chapter in evidence:
        start, end = max(0, chapter["start"]), min(info["duration"], chapter["end"])
        times = [min(start + (end - start) * fraction, info["duration"] - 1 / fps)
                 for fraction in (.2, .5, .8)]
        if any(seconds < start or seconds >= end for seconds in times):
            raise MediaError(f"chapter {chapter['name']} has no sampleable frame within its timing")
        frames = [extract_frame(path, seconds) for seconds in times]
        samples = []
        for seconds, frame in zip(times, frames):
            luma = frame.convert("L")
            histogram = luma.histogram()
            nonblack = sum(histogram[thresholds["nonblack_luma"] + 1:]) / (width * height)
            samples.append({"seconds": seconds, "mean_luma": ImageStat.Stat(luma).mean[0],
                            "nonblack_fraction": nonblack})
            if nonblack < thresholds["min_nonblack_fraction"]:
                raise MediaError(f"chapter {chapter['name']} has black decoded frame at {seconds}s")
        chapter.update(samples=samples, regions=[], moving_regions=0)
        if chapter["name"] not in RAIN_CHAPTERS:
            continue
        for name, box in _background_boxes(width, height):
            crops = [frame.crop(box) for frame in frames]
            comparisons = []
            for index, (before, after) in enumerate(zip(crops, crops[1:])):
                difference = ImageChops.difference(before, after)
                bands = difference.split()
                maximum = ImageChops.lighter(ImageChops.lighter(bands[0], bands[1]), bands[2])
                histogram = maximum.histogram()
                changed = sum(histogram[thresholds["changed_channel_delta"] + 1:])
                comparisons.append({
                    "start": times[index], "end": times[index + 1],
                    "mean_abs_delta": sum(ImageStat.Stat(difference).mean) / 3,
                    "changed_fraction": changed / (maximum.width * maximum.height),
                })
            moving = all(sample["changed_fraction"] >= thresholds["min_changed_fraction"]
                         and sample["mean_abs_delta"] >= thresholds["min_mean_abs_delta"]
                         for sample in comparisons)
            chapter["regions"].append({"name": name, "box": list(box),
                                       "comparisons": comparisons, "moving": moving})
            chapter["moving_regions"] += int(moving)
        if chapter["moving_regions"] < 2:
            raise MediaError(f"chapter {chapter['name']} needs motion in two background regions; "
                             f"measured {chapter['moving_regions']}: {chapter['regions']}")
    return {"video": info, "chapters": evidence, "thresholds": thresholds}


def _target_path(source, target):
    source, target = Path(source), Path(target)
    if source.resolve() == target.resolve() or (target.exists() and source.samefile(target)):
        raise ValueError("source and target must be separate files")
    return target.absolute()


def encode_inline(master, target, max_bytes=9_500_000):
    """Two-pass silent H.264 MP4 with faststart, preserving every frame and speed.

    Return video metadata, size_bytes, max_bytes and requested bitrate_bps.
    Keep source resolution (round odd dimensions down for yuv420p); never upscale.
    Reserve 8% plus MP4 header/per-frame overhead before deriving the bitrate.
    A failed encode/verification leaves any previous target intact.
    """
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
        raise ValueError("max_bytes must be a positive integer byte budget")
    target = _target_path(master, target)
    master = Path(master).resolve()
    source = inspect_video(master)
    width, height = source["width"] // 2 * 2, source["height"] // 2 * 2
    if min(width, height) < 2:
        raise MediaError("Source dimensions are too small for yuv420p without upscaling")
    usable_bytes = int(max_bytes * .92) - 4096 - source["frame_count"] * 16
    bitrate = int(usable_bytes * 8 / source["duration"])
    if bitrate < 1000:
        raise MediaError(f"Byte budget {max_bytes} cannot cover media/container overhead")
    with tempfile.TemporaryDirectory(prefix=f".{target.name}-", dir=target.parent) as directory:
        directory = Path(directory)
        staged = directory / "inline.mp4"
        common = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                  "-threads", "2", "-i", master, "-map", "0:v:0", "-an", "-sn", "-dn",
                  "-map_metadata", "-1", "-map_chapters", "-1",
                  "-vf", f"scale={width}:{height}", "-c:v", "libx264", "-preset", "medium",
                  "-threads", "2", "-pix_fmt", "yuv420p", "-b:v", str(bitrate),
                  "-fps_mode", "passthrough", "-passlogfile", directory / "pass"]
        timeout = max(120, source["duration"] * 20)
        _run(common + ["-pass", "1", "-f", "null", "-"], timeout=timeout)
        _run(common + ["-pass", "2", "-movflags", "+faststart", "-f", "mp4", staged],
             timeout=timeout)
        result = inspect_video(staged)
        _check_video(result, width, height, source["fps"])
        if (result["audio_streams"] != 0 or result["frame_count"] != source["frame_count"]
                or abs(result["duration"] - source["duration"]) > 1 / source["fps"] + .001):
            raise MediaError(f"Inline media did not preserve silent, full-speed footage: "
                             f"source={source}, encoded={result}")
        size = staged.stat().st_size
        if size <= 0 or size > max_bytes:
            raise MediaError(f"Encoded size {size} exceeds byte budget {max_bytes}")
        staged.replace(target)
    return {"video": result, "size_bytes": size, "max_bytes": max_bytes, "bitrate_bps": bitrate}


def make_poster(video, target, seconds):
    """Atomically save an actual decoded frame as PNG; return None."""
    target = _target_path(video, target)
    image = extract_frame(video, seconds)
    with tempfile.TemporaryDirectory(prefix=f".{target.name}-", dir=target.parent) as directory:
        staged = Path(directory) / "poster.png"
        image.save(staged, format="PNG")
        staged.replace(target)


def file_sha256(path):
    """Return the lowercase hex SHA-256 digest using bounded-memory reads."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
