# Arasaka KDE Rice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build, apply, verify, and safely roll back a maximum-spectacle Arasaka desktop for KDE Plasma 6.7.2.

**Architecture:** A local Git repository owns declarative theme assets and narrow deployment scripts, never a copy of the whole home configuration. Python handles JSON topology decisions; strict Bash handles staging, snapshots, deployment, diagnostics, and rollback; Plasma JavaScript creates idempotent role-based panels. All external components are pinned and verified before installation.

**Tech Stack:** Bash, Python 3 standard library, Plasma 6 JavaScript API, KConfig tools, systemd user units, SVG, FFmpeg, Kvantum, Klassy, KWin/Wayland.

**Spec:** `docs/superpowers/specs/2026-09-04-arasaka-kde-rice-design.md`

## Global Constraints

- Target TUXEDO OS with KDE Plasma 6.7.2 on Wayland.
- Keep exactly one virtual desktop and no Activities additions.
- Any enabled external output is primary; use the internal output only when no external output exists.
- Never change output mode, scale, refresh, transform, position, brightness, HDR, VRR, or color profile.
- Never move, delete, rename, or commit desktop files, secrets, browser data, or unrelated configuration.
- Every changed live file must be inventoried in a timestamped snapshot before replacement.
- Every downloaded artifact must be pinned by immutable URL and SHA-256.
- Do not execute upstream installation scripts against the live home directory.
- Preserve the Konsole `Quake.profile` workflow and bottom tab placement.
- Keep a functional native-Blur and static-wallpaper fallback.

---

### Task 1: Project Foundation And Test Harness

**Files:**
- Create: `README.md`
- Create: `Makefile`
- Create: `.gitignore`
- Create: `lib/common.sh`
- Create: `tests/testlib.sh`
- Create: `tests/foundation_test.sh`
- Create: `tests/run`

**Interfaces:**
- Produces: `project_root()`, `state_root()`, `cache_root()`, `snapshot_root()`, `log()`, `die()`, `require_command()`, and `atomic_copy(source, target)` for all later Bash commands.

- [ ] **Step 1: Write the failing foundation test**

Create `tests/testlib.sh` with assertion helpers and temporary-home setup. Create `tests/foundation_test.sh` that sources `lib/common.sh`, asserts `project_root` equals the repository root, asserts XDG-derived state/cache paths under a temporary `HOME`, and verifies `atomic_copy` replaces a target without leaving a temporary file.

- [ ] **Step 2: Run the test and verify the missing library fails**

Run: `bash tests/foundation_test.sh`

Expected: non-zero exit because `lib/common.sh` does not exist.

- [ ] **Step 3: Implement the shared shell library and project entry points**

Use strict mode in every executable. `state_root` returns `${XDG_STATE_HOME:-$HOME/.local/state}/arasaka-kde`; `cache_root` returns `${XDG_CACHE_HOME:-$HOME/.cache}/arasaka-kde`; `snapshot_root` appends `/snapshots`; `atomic_copy` copies to a sibling temporary path, preserves mode, and renames it into place. `Makefile` exposes `test`, `doctor`, `dry-run`, `apply`, and `rollback` targets. `.gitignore` excludes `.cache/`, `build/`, generated video, screenshots, and local snapshots.

- [ ] **Step 4: Run the foundation test**

Run: `make test`

Expected: `foundation_test: PASS` and exit 0.

- [ ] **Step 5: Commit the foundation**

Run: `git add README.md Makefile .gitignore lib/common.sh tests && git commit -m "build: add project foundation"`

### Task 2: Pinned Component Manifest And Safe Fetcher

**Files:**
- Create: `manifest/components.tsv`
- Create: `bin/fetch-components`
- Create: `tests/fetch_components_test.sh`
- Create: `tests/fixtures/component.txt`

**Interfaces:**
- Consumes: `cache_root()`, `log()`, `die()`, `atomic_copy()` from `lib/common.sh`.
- Produces: `fetch_component(name)` and a verified cache at `$(cache_root)/downloads`.

