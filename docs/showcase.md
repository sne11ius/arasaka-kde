# The recorded showcase

[Docs](README.md) / Showcase

The README film is made from a real disposable VM: PLM login, interactive rain,
Plasma, the launcher, styled Konsole windows, and tiling/effects.
GitHub Actions runs the same scripts available in the checkout.

## Record it

On Linux with Docker and KVM access, from the repository root:

```sh
./bin/record-showcase all
```

The command downloads the checksum-pinned Debian image, installs the frozen
package set and actual project components, reboots into PLM, and records the tour.
It prints the output directory under `build/showcase/`. The operator's running
desktop and login manager are not used by the recording.

To prepare once and retry the filmed tour without rebuilding the guest:

```sh
./bin/record-showcase prepare
./bin/record-showcase record --prepared build/showcase/run-YOUR-RUN
```

Use the run directory printed by preparation. A new overlay preserves that guest
between takes. Its source commit remains the version shown in the film.

Outputs are the high-quality `showcase.mp4`, a smaller `showcase-inline.mp4`, a
real-frame `poster.png`, `chapters.json`, and `provenance.json` with the source
commit, environment, dimensions, duration and file hashes. Recording is silent,
1280×720, with a 30 FPS capture target. Guest performance is that of the VM; footage
is not sped up or frame-interpolated.

## CI and publishing

[Recorded desktop showcase](https://github.com/sne11ius/arasaka-kde/actions/workflows/showcase.yml)
runs for visual/source changes on `main`, or manually:

```sh
gh workflow run showcase.yml --repo sne11ius/arasaka-kde
```

Successful runs retain the film as an Actions artifact. Main-branch publication
uploads the inline movie through GitHub's native media service and places the
master and provenance in a non-latest showcase prerelease. One closed, managed
media issue holds the native attachment. The publisher replaces only the marked
README block; unsuccessful recordings do not replace the published film.

Inline uploads require the `SHOWCASE_UPLOAD_TOKEN` repository secret: a fine-grained
GitHub token restricted to this repository with Contents and Issues read/write.
Set it from your own terminal:

```sh
gh secret set SHOWCASE_UPLOAD_TOKEN --repo sne11ius/arasaka-kde
```

The pinned GitHub CLI supports native video attachments. This credential is used
only by publishing, not placed in the guest. Codecov uses its separate GitHub OIDC
integration and needs no token secret.
