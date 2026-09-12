"""Measured media operations for the real showcase tour (FFmpeg + Pillow).

Nothing here supplies scene verification: the tour must provide that evidence.
All output replacement is atomic, and two-pass work belongs to a private directory.
"""

from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import re
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


def _run(command, timeout=120, *, capture_log=False):
    command = [str(arg) for arg in command]
    description = shlex.join(command)
    try:
        result = subprocess.run(command, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise MediaError(f"Timed out after {timeout}s: {description}\n"
                         f"{_diagnostic(error.stderr)}") from error
    except OSError as error:
        raise MediaError(f"Cannot run {description}: {error}") from error
    # Default commands use error-level logging: stderr can reveal partial decode
    # even with exit zero. The -xerror RGB decoder instead captures showinfo logs.
    if result.returncode or (result.stderr.strip() and not capture_log):
        raise MediaError(f"Media command exited {result.returncode}: {description}\n"
                         f"{_diagnostic(result.stderr)}")
    return (result.stdout, result.stderr) if capture_log else result.stdout


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


def _frame_timeline(path):
    """Read decoded presentation-order PTS, keeping rational time-base precision."""
    path = Path(path).resolve()
    raw = _run(["ffprobe", "-v", "error", "-threads", "2", "-select_streams", "v:0",
                "-show_frames", "-show_entries", "stream=width,height,time_base:frame=pts",
                "-of", "json", path])
    try:
        probe = json.loads(raw)
        stream = probe["streams"][0]
        time_base = Fraction(stream["time_base"])
        pts = [int(frame["pts"]) for frame in probe["frames"]]
        if not pts or time_base <= 0 or any(a >= b for a, b in zip(pts, pts[1:])):
            raise ValueError("missing or non-increasing frame presentation timestamps")
        return {"pts": pts, "time_base": time_base, "start_pts": pts[0],
                "width": int(stream["width"]), "height": int(stream["height"])}
    except (ValueError, TypeError, KeyError, IndexError, ZeroDivisionError) as error:
        raise MediaError(f"Unreadable frame timeline from {path}: {error}\n"
                         f"ffprobe: {_diagnostic(raw)}") from error


def _decode_selected(path, timeline, indices):
    """Decode exact frame indices once, verifying the actual FFmpeg output PTS.

    No seek or FPS conversion can substitute a neighboring frame. showinfo is
    attached to the RGB filter output; -xerror makes decode errors fatal even
    though info-level timestamp diagnostics are captured on successful runs.
    """
    indices = sorted(set(indices))
    selection = "+".join(f"eq(n,{index})" for index in indices)
    raw, log = _run(["ffmpeg", "-hide_banner", "-loglevel", "info", "-nostdin", "-xerror",
                     "-copyts", "-threads", "2", "-i", Path(path).resolve(), "-map", "0:v:0",
                     "-vf", f"select='{selection}',format=rgb24,showinfo=checksum=0",
                     "-an", "-fps_mode", "passthrough", "-c:v", "rawvideo", "-threads", "1",
                     "-f", "rawvideo", "pipe:1"], capture_log=True)
    log = _diagnostic(log)
    bases = re.findall(r"config in time_base:\s*(\d+/\d+)", log)
    decoded_pts = [int(value) for value in re.findall(r"\bn:\s*\d+\s+pts:\s*(-?\d+)\s+pts_time:", log)]
    frame_bytes = timeline["width"] * timeline["height"] * 3
    if (not bases or any(Fraction(base) != timeline["time_base"] for base in bases)
            or decoded_pts != [timeline["pts"][index] for index in indices]
            or len(raw) != frame_bytes * len(indices)):
        raise MediaError(f"Decoded frame/PTS output mismatch from {path}\n{log}")
    frames = {}
    for offset, (index, pts) in enumerate(zip(indices, decoded_pts)):
        image = Image.frombytes("RGB", (timeline["width"], timeline["height"]),
                                raw[offset * frame_bytes:(offset + 1) * frame_bytes])
        image.info.update(frame_index=index, pts=pts, time_base=str(timeline["time_base"]),
                          start_pts=timeline["start_pts"],
                          seconds=float((pts - timeline["start_pts"]) * timeline["time_base"]))
        frames[index] = image
    return frames


def extract_frame(path, seconds):
    """Return the first RGB frame presented at/after video-relative seconds.

    image.info records actual seconds, frame_index, pts, time_base and start_pts.
    The video's first presented frame is time zero, including nonzero-start media.
    """
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError("frame seconds must be finite and nonnegative")
    timeline = _frame_timeline(path)
    target = Fraction(str(seconds))
    for index, pts in enumerate(timeline["pts"]):
        if (pts - timeline["start_pts"]) * timeline["time_base"] >= target:
            return _decode_selected(path, timeline, [index])[index]
    raise MediaError(f"No decoded frame output from {path} at/after {seconds}s")


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


def _chapter_selection(chapter, timeline, duration):
    start = max(Fraction(0), Fraction(str(chapter["start"])))
    end = min(Fraction(str(duration)), Fraction(str(chapter["end"])))
    times = [(pts - timeline["start_pts"]) * timeline["time_base"] for pts in timeline["pts"]]
    eligible = [index for index, seconds in enumerate(times) if start <= seconds < end]
    if not eligible:
        raise MediaError(f"chapter {chapter['name']} has no actual frame within its timing")
    centers = [start + (end - start) * fraction for fraction in
               (Fraction(1, 5), Fraction(1, 2), Fraction(4, 5))]
    if chapter["name"] not in RAIN_CHAPTERS:
        return sorted({min(eligible, key=lambda index: abs(times[index] - center))
                       for center in centers}), []
    # Disjoint windows: at most 0.2s wide and at most 20% of a chapter. Selecting
    # actual endpoints inside each window prevents a single flash from supplying
    # the motion evidence for more than one pair. Never compare across windows.
    half_width = min(Fraction(1, 10), (end - start) / 10)
    pairs = []
    for center in centers:
        window = [index for index in eligible if center - half_width <= times[index] <= center + half_width]
        if len(window) < 2:
            raise MediaError(f"chapter {chapter['name']} needs two actual frames in each "
                             "separated background motion window")
        pairs.append((window[0], window[-1]))
    return [index for pair in pairs for index in pair], pairs


def validate_media(path, chapters, width, height, fps=30, min_duration=60, max_duration=150):
    """Validate measured media and return video/chapters/thresholds evidence.

    Actual PTS must lie inside each half-open chapter interval. Rain needs changes
    in three separated short pairs with no shared frame, in two background crops.
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
    timeline = _frame_timeline(path)
    if (len(timeline["pts"]) != info["frame_count"]
            or (timeline["width"], timeline["height"]) != (width, height)):
        raise MediaError("Frame timeline does not match inspected video")
    selections = [_chapter_selection(chapter, timeline, info["duration"]) for chapter in evidence]
    frames = _decode_selected(path, timeline, [index for indices, _ in selections for index in indices])
    thresholds = {"boundary_tolerance": BOUNDARY_TOLERANCE, "nonblack_luma": 8,
                  "min_nonblack_fraction": 0.01, "changed_channel_delta": 3,
                  "min_changed_fraction": 0.02, "min_mean_abs_delta": 0.2}
    for chapter, (indices, pairs) in zip(evidence, selections):
        samples = []
        for index in indices:
            frame = frames[index]
            actual = (frame.info["pts"] - timeline["start_pts"]) * timeline["time_base"]
            if not Fraction(str(chapter["start"])) <= actual < Fraction(str(chapter["end"])):
                raise MediaError(f"Decoded frame outside chapter {chapter['name']}: {actual}s")
            luma = frame.convert("L")
            histogram = luma.histogram()
            nonblack = sum(histogram[thresholds["nonblack_luma"] + 1:]) / (width * height)
            samples.append({"seconds": float(actual), "frame_index": index, "pts": frame.info["pts"],
                            "mean_luma": ImageStat.Stat(luma).mean[0],
                            "nonblack_fraction": nonblack})
            if nonblack < thresholds["min_nonblack_fraction"]:
                raise MediaError(f"chapter {chapter['name']} has black decoded frame at {float(actual)}s")
        chapter.update(samples=samples, regions=[], moving_regions=0)
        if chapter["name"] not in RAIN_CHAPTERS:
            continue
        for name, box in _background_boxes(width, height):
            comparisons = []
            for first, last in pairs:
                difference = ImageChops.difference(frames[first].crop(box), frames[last].crop(box))
                bands = difference.split()
                maximum = ImageChops.lighter(ImageChops.lighter(bands[0], bands[1]), bands[2])
                histogram = maximum.histogram()
                changed = sum(histogram[thresholds["changed_channel_delta"] + 1:])
                comparisons.append({
                    "start": frames[first].info["seconds"], "end": frames[last].info["seconds"],
                    "start_frame_index": first, "end_frame_index": last,
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
    return {"video": info, "chapters": evidence, "thresholds": thresholds,
            "timeline": {"time_base": str(timeline["time_base"]), "start_pts": timeline["start_pts"]}}


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