- [ ] **Step 1: Write fetcher tests**

Test a fixture manifest containing a `file://` URL. Assert a valid SHA-256 is accepted, a mismatched hash is rejected, a filename containing `../` is rejected, and a second fetch reuses the verified cache.

- [ ] **Step 2: Run the fetcher test and verify failure**

Run: `bash tests/fetch_components_test.sh`

Expected: non-zero exit because `bin/fetch-components` is absent.

- [ ] **Step 3: Implement the manifest and fetcher**

Use tab-separated fields `name`, `version`, `url`, `sha256`, and `filename`. Pin these release artifacts:

```text
panel-colorizer  v8.0.0  plasmoid-panel-colorizer-v8.0.0.plasmoid  93f737af4d6291f2c84800090258c77511270817d7a5ecc56de45a6af966b2ee
polonium         v1.2.1  polonium.kwinscript                         1f7cd126d4341761fde0e0d82f277118030dc372b734825d6b1edf3d41b6bd85
smart-video      v2.14.1 plasma-smart-video-wallpaper-reborn.tar.gz 7ac3c392942f40013622880a2ac1333734e1d63ac12cc0a73e54753d412789ca
application-bar  v0.10.0 application-title-bar.plasmoid             fb90a257ba9cce41deea27aef6f41a650a3a788af5542967d1d2c072c8ceac63
kurve            v3.6.0  Kurve-v3.6.0.plasmoid                      845b6823e2e2e91e82769e70c7a349fbc8ef7f90e360e0ad99884ee958ec9b03
```

Fetch Klassy v6.7.2 and Better Blur DX v2.5.1 source archives once, calculate their SHA-256, then record those immutable digests before any build step. The fetcher must use `curl --fail --location --proto '=https'`, reject unsafe filenames, write to a temporary file, verify with `sha256sum --check`, and rename only after verification.

- [ ] **Step 4: Run fetcher tests**

Run: `make test`

Expected: foundation and fetcher tests pass.

- [ ] **Step 5: Commit the verified fetch path**

Run: `git add manifest bin/fetch-components tests && git commit -m "feat: add verified component fetcher"`

### Task 3: Authored Theme Assets

**Files:**
- Create: `theme/color-schemes/Arasaka.colors`
- Create: `theme/konsole/Arasaka.colorscheme`
- Create: `theme/alacritty/arasaka.toml`
- Create: `theme/kvantum/Arasaka/Arasaka.kvconfig`
- Create: `theme/kvantum/Arasaka/Arasaka.svg`
- Create: `theme/plasma/desktoptheme/com.arasaka.mikoshi/metadata.json`
- Create: `theme/plasma/desktoptheme/com.arasaka.mikoshi/colors`
- Create: `theme/gtk/gtk.css`
- Create: `theme/firefox/userChrome.css`
- Create: `theme/zsh/arasaka-p10k.zsh`
- Create: `theme/icons/arasaka/index.theme`
- Create: `tests/theme_assets_test.py`

**Interfaces:**
- Produces: installable assets rooted at `theme/` using palette constants from the specification.

- [ ] **Step 1: Write structural theme tests**

Parse KDE INI files with `configparser`, JSON with `json`, SVG with `xml.etree.ElementTree`, and CSS through balanced-brace checks. Assert all seven palette colors appear in the expected files, `Arasaka.colors` defines every KDE color group, terminal background is `#07090C`, active decoration is `#E60012`, and no blue-purple accent literals are present.

- [ ] **Step 2: Run tests and verify missing assets fail**

Run: `python3 tests/theme_assets_test.py`

Expected: failure naming the first missing theme file.

- [ ] **Step 3: Create the KDE, terminal, and application themes**

