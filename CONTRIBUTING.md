# Contributing to Arasaka KDE

Thanks for spending some of your time here. Code, documentation, compatibility
reports, visual refinements, and thoughtful bug reports are all welcome.

## Find a starting point

- Read the [feature tour](README.md) and [documentation hub](docs/README.md).
- Browse [open issues](https://github.com/sne11ius/arasaka-kde/issues), or
  [describe an idea](https://github.com/sne11ius/arasaka-kde/issues/new/choose).
- For a substantial visual or behavioral change, discuss the intended result
  first so we can agree on the scope and supported host behavior.
- Small corrections and clearer instructions can go straight to a pull request.

Be kind and specific. Our [code of conduct](CODE_OF_CONDUCT.md) applies throughout
the project. For vulnerabilities, use [private security reporting](SECURITY.md).

## Set up and test

```sh
git clone https://github.com/sne11ius/arasaka-kde.git
cd arasaka-kde
git switch -c your-change
```

Use your own fork as the push remote when contributing from outside the project.
The [development guide](docs/development.md) lists dependencies and a Docker-based
test environment. Run the relevant checks before submitting:

```sh
make test
```

For documentation:

```sh
npm --prefix .github/ci ci
make lint-docs
```

Native rendering and real host behavior need the corresponding
[integration checks](docs/development.md#native-and-live-integration). State what
you actually ran, including skipped checks and observations still needed on a
normal lock/login. CI is useful evidence, not a substitute for the host boundary.

## Make a focused change

- Follow surrounding source structure, naming, and component boundaries.
- Update the relevant public guide when a command, prerequisite, or behavior changes.
- Keep input assets and source patches in the repository; generated packages,
  caches, screenshots of private desktops, and personal configuration stay local.
- Retain upstream author/license notices. Record new dependencies and adaptations
  in [ATTRIBUTION.md](ATTRIBUTION.md) and pin downloaded inputs in
  [`manifest/components.tsv`](manifest/components.tsv).
- Test behavior and failure cases that matter. Avoid tests that merely repeat
  implementation details or assert a decorative status value.

### Background changes

Desktop, idle/session locker, and PLM login are one managed background experience:
artwork, physics, animation quality/speed, hover, and clicks should match. Keep
shared defaults and parity checks current. PLM's separate greeter/wallpaper
processes require actual pointer delivery through the existing bus; enabling a
setting alone is insufficient. The desktop behind a locked session must still
reject input.

Preserve authentication, lock policy, and the user's clock preference. Update
user-local desktop/locker assets and build the system packages needed by PLM.
Report any user-run installation or next-session visual check still outstanding.

### Screenshots and visual evidence

Use a clean, disposable scene. Remove account names, notifications, document
contents, and other private information. Describe the display scale, Plasma/GPU
versions, and whether the image is source artwork, a test render, or a live host
capture. Include attribution for any new visual material.

## Send the pull request

Explain the problem, the result, and how you verified it. Link any related issue.
For visual changes, add a focused before/after image when practical. The PR template
provides a short outline; a small change deserves a small description.

Use concise, descriptive commit messages. Existing history uses forms such as
`feat: ...`, `fix: ...`, and `docs: ...`. Contributions retain the license of the
files/components they modify; original project material defaults to EUPL-1.2.
There is no separate contributor license agreement in this repository.

If a check fails, open its linked log and share the relevant error. We would
rather work through an honest failure together than hide it behind a green badge.
