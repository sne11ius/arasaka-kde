# Security policy

## Report a vulnerability privately

Use GitHub's **Security → Report a vulnerability** for this repository when private
reporting is enabled. You can start from the
[security page](https://github.com/sne11ius/arasaka-kde/security).

If that option is unavailable, email the maintainer at
[cornelius.wichering@gmail.com](mailto:cornelius.wichering@gmail.com), as listed on
[@sne11ius's public profile](https://github.com/sne11ius). Do not open a public issue
containing an unpatched exploit or private account information.

Include the affected commit/component, supported environment, impact, and minimal
steps to reproduce. Redact credentials, tokens, private keys, and personal desktop
configuration. A small disposable fixture is ideal.

## Maintenance scope

Security fixes are developed against `main`. Tagged releases are source snapshots;
there is no separate long-term support or guaranteed backport schedule. This is a
volunteer-maintained project without a promised response time. We will work with
reporters on a fix and appropriate disclosure when possible.

## Relevant boundaries

The project includes live desktop installers, native plugins, downloaded upstream
components, and optional login-manager packaging. Useful reports include path or
backup handling, input crossing host boundaries, package-installation boundaries,
or unintended changes to authentication and lock policy.

The default rain observer is passive. PLM forwards screen-local pointer activity
over its existing session bus, and a locked desktop must reject input. Wallpaper
changes should preserve credential handling, authentication, and the user's lock
policy. See [the wallpaper architecture](docs/wallpaper.md#how-input-reaches-the-rain).

Upstream components retain their own security processes. If a problem originates
upstream, identify the pinned version from `manifest/components.tsv` and coordinate
with the relevant project as needed.

CodeQL, Scorecard, and test results are useful signals with documented scope;
none is a guarantee that the project has no vulnerabilities.