Implement a complete KDE color scheme with dark views/windows, cold-white text, muted disabled text, and crimson focus/selection. Build a compact Kvantum theme with 2 px corner radius, thin frames, flat controls, and red active/hover states. The Plasma theme inherits Breeze Dark for unmodified assets and supplies its own color file and panel background metadata. GTK and Firefox CSS use only scoped selectors and do not hide navigation, security indicators, or browser controls.

- [ ] **Step 4: Create icon inheritance and prompt palette**

The Arasaka icon theme inherits `breeze-dark,breeze` and supplies only project-owned launcher/status overrides. The Powerlevel10k preset changes colors and separators without replacing `.p10k.zsh`; the apply step sources it from the existing config.

- [ ] **Step 5: Run theme tests**

Run: `make test`

Expected: all theme files parse and palette assertions pass.

- [ ] **Step 6: Commit the authored theme**

Run: `git add theme tests/theme_assets_test.py && git commit -m "feat: add Arasaka visual theme"`

### Task 4: Mikoshi Artwork And Sound

**Files:**
- Create: `assets/wallpapers/mikoshi-master.svg`
- Create: `assets/wallpapers/mikoshi-16x9.svg`
- Create: `assets/wallpapers/mikoshi-16x10.svg`
- Create: `assets/sounds/freedesktop/stereo/README.md`
- Create: `scripts/render-assets`
- Create: `tests/render_assets_test.sh`
- Create: `ATTRIBUTION.md`

**Interfaces:**
- Produces: `build/wallpapers/mikoshi-3840x2160.png`, `build/wallpapers/mikoshi-2560x1600.png`, `build/wallpapers/mikoshi-loop.mp4`, and a freedesktop-compatible sound directory.

- [ ] **Step 1: Write render validation tests**

Assert the source SVGs parse, contain 16:9 and 16:10 view boxes, keep the emblem in the central safe area, and contain only the approved palette. When rendering tools exist, assert exact PNG dimensions with `identify` and assert a silent H.264 loop with `ffprobe`.

- [ ] **Step 2: Run tests and verify missing artwork fails**

Run: `bash tests/render_assets_test.sh`

Expected: non-zero exit because source artwork is absent.

- [ ] **Step 3: Author the Mikoshi composition**

Create original SVG geometry: black architectural field, red central data monolith, white corporate grid, Japanese labels, scanline mask, and an Arasaka-inspired three-part sakura emblem. Keep text converted or rendered with the declared fonts and avoid embedding unlicensed raster art.

- [ ] **Step 4: Implement deterministic rendering**

Use `rsvg-convert` for exact static dimensions. Use FFmpeg to animate a 12-second seamless slow red pulse and vertical scan, encode H.264 yuv420p with no audio stream, and place generated files only under ignored `build/`.

- [ ] **Step 5: Generate a short original sound set**

Use FFmpeg sine/noise sources and envelopes to create startup, notification, warning, and logout Ogg files. Keep each under two seconds except startup, and normalize below clipping. Record that all authored assets are project-original in `ATTRIBUTION.md`.

- [ ] **Step 6: Run render tests**

Run: `make test`

Expected: source validation passes; binary render checks pass when dependencies are installed.

- [ ] **Step 7: Commit source assets**

Run: `git add assets scripts/render-assets tests/render_assets_test.sh ATTRIBUTION.md && git commit -m "feat: add Mikoshi artwork sources"`

### Task 5: Display Topology Decision Engine

**Files:**
- Create: `lib/arasaka_topology.py`
- Create: `bin/reconcile-displays`
- Create: `systemd/arasaka-display-reconcile.service`
- Create: `systemd/arasaka-display-reconcile.path`
- Create: `tests/fixtures/topology/internal-only.json`
- Create: `tests/fixtures/topology/internal-external.json`
- Create: `tests/fixtures/topology/external-only.json`
- Create: `tests/fixtures/topology/multiple-external.json`
- Create: `tests/topology_test.py`

