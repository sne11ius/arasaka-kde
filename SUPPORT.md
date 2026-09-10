# Getting help

You are welcome to ask questions, even if you are new to Plasma customization.

1. Check [installation](docs/installation.md) for prerequisites and compatibility.
2. Look up the symptom in [troubleshooting](docs/troubleshooting.md).
3. If you are still stuck, [open a support question](https://github.com/sne11ius/arasaka-kde/issues/new/choose).

## Help us reproduce it

Include the smallest useful set of details:

- The exact command or interaction, expected result, and actual result.
- Your distribution, Plasma/KWin version, Wayland or X11, and GPU/driver if rendering
  is involved.
- The commit (`git rev-parse --short HEAD`) and whether you have local changes.
- The affected surface: desktop, session locker, PLM login, launcher, or windows.
- A short relevant log excerpt and a cropped/redacted screenshot if helpful.

Useful version commands:

```sh
git rev-parse --short HEAD
plasmashell --version
kwin_wayland --version
```

Do not upload complete home directories, private backups, browser profiles,
passwords, tokens, or keys. Installer backup paths identify recovery snapshots;
the contents usually are not needed for an initial report.

## Other kinds of reports

- **Bug or feature idea:** use the matching [issue form](https://github.com/sne11ius/arasaka-kde/issues/new/choose).
- **Vulnerability:** follow [SECURITY.md](SECURITY.md) for private reporting.
- **Conduct concern:** use the private contact in [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
- **Documentation fix:** a small [pull request](CONTRIBUTING.md) is welcome.

Support is best-effort and volunteer-run. Clear reports and kindness make it much
easier for everyone to help.
