import io
from pathlib import Path
import subprocess
import unittest

from PIL import Image, ImageFilter


ROOT = Path(__file__).resolve().parents[1]


class WallpaperArtworkTests(unittest.TestCase):
    def test_tiling_gaps_reveal_color_instead_of_window_darkness(self):
        # Relative luminance against the theme's #11151A window surface.
        linear = [(value / 255 / 12.92 if value <= 10 else
                   ((value / 255 + 0.055) / 1.055) ** 2.4) for value in range(256)]
        window = sum(weight * linear[value] for weight, value in
                     zip((0.2126, 0.7152, 0.0722), (17, 21, 26)))
        for aspect, height in (("16x9", 270), ("16x10", 300)):
            png = subprocess.run(
                ["rsvg-convert", "--width", "480", "--height", str(height),
                 str(ROOT / f"assets/wallpapers/mikoshi-{aspect}.svg")],
                check=True, capture_output=True).stdout
            # Broad illumination must survive blur; isolated neon lines are not enough.
            image = Image.open(io.BytesIO(png)).convert("RGB").filter(ImageFilter.GaussianBlur(3))
            for axis in ("vertical", "horizontal"):
                for position in (0.01, 0.25, 0.5, 0.75, 0.99):
                    with self.subTest(aspect=aspect, axis=axis, position=position):
                        length = height if axis == "vertical" else 480
                        visible = 0
                        for along in range(length):
                            xy = ((int(position * 480), along) if axis == "vertical" else
                                  (along, int(position * height)))
                            pixel = image.getpixel(xy)
                            luminance = sum(weight * linear[value] for weight, value in
                                            zip((0.2126, 0.7152, 0.0722), pixel))
                            contrast = (luminance + 0.05) / (window + 0.05)
                            if contrast >= 1.5 and max(pixel) - min(pixel) >= 30:
                                visible += 1
                        self.assertGreaterEqual(visible / length, 0.8,
                                                "At least 80% of each gap must reveal contrasting color")


if __name__ == "__main__":
    unittest.main()