**Interfaces:**
- Produces: `classify_output(connector: str) -> Literal["internal", "external"]`, `choose_primary(outputs: list[dict]) -> str`, and `priority_changes(outputs: list[dict]) -> list[tuple[str, int]]`.
- Produces: `bin/reconcile-displays --json FILE --dry-run` for fixture and live use.

- [ ] **Step 1: Capture and sanitize the live KScreen JSON shape**

Run `kscreen-doctor -j`, retain only structural fields needed by tests, and ensure EDID/model/serial data does not enter fixtures.

- [ ] **Step 2: Write topology unit tests**

Assert `eDP`, `LVDS`, and `DSI` prefixes classify as internal. Assert one external wins over internal, external-only selects the current external, multiple external outputs preserve their relative priority, disabled outputs are ignored, and generated changes alter priority only.

- [ ] **Step 3: Run tests and verify missing engine fails**

Run: `python3 tests/topology_test.py`

Expected: import failure for `lib.arasaka_topology`.

- [ ] **Step 4: Implement the pure decision engine**

Do not shell out from Python. Accept normalized dictionaries, return deterministic decisions, reject a topology with no enabled output, and never include mode/scale/position fields in returned mutations.

- [ ] **Step 5: Implement the live wrapper and user units**

`bin/reconcile-displays` obtains JSON from `kscreen-doctor -j`, invokes the pure engine, prints decisions in dry-run mode, and otherwise runs only `kscreen-doctor output.<id>.priority.<n>` operations. The path unit watches `%h/.config/kwinoutputconfig.json`; the service coalesces events and calls the idempotent command.

- [ ] **Step 6: Run topology tests and live dry-run**

Run: `python3 tests/topology_test.py && bin/reconcile-displays --dry-run`

Expected: tests pass; live output identifies the enabled external as desired primary and prints no mode, scale, refresh, or position operation.

- [ ] **Step 7: Commit topology support**

Run: `git add lib/arasaka_topology.py bin/reconcile-displays systemd tests && git commit -m "feat: add external-first display reconciliation"`

### Task 6: Idempotent Plasma Panels And KWin Policy

**Files:**
- Create: `plasma/layout.js`
- Create: `plasma/query-layout.js`
- Create: `kwin/kwinrc.ini`
- Create: `kwin/poloniumrc.ini`
- Create: `tests/plasma_layout_test.py`

**Interfaces:**
- Consumes: primary and internal screen indexes passed as JSON to `plasma/layout.js`.
- Produces: exactly two tagged primary panels and zero or one tagged telemetry panel; one virtual desktop; Polonium and KWin settings.

- [ ] **Step 1: Probe Plasma 6.7 scripting properties without mutation**

Use `qdbus6 org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript` with `query-layout.js` to record available screen and panel properties. Adapt only property names proven by this probe.

- [ ] **Step 2: Write static and model tests**

Assert the layout source removes only panels tagged `ARASAKA_PRIMARY_TOP`, `ARASAKA_PRIMARY_DOCK`, or `ARASAKA_TELEMETRY`; creates no pager; uses only one system tray; includes Application Title Bar, Panel Colorizer, Icons-Only Task Manager, System Monitor sensors, and Kurve in their specified roles; and converges to the same panel model on a second run.

- [ ] **Step 3: Run tests and verify missing layout fails**

Run: `python3 tests/plasma_layout_test.py`

Expected: failure because `plasma/layout.js` is absent.

- [ ] **Step 4: Implement primary panels**

Create a 38 px full-width top strip with launcher, active application, media, sensors, flexible spacer, system tray, and clock. Create a 52 px centered floating dock with icons-only tasks. Configure Panel Colorizer with dark angular blocks, cold-white foregrounds, and crimson active edges.

- [ ] **Step 5: Implement telemetry role and single-screen convergence**

When a separate internal screen exists, create a slim telemetry panel containing CPU/GPU/network/battery sensors and Kurve but no launcher, task manager, tray, or clock. When only one screen exists, remove that role and place the two primary panels on the available screen.

- [ ] **Step 6: Implement KWin and Polonium policy**

