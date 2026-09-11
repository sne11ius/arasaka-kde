# Reproducible login-to-desktop showcase

## Approved outcome

Replace the README's static hero with a real, approximately 90-second video made
by CI. Show PLM login, native rain and pointer interaction, the launcher, styled
Konsole windows, tiling, TV Glitch transitions, and a lock/unlock round trip.
The user approved this real-VM design and native inline publishing on 2026-09-11.

## Runtime and provenance

Use QEMU/KVM with a Debian forky generic image and a frozen Debian APT snapshot.
The image is the official amd64 build `20260911-2598`, verified with its published
SHA-512 digest. The APT snapshot is `20260911T000000Z`. Build native dependencies
and both PLM packages in the guest against that same stack. All project visuals
come from the recorded source commit and the existing pinned component manifest.

The recording fixture owns a disposable `demo` account and VM disk. It uses real
PAM login, PLM processes, Plasma Wayland, Konsole, and the managed rain module.
Provisioning does not change the operator's desktop, display manager, or account.
Guest-only administrative scripts require a fixture marker and QEMU virtualization.

The host runtime is a digest-pinned Docker image containing QEMU, Xvfb, FFmpeg,
OpenSSH tools, Python, Pillow, xdotool, and ISO creation tools. Only `/dev/kvm` is
passed through; no live display, home, session bus, or host systemd is mounted.
The default guest display is 1280×720 with 30 FPS capture. The high-quality master
and a size-bounded H.264 inline copy have identical scenes and running speed.

## File boundaries

- `bin/record-showcase`: normal-user entry point; checks Docker/KVM, builds the
  recorder image, and invokes the same host controller used in CI.
- `scripts/showcase/runner.py`: immutable downloads, owned workspace, VM lifecycle,
  SSH provisioning, phase readiness, and orchestrating recording.
- `scripts/showcase/machine.py`: QMP command/reply handling and guest transport.
- `scripts/showcase/guest-prepare.sh`: guest-only package/native-component setup.
- `scripts/showcase/guest-session.sh`: idempotent desktop deployment and demo scene.
- `scripts/showcase/tour.py`: real keyboard/mouse actions and chapter evidence.
- `scripts/showcase/media.py`: encoding and observable video/scene validation.
- `scripts/showcase/publish.py`: GitHub attachment/release publication and a
  narrowly managed README block; preserves the last good public video on failure.
- `showcase/environment.json`: immutable image/snapshot, display, resource limits.
- `showcase/storyboard.json`: ordered scenes and nominal dwell durations.
- `.github/showcase/Dockerfile`: recorder dependencies and runtime user.
- `.github/workflows/showcase.yml`: build/record/validate, artifacts, and publishing.
- `tests/showcase_test.py`: host-side protocol, lifecycle, media, and publication
  regressions; no real login session is needed for this small unit suite.
- `docs/showcase.md`: one-command reproduction, evidence, CI, and credential setup.

## Lifecycle and idempotence

An invocation acquires an exclusive workspace lock. Verified base downloads are
immutable and reusable; incomplete downloads are never accepted. Each recording
uses a fresh qcow2 overlay and fresh fixture keys. The source is transferred as a
Git bundle containing HEAD and its ancestry, not the operator's working files.
The guest records the source SHA and installed package versions.

Provisioning installs the missing visual/build prerequisites, builds Klassy and
Better Blur DX from pinned inputs, builds the shader/PLM packages, starts a real
Plasma session for the scoped deployment commands, and configures PLM as the final
manager. Final autologin is disabled. Reboot into PLM before recording begins.
Commands use readiness checks with deadlines, and fail rather than record a
half-installed theme. Rerunning preparation converges on the same owned settings.

The tour starts once the greeter is visible. Use QMP keyboard events and the
isolated display's actual pointer, so clicks traverse the greeter/wallpaper bridge
or the desktop's normal input path. Wait for login/session and lock state through
guest services, and for launched application windows through the native helper.
Short dwell times compose the film; they do not replace readiness checks.

## Storyboard

1. Greeter: rain, hover and left-click activity; authenticate the demo user.
2. Desktop: a clean reveal, then hover and clicks on rain-covered areas.
3. Launcher: Super, application search, and launch Konsole.
4. Terminals: actual system information, process monitor, and project code/history;
   use the managed palette and fonts, automatic tiling, and readable output.
5. Effects: focus/rearrange tiles and minimize/restore with the actual effects.
6. Native full menu/tray, then dismiss to the workspace.
7. Session lock: rain interaction, real unlock, final composed desktop.

A chapter log records observed host state and frame timestamps. No synthetic QML
login, fabricated terminal output, interpolated rain, or prerecorded substitute
may stand in for a successful real session. Capture performance is reported as
fixture evidence, not a physical-GPU benchmark.

## Media and publication

Produce `showcase.mp4`, `showcase-inline.mp4`, `poster.png`, `chapters.json`, and
`provenance.json`. Validate H.264/yuv420p, dimensions, duration, frame count, required
chapter completion, nonblack frames, and visible frame changes in rain chapters.
Keep diagnostic screenshots/logs on failure; publish only validated success.

The inline copy fits GitHub's 10 MB free-plan attachment limit. Publish with a
pinned GitHub CLI version supporting `--attach`, using a repository-scoped
`SHOWCASE_UPLOAD_TOKEN` provided by the owner. The default Actions token is not
accepted by that upload client. Use one managed media issue rather than creating
a new issue for every run. Store the master and provenance in a non-latest
prerelease so the software-release badge keeps its existing meaning.

Only the managed README showcase block changes during refresh. The block links
the exact source commit and high-quality master. Repeated publishing of the same
source/video hash is a no-op. Publication runs only for trusted main-branch output;
branch runs produce reviewable artifacts. Missing upload credentials are reported
explicitly, with the generated film still available as a CI artifact.

## Acceptance

- All guest stages complete twice without accumulating duplicate configuration.
- A cold VM boot reaches the real PLM greeter and authenticates into Plasma.
- The recorded tour completes every required scene and demonstrates rain input.
- The actual captured film is reviewed for readability, framing, and animation.
- GitHub Actions produces and validates the film from committed scripts.
- The README displays the uploaded film inline, with public source/provenance links.
- Existing docs, workflow, repository, native rain, and coverage checks remain valid.
