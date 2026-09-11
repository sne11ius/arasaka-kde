# CI Showcase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate and publish a real login-to-desktop film from an idempotent CI-controlled VM.

**Architecture:** A normal-user host controller runs a disposable QEMU/KVM guest
inside a recorder container. Guest scripts install the real project; a state-aware
tour drives native input while FFmpeg captures the display. A separate publisher
validates provenance and updates only the README's managed video block.

**Tech Stack:** Python 3, Bash, QEMU/KVM/QMP, cloud-init, Debian snapshot APT,
KDE Plasma Wayland/PLM, Xvfb/xdotool, FFmpeg/ffprobe, GitHub Actions/CLI.

**Spec:** `docs/superpowers/specs/2026-09-11-ci-showcase-design.md`

## Global constraints

- Debian generic amd64 image `20260911-2598`; APT snapshot `20260911T000000Z`.
- Capture 1280×720 at 30 FPS, approximately 90 seconds; keep playback at recorded speed.
- Actual PLM, Plasma, project packages, pointer delivery, terminal output, and lock/unlock.
- Administrative changes are confined to a marked QEMU guest.
- Source HEAD and package versions accompany the film; only committed source is recorded.
- Failed capture never replaces the last good video; publish only trusted main output.
- No host display/session bus/private home is mounted into the recorder.

## Task 1: Host environment and VM transport

**Files:** `.github/showcase/Dockerfile`, `showcase/environment.json`,
`bin/record-showcase`, `scripts/showcase/{runner,machine}.py`, `tests/showcase_test.py`.

**Interfaces:** `QMP(socket_path).execute(command, arguments=None)` matches replies
by ID and handles events; `Guest(port, key).run(command, timeout=...)` executes only
over the fixture's SSH port. `verified_download(url, path, algorithm, digest)`
atomically accepts only matching bytes. CLI phases are `prepare`, `record`, `all`.

- [ ] Write protocol/download tests: mismatched bytes cannot replace a cached
  image; asynchronous QMP events do not become command results; errors/timeouts
  propagate; workspace locking excludes a second controller.
- [ ] Run `python3 tests/showcase_test.py -v` and observe the missing implementation.
- [ ] Implement SHA-512 streaming download and rename after verification:

  ```python
  actual = hashlib.file_digest(stream, algorithm).hexdigest()
  if actual != expected:
      raise ValueError("download checksum mismatch")
  os.replace(partial, destination)
  ```

- [ ] Implement cloud-init fixture users/keys and ISO creation, a qcow2 overlay,
  KVM/virtio display, QMP socket, loopback SSH forwarding, and process cleanup.
  Use `git bundle create SOURCE.bundle HEAD` for source transfer.
- [ ] Boot the image, wait for `cloud-init status --wait`, and obtain the real
  guest's `/etc/os-release` over SSH. Store console and transport errors in the
  owned workspace. Verify protocol tests and commit this independently testable boot.

## Task 2: Idempotent real KDE/PLM guest

**Files:** `scripts/showcase/guest-prepare.sh`, `scripts/showcase/guest-session.sh`.

**Interfaces:** `guest-prepare.sh SOURCE_BUNDLE` creates the marked environment and
  `/home/demo/arasaka-kde`; `guest-session.sh prepare|status|reset` runs with the
  demo user's real D-Bus/runtime environment. A JSON readiness result identifies
  the current source, session type, wallpaper, and native window-policy state.

- [ ] Add a regression proving preparation refuses an unmarked/non-QEMU host.
- [ ] Install the versioned PLM build dependencies from the existing control file,
  shader/KWin prerequisites, the stock desktop/launcher/tray, Konsole, Kvantum
  themes, fonts, and terminal tools using the frozen APT source.
- [ ] Build/install pinned Klassy and Better Blur DX inside the guest. Use the
  existing scoped commands for shader assets, tiling, effects, and theme setup.
- [ ] Configure a demo Konsole profile using Arasaka colors and JetBrains Mono,
  with real shell/system/code displays. Create only fixture-owned settings.
- [ ] Build both PLM packages as `demo`; install in the guest, use the shared login
  background updater, and verify the actual configured session/PAM/asset state.
- [ ] Run preparation twice and compare managed settings/source fingerprints.
  Reboot and prove the actual PLM greeter starts with final autologin disabled.

## Task 3: Real-input tour and video validation

**Files:** `showcase/storyboard.json`, `scripts/showcase/{tour,media}.py`,
`tests/showcase_test.py`.

**Interfaces:** `run_tour(guest, qmp, display, output)` returns completed chapters
with monotonic timestamps and screenshot paths. `validate_media(video, chapters,
width, height)` returns ffprobe metadata or raises on invalid/missing evidence.

- [ ] Write failing tests for missing chapters, wrong dimensions/codec, truncated
  duration, black frames, and absent rain-scene frame changes using tiny generated
  FFmpeg fixtures. Test fixtures are never published as the showcase.
- [ ] Implement native key sequences and smooth pointer moves/clicks, waiting for
  observed session, launcher/window, and lock state at each transition.
- [ ] Capture Xvfb's QEMU display with `ffmpeg -f x11grab -framerate 30`, H.264,
  yuv420p, and faststart. Record the actual guest; do not replace its screen with
  test-only QML or change simulation pace to conceal dropped frames.
- [ ] Implement a two-pass, size-bounded inline copy and a high-quality master.
  Include source SHA, package inventory, display settings, media hashes, and
  chapter results in provenance. Test real failure paths and all media tests.
- [ ] Run and review the full tour; retain first/last/chapter screenshots and fix
  framing, readiness, or input delivery before committing the recorder.

## Task 4: CI publishing and README integration

**Files:** `.github/workflows/showcase.yml`, `scripts/showcase/publish.py`,
`README.md`, `docs/{showcase,README,automation}.md`, `.github/dependabot.yml`.

**Interfaces:** Publisher consumes only validated `provenance.json` and its hashed
media. `replace_showcase(readme, block)` preserves bytes outside unique managed
markers and rejects ambiguous markers. Same source/media hashes make publishing a
no-op. A missing token leaves artifacts available and reports the required setup.

- [ ] Write failing tests for block preservation, duplicate/missing markers, bad
  media hash, and repeat publication.
- [ ] Implement the publisher with pinned GitHub CLI attachment support, one
  managed media issue, non-latest showcase release assets, and source links.
- [ ] Add Actions jobs for generation and publication, read-only defaults,
  scoped publish permissions, concurrency control, finite timeouts, and explicit
  artifact paths. Exclude fixture disks and private transport keys from uploads.
- [ ] Add a real workflow-backed showcase badge. Trigger source/visual changes
  and manual runs, without retriggering on its own README refresh.
- [ ] Run actionlint, Markdown and link checks, the host/media unit suite, and a
  full hosted recording. Confirm inline playback and public artifact provenance.
- [ ] Review the final scoped diff, integrate with current main without overwriting
  concurrent work, and publish the verified pipeline and generated film.
