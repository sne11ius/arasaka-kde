# Automation and badge provenance

[Docs](README.md) / Automation

Every README badge is served by a third-party service and links to its evidence.
Build and analysis states come from GitHub Actions, coverage from Codecov,
security-practice scores from OpenSSF Scorecard, and repository metadata from
GitHub through Shields.io. No checked-in badge SVG or hand-written passing value
stands in for a result.

## Badge directory

| Badge | Backing service | Meaning |
| --- | --- | --- |
| Tests | GitHub Actions → Shields.io | `tests.yml`: repository suite and coverage generation/upload |
| Native build | GitHub Actions → Shields.io | `native.yml`: C++ rain physics, Qt/OpenGL rendering/input, and pointer bridge |
| Docs | GitHub Actions → Shields.io | `docs.yml`: Markdown, local links/fragments, and workflow syntax |
| Links | GitHub Actions → Shields.io | `links.yml`: external public-link check |
| CodeQL | GitHub Actions → Shields.io | Completion of Python and JavaScript/TypeScript analysis; not a vulnerability-free certificate |
| Core coverage | Codecov | Executed lines in the explicitly instrumented helper/physics scope below |
| OpenSSF Scorecard | Scorecard's public API | Repository security-practice score and detailed checks |
| Release | GitHub Releases → Shields.io | Latest published source release |
| License | GitHub license detection → Shields.io | Repository default; component exceptions still apply |
| Last commit | GitHub → Shields.io | Latest commit date on `main` |
| Contributors | GitHub → Shields.io | Contributor count |
| Stars / forks | GitHub → Shields.io | Public repository counts |
| Issues / pull requests | GitHub → Shields.io | Open counts, not a quality score |

Workflow badges follow `main`. Status and score colors reflect the service's
result; green metadata counts are styling, not health claims. Provider caching
can delay updates. An uninitialized or failed service is not treated as passing.

## Coverage scope

`make coverage` runs existing meaningful tests with instrumentation and produces:

| Report | Codecov flag | Measured production source |
| --- | --- | --- |
| `build/coverage/python.xml` | `python-helpers` | `lib/arasaka_topology.py` and `lib/arasaka_polonium.py` |
| `build/coverage/physics.xml` | `rain-physics` | `native/rain/dropletsimulation.cpp` and its header |

Python reports include branch measurement. The native report uses GCC/gcovr.
Codecov combines these reports into the README's **core coverage** figure.

This is **not whole-repository coverage**. Shell installers, Python `bin/` commands,
JavaScript/QML, shader code, the OpenGL renderer, KWin helper, PLM packaging, and
authentication are outside this percentage. Many have fixture or opt-in tests,
but are not instrumented by this coverage pipeline. The native build separately
exercises renderer/input/bridge behavior. Expand instrumentation before expanding
the scope claim; do not exclude difficult source merely to increase the badge.

Coverage uploads use GitHub OIDC on trusted pushes/manual runs in the canonical
repository. Fork pull requests generate downloadable reports without upload
credentials. Both named reports must arrive before Codecov posts combined status;
upload errors fail the publishing job. No fabricated starting percentage or
automatic score guarantee is configured.

## Public workflows

- **Repository tests:** run the existing suite in a digest-pinned Debian 13 test
  image, as an unprivileged user. Coverage runs after repository tests pass.
- **Native rain:** build/test physics and Qt/OpenGL rain components using Xvfb and
  Mesa software rendering; PLM pointer delivery uses a private bus and separate
  processes. Full greeter/authentication and full KDE package builds are out of scope.
- **Docs:** locked Markdown tooling, offline file/fragment checks, and actionlint.
- **Links:** external links on contributions and weekly, so upstream rot surfaces.
- **CodeQL:** Python and JavaScript/TypeScript on contributions and weekly. C++,
  QML, GLSL, and Bash are not covered by this configuration.
- **Scorecard:** publishes signed-origin results to the public Scorecard service
  on pushes to `main` and weekly. A scan's completion and its score are different facts.

Actions are pinned to commit SHAs and updated by Dependabot. The test image pins
the base digest and the artwork's Rajdhani font with its OFL license. Debian
package updates are resolved at image build time, so this is not a bit-for-bit
pinned toolchain. `.github/ci/package-lock.json` locks docs
dependencies. The `smol-toml` override selects the patched 1.8.0 parser while the
linter still pins a version affected by GHSA-7w5x-hrqm-74c2. Workflow permissions
default to read-only, with write permissions scoped to OIDC publishing and
code-scanning uploads where required.

