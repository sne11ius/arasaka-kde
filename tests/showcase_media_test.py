#!/usr/bin/env python3
"""Real FFmpeg regressions using TEMPORARY SYNTHETIC fixtures, never showcase proof."""

import hashlib
from fractions import Fraction
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, ImageChops, ImageStat

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.showcase import media


class SyntheticMediaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Dependencies are required: CI must not silently skip real media tests.
        for tool in ("ffmpeg", "ffprobe"):
            if not shutil.which(tool):
                raise RuntimeError(f"SYNTHETIC media tests require {tool}")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="synthetic-media-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def clip(self, name="synthetic.mp4", source=None, duration=3.5,
             codec="libx264", pixel_format="yuv420p", audio=False):
        path = self.root / name
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
                   "-f", "lavfi", "-i", source or "testsrc2=size=160x96:rate=30"]
        if audio:
            command += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=8000"]
        command += ["-t", str(duration), "-c:v", codec, "-pix_fmt", pixel_format,
                    "-threads", "2"]
        if codec == "libx264":
            command += ["-preset", "ultrafast", "-crf", "10"]
        if audio:
            command += ["-c:a", "aac"]
        result = subprocess.run(command + [str(path)], capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        return path


class InspectionTest(SyntheticMediaTest):
    def test_inspection_measures_decodable_frames_and_audio(self):
        path = self.clip(audio=True)
        result = media.inspect_video(path)
        self.assertEqual(result["codec"], "h264")
        self.assertEqual(result["pixel_format"], "yuv420p")
        self.assertEqual((result["width"], result["height"]), (160, 96))
        self.assertEqual(result["fps"], 30)
        self.assertAlmostEqual(result["duration"], 3.5, places=2)
        self.assertEqual(result["frame_count"], 105)
        self.assertEqual(result["audio_streams"], 1)
        json.dumps(result, allow_nan=False)

    def test_inspection_counts_frames_without_container_frame_count(self):
        path = self.clip("synthetic.mkv", duration=0.5, codec="ffv1")
        self.assertEqual(media.inspect_video(path)["frame_count"], 15)

    def test_corrupt_payload_cannot_pass_on_intact_container_metadata(self):
        path = self.clip()
        data = bytearray(path.read_bytes())
        payload = data.index(b"mdat") + 4
        data[payload:payload + 4000] = b"\x00" * 4000
        path.write_bytes(data)
        with self.assertRaisesRegex(media.MediaError, "ffprobe"):
            media.inspect_video(path)

    def test_missing_tool_reports_command_and_input(self):
        path = self.root / "synthetic.mp4"
        with patch.dict(os.environ, PATH=""):
            with self.assertRaisesRegex(media.MediaError, "Cannot run ffprobe.*synthetic.mp4"):
                media.inspect_video(path)

    def test_unreadable_empty_and_audio_only_inputs_fail_with_diagnostics(self):
        empty = self.root / "empty.mp4"
        empty.touch()
        invalid = self.root / "invalid.mp4"
        invalid.write_text("not a video")
        audio = self.root / "audio.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                        "sine=duration=0.1", str(audio)], check=True, capture_output=True)
        for path in (self.root / "missing.mp4", empty, invalid, audio):
            with self.subTest(path=path.name), self.assertRaises(media.MediaError) as caught:
                media.inspect_video(path)
            self.assertIn(path.name, str(caught.exception))

    def test_extract_decodes_rgb_at_requested_time(self):
        path = self.clip(source="color=red:size=160x96:rate=30", duration=0.5)
        image = media.extract_frame(path, 0.2)
        self.assertEqual(image.mode, "RGB")
        self.assertEqual(image.size, (160, 96))
        red, green, blue = image.getpixel((80, 48))
        self.assertGreater(red, 245)
        self.assertLess(max(green, blue), 5)
        moving = self.clip("moving.mp4")
        difference = ImageChops.difference(media.extract_frame(moving, 0.1),
                                          media.extract_frame(moving, 2.8))
        self.assertGreater(sum(ImageStat.Stat(difference).mean), 10)

    def test_extract_rejects_missing_output_and_invalid_time(self):
        path = self.clip(duration=0.2)
        with self.assertRaisesRegex(media.MediaError, "frame|output"):
            media.extract_frame(path, 10)
        for seconds in (-1, float("nan"), float("inf")):
            with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                media.extract_frame(path, seconds)

    def test_extract_reports_returned_frame_pts_after_seek_between_frames(self):
        image = media.extract_frame(self.clip(), 0.25)
        self.assertAlmostEqual(image.info.get("seconds", -1), 8 / 30, places=6)
        self.assertEqual(image.info["frame_index"], 8)
        self.assertAlmostEqual(float(Fraction(image.info["time_base"]) *
                                     (image.info["pts"] - image.info["start_pts"])), 8 / 30)

    def test_extract_normalizes_nonzero_pts_and_handles_b_frame_reordering(self):
        source = self.clip()
        shifted = self.root / "shifted-b-frames.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(source), "-an",
                        "-c:v", "libx264", "-bf", "3", "-threads", "2",
                        "-output_ts_offset", "5", str(shifted)],
                       check=True, capture_output=True, timeout=30)
        image = media.extract_frame(shifted, 0.25)
        self.assertAlmostEqual(image.info.get("seconds", -1), 8 / 30, places=6)
        self.assertEqual(image.info["frame_index"], 8)
        self.assertAlmostEqual(float(Fraction(image.info["time_base"]) * image.info["pts"]),
                               5 + 8 / 30, places=6)
        difference = ImageChops.difference(image, media.extract_frame(source, 8 / 30))
        self.assertLess(sum(ImageStat.Stat(difference).mean) / 3, 5)

    def test_decoder_rejects_actual_pts_that_disagree_with_probed_selection(self):
        source = self.clip()
        timeline = media._frame_timeline(source)
        shifted = self.root / "different-pts.mp4"
        # Same compressed pictures/time base, different real timestamps. This
        # catches trusting the probe alone without verifying the RGB decoder PTS.
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(source), "-c", "copy",
                        "-output_ts_offset", "5", str(shifted)],
                       check=True, capture_output=True, timeout=30)
        with self.assertRaisesRegex(media.MediaError, "PTS output mismatch"):
            media._decode_selected(shifted, timeline, [8])

    def test_poster_is_requested_video_frame_and_failure_is_atomic(self):
        path = self.clip()
        target = self.root / "poster.png"
        media.make_poster(path, target, 1.3)
        with Image.open(target) as poster:
            self.assertEqual(poster.format, "PNG")
            self.assertIsNone(ImageChops.difference(
                poster.convert("RGB"), media.extract_frame(path, 1.3)).getbbox())
        before = target.read_bytes()
        with self.assertRaises(media.MediaError):
            media.make_poster(path, target, 100)
        self.assertEqual(target.read_bytes(), before)
        with self.assertRaises(ValueError):
            media.make_poster(path, path, 0.1)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()),
                         ["poster.png", "synthetic.mp4"])

    def test_digest_streams_all_bytes(self):
        path = self.root / "large.bin"
        data = b"synthetic-provenance\x00\xff" * 150000
        path.write_bytes(data)
        with patch.object(Path, "read_bytes", side_effect=AssertionError("not streamed")):
            self.assertEqual(media.file_sha256(path), hashlib.sha256(data).hexdigest())