Set one virtual desktop, 6 px gaps, center-master external default, master-stack internal default, floating rules for dialogs and utility windows, Magic Lamp minimization, Overview/Present Windows, and native Blur as the initial safe effect. Do not enable Cube, Wobbly Windows, or Burn My Windows.

- [ ] **Step 7: Run layout tests**

Run: `make test`

Expected: panel model and policy tests pass.

- [ ] **Step 8: Commit desktop policy**

Run: `git add plasma kwin tests/plasma_layout_test.py && git commit -m "feat: add adaptive Plasma command center"`

### Task 7: Snapshot, Apply, And Rollback Pipeline

**Files:**
- Create: `lib/inventory.tsv`
- Create: `bin/snapshot`
- Create: `bin/apply`
- Create: `bin/rollback`
- Create: `tests/apply_rollback_test.sh`

**Interfaces:**
- Consumes: assets from Tasks 3-4, shared functions from Task 1, and panel/topology commands from Tasks 5-6.
- Produces: timestamped snapshots under `$(snapshot_root)`, `bin/apply --dry-run`, live apply, and selected-snapshot rollback.

- [ ] **Step 1: Write sandboxed apply/rollback tests**

Set temporary `HOME`, XDG directories, and stub KDE commands. Assert dry-run changes nothing; apply snapshots pre-existing files, installs project files, preserves unrelated files, appends an idempotent Powerlevel10k source line, and a second apply does not duplicate it; rollback restores exact hashes and removes only project-owned new files.

- [ ] **Step 2: Run tests and verify missing commands fail**

Run: `bash tests/apply_rollback_test.sh`

Expected: non-zero exit because `bin/apply` and `bin/rollback` are absent.

- [ ] **Step 3: Define the explicit inventory**

List every target path and ownership mode. Include KDE color/theme paths, Kvantum, Konsole, Alacritty import, GTK CSS imports, Firefox profile chrome discovered at runtime, icons, sounds, wallpapers, Plasma/KWin scoped settings, and systemd user units. Exclude full-directory copying and unrelated configuration keys.

- [ ] **Step 4: Implement snapshot and rollback**

Snapshots contain `manifest.tsv`, copies of files that existed, and markers for targets that did not exist. Record SHA-256, mode, and target path. Rollback validates the manifest, restores existing files atomically, removes only targets marked newly created, reloads user units, and reconfigures KWin/Plasma.

- [ ] **Step 5: Implement dry-run and apply**

Validate first, render into staging, snapshot, deploy user assets, apply KConfig values, install applets with `kpackagetool6`, run Plasma layout scripting, install topology units, and reload Plasma. Keep SDDM as a separately printed privileged phase. Trap pre-switch failures and invoke rollback automatically.

- [ ] **Step 6: Run sandbox tests**

Run: `make test`

Expected: apply and rollback tests pass with exact restoration.

- [ ] **Step 7: Commit deployment pipeline**

Run: `git add lib/inventory.tsv bin tests/apply_rollback_test.sh && git commit -m "feat: add reversible theme deployment"`

### Task 8: Dependency Installer And Diagnostics

**Files:**
- Create: `bin/install`
- Create: `bin/doctor`
- Create: `tests/doctor_test.sh`
- Create: `docs/recovery.md`

**Interfaces:**
- Consumes: component manifest, fetcher, rendering command, inventory, and live KDE commands.
- Produces: a dependency/component installer and machine-readable `bin/doctor --json` plus readable default output.

- [ ] **Step 1: Write diagnostic tests with command stubs**

Assert healthy stubs return exit 0 and JSON status `ok`. Assert X11, wrong Plasma major, missing codec, mismatched KWin/Better Blur ABI, failed wallpaper probe, and missing applet each return non-zero with a specific remediation message. Assert degraded native-Blur/static-wallpaper fallback is distinguishable from fatal status.

- [ ] **Step 2: Run tests and verify missing doctor fails**

