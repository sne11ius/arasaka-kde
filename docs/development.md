# Development

[Docs](README.md) / Development

## Source map

| Directory | Responsibility |
| --- | --- |
| `assets/` | Original branding, wallpaper SVGs, shader adaptation patches |
| `bin/` | Scoped build, installation, and configuration commands |
| `lib/` | Topology helpers, Polonium adaptation, common shell utilities |
| `manifest/components.tsv` | Immutable upstream resources with SHA-256 hashes |
| `native/rain/` | Droplet simulation, optical-field rendering, passive input |
| `native/login/` | Screen-local PLM pointer bridge |
| `native/window-policy/` | Native KWin helper for managed tiling |
| `plasma/` | Launcher, scripting templates, shared wallpaper defaults |
| `packaging/` | PLM Debian packaging and frontend adaptation |
| `systemd/` | User-session display reconciliation units |
| `theme/` | Plasma, KWin, application, shell, and retained SDDM styling |
| `tests/` | Fixture, controller, native, and opt-in session tests |
| `.github/` | Public checks, test container, and contribution templates |

## Repository tests

```sh
make test
```

The runner discovers `*_test.sh` and `*_test.py`. It includes the real C++ physics
build through the Python wrapper, the adapted Polonium controller under Node.js,
and real SVG rendering. Install Python 3.12+, Pillow, Bash, Node.js, CMake, a C++20
compiler, Make or Ninja, `curl`, `patch`, `jq`, `rsvg-convert`, KDE KConfig tools,
and the artwork's **Rajdhani SemiBold** font. Font fallback can change the rendered
contrast samples; the CI image supplies the pinned font and its license.
Some suites skip when required KDE/native tools are missing; public CI installs
them explicitly. Tests use temporary homes and stub session tools.

Some fixture suites expect `/tmp/opencode` to exist:

```sh
mkdir -p /tmp/opencode
```

### Use the same container as CI

With Docker installed and usable by your normal user:

```sh
docker build --tag arasaka-ci .github/ci
docker run --rm --user "$(id -u):$(id -g)" \
  --volume "$PWD:/workspace" arasaka-ci make test
```

The image pins Debian 13's base digest and supplies the test tools, including Qt 6
and software OpenGL. Tests run unprivileged. It mounts the checkout, not your live
Plasma configuration or session bus. Build outputs stay under ignored `build/`.

## Test matrix

| Check | What it proves | Where it runs |
| --- | --- | --- |
| `make test` | Repository fixtures, real helper/controller behavior, artwork, physics | Local / public Actions |
| `make test-native` | C++ physics plus Qt/OpenGL field/input and cross-process pointer delivery | CI container / prepared Linux host |
| `make coverage` | Measured execution of Python helpers and C++ rain physics | CI container; reports uploaded to Codecov |
| `make lint-docs` | Public Markdown formatting | Local / public Actions |
| Lychee offline | Relative files and Markdown fragments | Local / public Actions |
| Lychee online | Public external links, with documented dynamic-service exclusions | Local / scheduled Actions |
| CodeQL | Python and JavaScript/TypeScript static analysis | Public Actions |
| OpenSSF Scorecard | Repository security practices | Public Actions → public Scorecard API |
| Host QML / full shader smoke | Actual wallpaper package and renderer integration | Opt-in, prepared KDE environment |
| Launcher / virtual KWin smoke | Real native UI and compositor interactions in isolation | Opt-in, prepared KDE environment |
| Normal lock, login, hotplug, suspend | Actual host lifecycle and physical input | Manual observation |

A native build badge covers the tested native rain components, not a complete
PLM package build or successful authentication. [Coverage scope →](automation.md#coverage-scope)

## Native and live integration

### Standalone rain and input

In the CI container, replace `make test` in the Docker command with:

```sh
make test-native
```

The graphics checks use Mesa software OpenGL in Xvfb, and the login-pointer test
uses a private D-Bus session with separate sender/receiver processes. They do not
open or alter your live greeter. Hardware-driver coverage needs a separate run.

### Full wallpaper host

For a retained patched upstream source tree, run from the repository root on a
host with the [shader build prerequisites](installation.md#shader-build), Qt Quick
Test, and a working OpenGL window system:

```sh
ARCHIVE=$(./bin/fetch-components shader-wallpaper)
UPSTREAM=$(mktemp -d)
BUILD=$(mktemp -d)
tar -xzf "$ARCHIVE" --strip-components=1 -C "$UPSTREAM"
patch --batch --forward --fuzz=0 -p1 -d "$UPSTREAM" \
  -i "$PWD/assets/wallpapers/shaders/interactive-rain-host.patch"
mkdir -p "$UPSTREAM/src/rain"
cp native/rain/{dropletsimulation,rainfieldrenderer,raininput}.{h,cpp} "$UPSTREAM/src/rain/"
cmake -S "$UPSTREAM" -B "$BUILD" -DCMAKE_BUILD_TYPE=Release
cmake --build "$BUILD" --parallel 2
cp "$UPSTREAM/package/contents/ui/Shaders/Heartfelt.frag" "$UPSTREAM/Heartfelt_No_Heart.frag"
patch --batch --forward --fuzz=0 -p1 -d "$UPSTREAM" \
  -i "$PWD/assets/wallpapers/shaders/heartfelt-no-heart.patch"
cp "$UPSTREAM/Heartfelt_No_Heart.frag" "$UPSTREAM/Interactive_Rain.frag"
patch --batch --forward --fuzz=0 -p1 -d "$UPSTREAM" \
  -i "$PWD/assets/wallpapers/shaders/interactive-rain.patch"
cmake -S tests/native_rain -B build/rain-host-tests -DRAIN_UPSTREAM_SOURCE="$UPSTREAM"
cmake --build build/rain-host-tests --parallel 2
ctest --test-dir build/rain-host-tests --output-on-failure
python3 tests/shader_smoke.py --rain-check --package "$UPSTREAM/package" \
  --shader "$UPSTREAM/Interactive_Rain.frag" --texture assets/wallpapers/mikoshi-16x9.svg \
  --screenshot /tmp/interactive-rain.png
```

This sequence uses Bash brace expansion. Temporary source/build directories avoid
live installation. `--rain-check` covers rendering, pause/resume, selection failure,
and input roles. Optional `--previous-native PATH` checks new host QML against a
copied previous module. `--blur-check` instead examines filtering and lightning;
it cannot be combined with `--rain-check`.

For gallery round-trips, supply a staged/installed package and its external shaders:

```sh
node tests/shader_gallery_smoke.js "$PACKAGE" "$NOHEART_SHADER" "$RAIN_SHADER"
```

Those variables must point to your actual artifacts. The check exercises the real
gallery selection function without calling Plasma or changing settings.

### Launcher and window policy

Inside a working Wayland environment:

```sh
python3 tests/launcher_smoke.py
```

For the window-policy checks, choose an empty/nonexistent staging path:

```sh
./bin/apply-window-policy --stage-only /tmp/opencode/policy-package
python3 tests/window_policy_smoke.py /tmp/opencode/policy-package
```

The suite starts a private virtual KWin session, disposable application windows,
fixed-size dialogs, a credential-free pinentry confirmation, and a disposable
Konsole. It checks actual tile membership, decorations, drag/drop, output
destruction/recreation, exception recovery, and the PID-scoped floating exception.

## Public-docs checks

```sh
npm --prefix .github/ci ci
make lint-docs
```

See [automation](automation.md#run-the-checks-locally) for local link checking,
workflow validation, coverage, and hosted-service activation.