class ValidationTest(SyntheticMediaTest):
    def setUp(self):
        super().setUp()
        self.chapters = [{"name": name, "start": index * 0.5,
                          "end": (index + 1) * 0.5, "verified": True}
                         for index, name in enumerate([
                             "login", "desktop-rain", "launcher", "terminals",
                             "effects", "lock", "final"])]

    def moving(self, name="moving.mp4"):
        return self.clip(name, source="nullsrc=size=160x96:rate=30,"
                         "geq=lum='100+60*sin(X/9+Y/11+N/3)':cb=128:cr=128")

    def validate(self, path, chapters=None, **kwargs):
        options = dict(width=160, height=96, min_duration=3, max_duration=4)
        options.update(kwargs)
        return media.validate_media(path, self.chapters if chapters is None else chapters,
                                    **options)

    def test_valid_clip_returns_measured_visibility_and_distributed_motion(self):
        result = self.validate(self.moving())
        self.assertEqual(result["video"]["frame_count"], 105)
        self.assertEqual(len(result["chapters"]), 7)
        for chapter in result["chapters"]:
            self.assertGreaterEqual(len(chapter["samples"]), 3)
            for sample in chapter["samples"]:
                self.assertGreater(sample["mean_luma"], 20)
                self.assertGreater(sample["nonblack_fraction"], 0.9)
                self.assertGreater(sample["seconds"], chapter["start"])
                self.assertLess(sample["seconds"], chapter["end"])
            if chapter["name"] in ("login", "desktop-rain", "lock"):
                self.assertGreaterEqual(chapter["moving_regions"], 2)
                for region in chapter["regions"]:
                    left, top, right, bottom = region["box"]
                    self.assertTrue(0 < left < right < 160)
                    self.assertTrue(0 < top < bottom < 96)
                    self.assertTrue(right <= 48 or left >= 112)
                    for comparison in region["comparisons"]:
                        self.assertGreater(comparison["mean_abs_delta"], 1)
                        self.assertGreater(comparison["changed_fraction"], 0.1)
        json.dumps(result, allow_nan=False)

    def test_rejects_wrong_codec_pixel_format_geometry_fps_and_duration(self):
        for options in ({"codec": "mpeg4"}, {"pixel_format": "yuv444p"},
                        {"source": "testsrc2=size=128x96:rate=30"},
                        {"source": "testsrc2=size=160x96:rate=24"},
                        {"duration": 2}, {"duration": 5}):
            with self.subTest(options=options):
                path = self.clip(f"wrong-{len(list(self.root.iterdir()))}.mp4", **options)
                with self.assertRaises(media.MediaError):
                    self.validate(path)

    def test_production_duration_bounds_are_not_fixture_bounds(self):
        with self.assertRaisesRegex(media.MediaError, "duration"):
            media.validate_media(self.moving(), self.chapters, 160, 96)

    def test_required_chapters_must_be_unique_ordered_and_verified(self):
        path = self.moving()
        for variant in ("missing", "out-of-order", "false", "truthy", "duplicate"):
            chapters = [dict(chapter) for chapter in self.chapters]
            if variant == "missing":
                chapters.pop(2)
            elif variant == "out-of-order":
                chapters[0]["name"], chapters[1]["name"] = "desktop-rain", "login"
            elif variant in ("false", "truthy"):
                chapters[2]["verified"] = False if variant == "false" else "yes"
            else:
                chapters[2]["name"] = "login"
            with self.subTest(variant=variant), self.assertRaisesRegex(
                    media.MediaError, "chapter|verified"):
                self.validate(path, chapters)

    def test_chapter_timing_rejects_overlap_empty_outside_and_nonfinite(self):
        path = self.moving()
        for index, field, value in ((1, "start", 0.4), (1, "end", 0.5),
                                    (0, "start", -0.6), (6, "end", 4.1),
                                    (2, "end", float("nan")),
                                    (2, "start", float("inf"))):
            chapters = [dict(chapter) for chapter in self.chapters]
            chapters[index][field] = value
            with self.subTest(field=field, value=value), self.assertRaisesRegex(
                    media.MediaError, "timing|overlap|chapter"):
                self.validate(path, chapters)

    def test_small_capture_boundary_skew_is_clamped_to_real_frames(self):
        self.chapters[0]["start"] = -0.2
        self.chapters[-1]["end"] = 3.7
        result = self.validate(self.moving())
        samples = [sample for chapter in result["chapters"] for sample in chapter["samples"]]
        self.assertTrue(all(0 <= sample["seconds"] < 3.5 for sample in samples))

    def test_final_chapter_cannot_borrow_a_frame_before_its_start(self):
        self.chapters[-1]["start"] = 3.49  # After the last frame at 3.466666...s.
        with self.assertRaisesRegex(media.MediaError, "final.*frame|frame.*final"):
            self.validate(self.moving())

    def test_counted_frames_must_cover_container_duration(self):
        source = self.clip(audio=True)
        path = self.root / "padded-audio.mkv"
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(source), "-c:v", "copy",
                        "-af", "apad=whole_dur=5", "-c:a", "aac", "-t", "5", str(path)],
                       check=True, capture_output=True, timeout=30)
        with self.assertRaisesRegex(media.MediaError, "frame count"):
            self.validate(path, max_duration=6)

    def test_later_rain_chapters_must_each_animate(self):
        for index, (name, first, last) in enumerate((("desktop-rain", 15, 29), ("lock", 75, 89))):
            path = self.clip(f"frozen-{index}.mp4", source="nullsrc=size=160x96:rate=30,"
                             f"geq=lum='100+60*sin(X/9+Y/11+if(between(N,{first},{last}),"
                             f"{first},N)/3)':cb=128:cr=128")
            with self.subTest(name=name), self.assertRaisesRegex(media.MediaError, name):
                self.validate(path)

    def test_one_frame_flash_per_chapter_cannot_prove_sustained_rain(self):
        # The old 20/50/80% seeks returned frames 3/8/12 in each 15-frame
        # chapter. A flash only at frame 8 moved both shared-middle comparisons.
        path = self.clip(source="nullsrc=size=160x96:rate=30,"
                         "geq=lum='100+60*eq(mod(N,15),8)':cb=128:cr=128")
        with self.assertRaisesRegex(media.MediaError, "background|motion"):
            self.validate(path)

    def test_interior_black_frame_cannot_be_replaced_by_next_chapters_frame(self):
        self.chapters[2].update(start=1.0, end=1.03)
        path = self.clip(source="nullsrc=size=160x96:rate=30,"
                         "geq=lum='if(eq(N,30),0,100+60*sin(X/9+Y/11+N/3))':cb=128:cr=128")
        with self.assertRaisesRegex(media.MediaError, "launcher.*black|black.*launcher"):
            self.validate(path)

    def test_interior_chapter_with_no_frame_presentation_time_is_rejected(self):
        self.chapters[2].update(start=1.001, end=1.002)
        with self.assertRaisesRegex(media.MediaError, "launcher.*frame|frame.*launcher"):
            self.validate(self.moving())

    def test_short_visible_chapter_reports_its_only_actual_frame(self):
        self.chapters[2].update(start=1.0, end=1.03)
        result = self.validate(self.moving())
        samples = result["chapters"][2]["samples"]
        self.assertEqual(len(samples), 1)
        self.assertEqual(samples[0]["seconds"], 1.0)
        self.assertEqual(samples[0]["frame_index"], 30)
        timeline = result["timeline"]
        self.assertEqual(Fraction(timeline["time_base"]) *
                         (samples[0]["pts"] - timeline["start_pts"]), 1)

    def test_evidence_uses_actual_frame_times_and_independent_short_motion_pairs(self):
        result = self.validate(self.moving())
        for chapter in result["chapters"]:
            for sample in chapter["samples"]:
                self.assertAlmostEqual(sample["seconds"] * 30, round(sample["seconds"] * 30),
                                       places=5)
            for region in chapter["regions"]:
                comparisons = region["comparisons"]
                self.assertGreaterEqual(len(comparisons), 2)
                endpoints = [point for pair in comparisons for point in (pair["start"], pair["end"])]
                self.assertEqual(len(set(endpoints)), len(endpoints), "motion pairs share a frame")
                for pair in comparisons:
                    self.assertGreater(pair["end"], pair["start"])
                    self.assertLessEqual(pair["end"] - pair["start"], 0.2 + 1e-6)

    def test_black_frames_are_rejected_even_in_nonrain_chapters(self):
        path = self.clip(source="nullsrc=size=160x96:rate=30,"
                         "geq=lum='if(between(N,30,44),0,100+60*sin(X/9+Y/11+N/3))':"
                         "cb=128:cr=128")
        with self.assertRaisesRegex(media.MediaError, "launcher.*black|black.*launcher"):
            self.validate(path)
        black = self.clip("black.mp4", source="color=black:size=160x96:rate=30")
        with self.assertRaisesRegex(media.MediaError, "black"):
            self.validate(black)

    def test_static_and_form_clock_or_single_corner_motion_cannot_prove_rain(self):
        # Spatial masks deliberately isolate animation from the background, or
        # to one background corner. Global frame differences must not pass them.
        masks = ["0", "between(X,55,105)*between(Y,20,80)", "lt(Y,8)",
                 "lt(X,48)*lt(Y,45)", "between(X,20,24)*between(Y,20,24)"]
        for index, mask in enumerate(masks):
            path = self.clip(f"localized-{index}.mp4", source=
                             "nullsrc=size=160x96:rate=30,"
                             f"geq=lum='100+({mask})*60*sin(N/3)':cb=128:cr=128")
            with self.subTest(mask=mask), self.assertRaisesRegex(media.MediaError,
                                                                "background|motion"):
                self.validate(path)