Run: `bash tests/doctor_test.sh`

Expected: non-zero exit because `bin/doctor` is absent.

- [ ] **Step 3: Implement distro dependency resolution**

Map TUXEDO/Debian package names for build tools, Qt/KF6 development libraries, Kvantum, FFmpeg, librsvg, CAVA, WebSockets, and fonts. Print the exact package command before using `sudo`. Install user-level plasmoids from verified files with `kpackagetool6`; extract source archives into cache; build Klassy and Better Blur DX in isolated build directories; never invoke their installer scripts.

- [ ] **Step 4: Implement doctor and fallbacks**

Check commands, Wayland, Plasma/KWin versions, manifest hashes, installed packages, applet/effect registration, generated assets, media codecs, user units, panel count, virtual desktop count, current primary-output decision, and live Plasma/KWin logs. Provide commands to switch video to static and Better Blur DX to native Blur.

- [ ] **Step 5: Document TTY and graphical recovery**

Document stopping video wallpaper, disabling the topology units, restoring the newest snapshot, restarting Plasma, and recovering from a KWin effect mismatch after upgrades.

- [ ] **Step 6: Run diagnostics tests**

Run: `make test`

Expected: all healthy, degraded, and fatal fixture cases pass.

- [ ] **Step 7: Commit installer and diagnostics**

Run: `git add bin/install bin/doctor tests/doctor_test.sh docs/recovery.md && git commit -m "feat: add installer and health diagnostics"`

### Task 9: Live Staged Rollout And Acceptance

**Files:**
- Modify: `README.md`
- Create: `docs/verification.md`

**Interfaces:**
- Consumes: all project commands and assets.
- Produces: verified live desktop, verification evidence, and documented rollback snapshot identifier.

- [ ] **Step 1: Run the full test suite from a clean worktree**

Run: `make test`

Expected: every foundation, fetch, theme, render, topology, layout, apply/rollback, and doctor test passes.

- [ ] **Step 2: Run preflight and dry-run**

Run: `./bin/doctor --preflight && ./bin/apply --dry-run`

Expected: no fatal preflight issue; dry-run lists only inventoried paths/settings and no display property other than priority.

- [ ] **Step 3: Install dependencies and render assets**

Run: `./bin/install && ./scripts/render-assets`

Expected: verified applets and exact-version effects are registered; static PNGs and silent MP4 pass render validation.

- [ ] **Step 4: Apply with the current external display connected**

Run: `./bin/apply`

Expected: command prints the snapshot identifier, makes the external output primary, places primary panels externally and telemetry internally, keeps one virtual desktop, and reports whether logout is required.

- [ ] **Step 5: Verify the live session**

Run `./bin/doctor`, inspect the Plasma/KWin user journal since apply, exercise tiling and floating windows on both outputs, test Overview and Magic Lamp, play audio for Kurve, open Qt/GTK/Firefox/Edge/Electron applications, lock/unlock, and capture a full desktop screenshot. Record each result and screenshot path in `docs/verification.md`.

- [ ] **Step 6: Prove rollback and reapply**

Run `./bin/rollback <snapshot-id>`, verify hashes and original appearance/configuration, then run `./bin/apply` again and repeat `./bin/doctor`. Do not claim reversibility until both restoration and reapplication pass.

- [ ] **Step 7: Verify laptop-only decision logic**

Run the live reconciler against sanitized internal-only KScreen JSON and, if the user disconnects the monitor during this session, verify the real panels move correctly. Record fixture verification separately from physical hotplug verification.

- [ ] **Step 8: Finalize user documentation**

Document normal install/apply/rollback, component upgrades, KWin rebuild requirements after Plasma upgrades, external-primary rules, static fallback, and the exact newest snapshot identifier in `README.md` and `docs/verification.md`.

- [ ] **Step 9: Commit verified integration**

Run: `git add README.md docs/verification.md && git commit -m "docs: record verified Arasaka rollout"`