### Link-check boundaries

Public Markdown, file paths, and anchors are checked. Historical records under
`docs/superpowers/`, `TODO.md`, and agent instructions are not public-guide lint
targets. The Lychee configuration lists narrowly scoped exclusions for dynamic
badge images and Shadertoy's bot-blocked pages. A badge image returning HTTP 200
does not prove that its underlying check passed; inspect the linked service.

Links to new workflows and external dashboards may be unavailable until this
change is published and the services initialize. Those are activation tasks,
not grounds to replace their badges with static green images.

## Activate the hosted services

These steps are for the repository owner. The files can be prepared and checked
locally, but GitHub cannot run an unpublished workflow.

### 1. Publish the reviewed change

Commit and push the intended docs/automation files through your normal workflow.
Include any current source changes the tests/docs depend on. Review the worktree
first so unrelated local work is not accidentally included.

After the change reaches `main`, inspect runs:

```sh
gh run list --repo sne11ius/arasaka-kde --limit 15
```

### 2. Connect Codecov

1. Open [Codecov](https://app.codecov.io/gh/sne11ius/arasaka-kde) and sign in with GitHub.
2. Grant access to this repository and activate it if prompted. Use the free public
   repository offering; no paid service is required by these workflows.
3. Rerun the repository test workflow after activation:

   ```sh
   gh workflow run tests.yml --repo sne11ius/arasaka-kde --ref main
   ```

The workflow uses `use_oidc: true`, so there is no `CODECOV_TOKEN` to copy into the
repository. If an upload fails, inspect its log and repository access in Codecov;
do not hide the failure. [Codecov action and OIDC documentation](https://github.com/codecov/codecov-action#using-oidc).

### 3. Let Scorecard publish

No separate Scorecard account is required. The push to `main` runs the workflow
with `publish_results: true` and a job-scoped GitHub OIDC token. Open the
[public report](https://scorecard.dev/viewer/?uri=github.com/sne11ius/arasaka-kde)
after the run completes. The initial score reflects actual repository settings;
some findings, such as review or branch-protection practices, require maintainer
decisions beyond workflow files.

### 4. Enable private vulnerability reports

In GitHub, open **Settings → Advanced Security → Private vulnerability reporting**
and enable it. Or, with an authenticated owner account:

```sh
gh api --method PUT repos/sne11ius/arasaka-kde/private-vulnerability-reporting
```

The security policy includes a fallback contact procedure while this is disabled.
Check **Security → Code scanning** for CodeQL and Scorecard results. Default Actions
permissions can stay read-only: the workflows request their specific permissions.

### 5. Verify the front page

Open the published README, follow every status badge, and confirm a real run/report
exists. Check the hero, the diagram, keyboard table, collapsible sections, and
mobile layout. Shields.io and GitHub's image cache may take time to refresh.

For forks, replace the canonical `sne11ius/arasaka-kde` badge/report URLs and upload
guard with your repository, then activate its services. Otherwise the badges
would describe upstream rather than your fork.

## Run the checks locally

Build the test container once, then use it for the suite, native tests, and coverage:

```sh
docker build --tag arasaka-ci .github/ci
docker run --rm --user "$(id -u):$(id -g)" \
  --volume "$PWD:/workspace" arasaka-ci make test
docker run --rm --user "$(id -u):$(id -g)" \
  --volume "$PWD:/workspace" arasaka-ci make test-native coverage
```

For Markdown:

```sh
npm --prefix .github/ci ci
make lint-docs
```

With [Lychee](https://github.com/lycheeverse/lychee) and
[actionlint](https://github.com/rhysd/actionlint) installed:

```sh
lychee --offline --include-fragments --config .lychee.toml \
  README.md ATTRIBUTION.md CONTRIBUTING.md CODE_OF_CONDUCT.md SECURITY.md SUPPORT.md \
  'docs/*.md' '.github/*.md'
lychee --config .lychee.toml \
  README.md ATTRIBUTION.md CONTRIBUTING.md CODE_OF_CONDUCT.md SECURITY.md SUPPORT.md \
  'docs/*.md' '.github/*.md'
actionlint
```

GitHub API rate limits or upstream outages can affect online link checks. Retain
the failing URL and response when investigating, and keep offline checks useful
even when a third-party service is unavailable.
