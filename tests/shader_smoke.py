#!/usr/bin/env python3
"""Exercise an installed or staged native shader renderer in an isolated Qt window."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--shader", type=Path, required=True)
    parser.add_argument("--texture", type=Path, required=True)
    parser.add_argument("--screenshot", type=Path, required=True)
    parser.add_argument("--blur-check", action="store_true", help="test Heartfelt's blur, lightning and fixed animation times")
    args = parser.parse_args()
    native = args.package.resolve() / "contents/ui/shaderwallpaper"
    for path in (native / "libshaderwallpaperplugin.so", args.shader, args.texture):
        if not path.is_file():
            parser.error(f"required file missing: {path}")
    with tempfile.TemporaryDirectory(prefix="arasaka-shader-smoke-") as directory:
        stage = Path(directory)
        # A nonempty sandbox library prevents fallback to the live shader index.
        library = stage / "data/plasma/wallpapers/online.knowmad.shaderwallpaper/contents/ui/Shaders"
        library.mkdir(parents=True)
        (library / "Default.frag").write_text("void mainImage(out vec4 c, in vec2 p) { c = vec4(1); }\n")
        replacements = {
            "__PLUGIN_URL__": native.as_uri(),
            "__SHADER_URL__": json.dumps(args.shader.resolve().as_uri()),
            "__TEXTURE_URL__": json.dumps(args.texture.resolve().as_uri()),
            "__SCREENSHOT__": json.dumps(str(args.screenshot.resolve())),
        }
        if args.blur_check:
            edge = stage / "edge.svg"
            edge.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256">'
                            '<path fill="black" d="M0 0h256v256H0z"/>'
                            '<path fill="white" d="M128 0h128v256H128z"/></svg>')
            subprocess.run(["rsvg-convert", str(edge), "-o", str(stage / "edge.png")], check=True)
            source = args.shader.read_text()
            sample = re.search(r"^\s*vec3 col = (.+);", source, re.MULTILINE)
            if not sample:
                parser.error("cannot locate Heartfelt's background sampling expression")
            lightning = re.search(r"float lightning =.*?(?=\n\s*col \*=)", source, re.DOTALL)
            if not lightning:
                parser.error("cannot locate Heartfelt's lightning calculation")
            # Use the actual sampling expression without rain/lighting obscuring the edge response.
            code = "#define mainImage rainImage\n#define iTime (iMouse.x)\n" + source
            code += "\n#undef mainImage\n#undef iTime\nvoid mainImage(out vec4 color, in vec2 p) {\n"
            code += "if (iMouse.y > 0.) { rainImage(color, p); return; }\n"
            # Red is actual lightning, green the original, blue identifies retained cycles.
            code += "if (iMouse.y < 0.) { float t = p.x / iResolution.x * 50.2654824574;\n"
            code += lightning[0] + "\n"
            code += "float original = sin(t*sin(t*10.))*pow(max(0.,sin(t+sin(t))),10.);\n"
            code += "color = vec4(.5+.5*lightning, .5+.5*original, 1.-mod(floor(t/6.28318530718),2.), 1.); return; }\n"
            code += "vec2 UV = p / iResolution.xy, n = vec2(0); float focus = 6.;\n"
            code += "color = vec4(" + sample[1] + ", 1.);\n}\n"
            replacements.update(__SHADER_CODE__=json.dumps(code),
                                __EDGE_URL__=json.dumps((stage / "edge.png").as_uri()))
        qml = Path(__file__).with_name("blur_checks.qml" if args.blur_check else "shader_checks.qml").read_text()
        for key, value in replacements.items():
            qml = qml.replace(key, value)
        test = stage / "tst_shader.qml"
        test.write_text(qml)
        env = os.environ.copy()
        env.pop("QT_QUICK_BACKEND", None)
        env.update(QSG_RHI_BACKEND="opengl", QSG_RENDER_LOOP="basic", QML_DISABLE_DISK_CACHE="1",
                   XDG_DATA_HOME=str(stage / "data"), XDG_CONFIG_HOME=str(stage / "config"),
                   XDG_CACHE_HOME=str(stage / "cache"))
        return subprocess.run(["/usr/lib/qt6/bin/qmltestrunner", "-input", str(test)],
                              env=env, timeout=60).returncode


if __name__ == "__main__":
    raise SystemExit(main())