class EncodingTest(SyntheticMediaTest):
    def test_inline_is_silent_h264_faststart_with_same_frames_speed_and_scenes(self):
        master = self.clip("master.mp4", audio=True)
        digest = media.file_sha256(master)
        target = self.root / "inline.mp4"
        result = media.encode_inline(master, target, max_bytes=60000)
        self.assertEqual(result["size_bytes"], target.stat().st_size)
        self.assertLessEqual(result["size_bytes"], 60000)
        self.assertEqual(result["max_bytes"], 60000)
        self.assertGreater(result["bitrate_bps"], 0)
        self.assertEqual(result["video"]["codec"], "h264")
        self.assertEqual(result["video"]["pixel_format"], "yuv420p")
        self.assertEqual(result["video"]["audio_streams"], 0)
        self.assertEqual(result["video"]["fps"], 30)
        self.assertEqual(result["video"]["frame_count"], 105)
        self.assertAlmostEqual(result["video"]["duration"], 3.5, places=2)
        self.assertEqual((result["video"]["width"], result["video"]["height"]), (160, 96))
        data = target.read_bytes()
        # Parse real top-level ISO BMFF atoms, not arbitrary substring positions.
        atoms, offset = [], 0
        while offset < len(data):
            size = int.from_bytes(data[offset:offset + 4], "big")
            atoms.append(data[offset + 4:offset + 8])
            self.assertGreaterEqual(size, 8)
            offset += size
        self.assertLess(atoms.index(b"moov"), atoms.index(b"mdat"))
        for seconds in (0.2, 1.2, 2.2, 3.2):
            difference = ImageChops.difference(media.extract_frame(master, seconds),
                                              media.extract_frame(target, seconds))
            self.assertLess(sum(ImageStat.Stat(difference).mean) / 3, 15)
        self.assertEqual(media.file_sha256(master), digest)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["inline.mp4", "master.mp4"])
        json.dumps(result, allow_nan=False)

    def test_encoding_preserves_fractional_recorded_fps(self):
        master = self.clip(source="testsrc2=size=160x96:rate=30000/1001")
        result = media.encode_inline(master, self.root / "inline.mp4", max_bytes=60000)
        self.assertAlmostEqual(result["video"]["fps"], 30000 / 1001, places=5)
        self.assertEqual(result["video"]["frame_count"], 105)

    def test_odd_source_dimensions_are_rounded_down_never_upscaled(self):
        master = self.clip("odd.mkv", source="testsrc=size=161x97:rate=30",
                           codec="ffv1", pixel_format="yuv444p")
        result = media.encode_inline(master, self.root / "inline.mp4", max_bytes=60000)
        self.assertEqual((result["video"]["width"], result["video"]["height"]), (160, 96))
        self.assertEqual(result["video"]["frame_count"], 105)

    def test_impossible_and_invalid_budgets_preserve_existing_target(self):
        master = self.clip()
        target = self.root / "inline.mp4"
        target.write_bytes(b"previous complete output")
        for budget in (1, 100, 0, -1, float("nan")):
            with self.subTest(budget=budget), self.assertRaises((media.MediaError, ValueError)):
                media.encode_inline(master, target, max_bytes=budget)
            self.assertEqual(target.read_bytes(), b"previous complete output")
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["inline.mp4", "synthetic.mp4"])

    def test_source_aliases_cannot_be_overwritten(self):
        master = self.clip()
        digest = media.file_sha256(master)
        hardlink = self.root / "hardlink.mp4"
        hardlink.hardlink_to(master)
        symlink = self.root / "symlink.mp4"
        symlink.symlink_to(master)
        for target in (master, hardlink, symlink):
            with self.subTest(target=target.name), self.assertRaises(ValueError):
                media.encode_inline(master, target)
        self.assertEqual(media.file_sha256(master), digest)

    def test_oversized_encoded_result_is_not_installed(self):
        master = self.clip()
        target = self.root / "inline.mp4"
        target.write_bytes(b"previous complete output")
        inspect = media.inspect_video

        def padded_output(path):
            info = inspect(path)
            if Path(path).resolve() != master.resolve():
                # Real encoded MP4 plus harmless trailing bytes models bitrate
                # overshoot without replacing encoding/decoding with a mock.
                with Path(path).open("ab") as stream:
                    stream.write(b"\x00" * 60000)
            return info

        with patch.object(media, "inspect_video", side_effect=padded_output):
            with self.assertRaisesRegex(media.MediaError, "budget|size"):
                media.encode_inline(master, target, max_bytes=60000)
        self.assertEqual(target.read_bytes(), b"previous complete output")
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["inline.mp4", "synthetic.mp4"])

    def test_second_pass_failure_preserves_diagnostics_and_cleans_scoped_stats(self):
        master = self.clip()
        target = self.root / "inline.mp4"
        unrelated = self.root / "ffmpeg2pass-0.log"
        unrelated.write_text("unrelated process statistics")
        run = subprocess.run
        passes = 0

        def fail_second_pass(command, **kwargs):
            nonlocal passes
            if command[0] == "ffmpeg":
                passes += 1
                if passes == 2:
                    return run([sys.executable, "-c",
                                "import sys; print('synthetic encoder disk failure', "
                                "file=sys.stderr); sys.exit(13)"], **kwargs)
            return run(command, **kwargs)

        with patch.object(media.subprocess, "run", side_effect=fail_second_pass):
            with self.assertRaisesRegex(media.MediaError, "(?s)13.*synthetic encoder disk failure"):
                media.encode_inline(master, target, max_bytes=60000)
        self.assertFalse(target.exists())
        self.assertEqual(unrelated.read_text(), "unrelated process statistics")
        self.assertEqual(sorted(p.name for p in self.root.iterdir()),
                         ["ffmpeg2pass-0.log", "synthetic.mp4"])

    def test_real_process_timeout_keeps_stderr_diagnostics(self):
        with self.assertRaisesRegex(media.MediaError, "(?s)Timed out.*synthetic timeout detail"):
            media._run([sys.executable, "-c", "import sys,time; "
                        "print('synthetic timeout detail',file=sys.stderr,flush=True); "
                        "time.sleep(10)"], timeout=0.2)


if __name__ == "__main__":
    print("SYNTHETIC FFmpeg unit fixtures only; not real showcase evidence.", flush=True)
    unittest.main()
