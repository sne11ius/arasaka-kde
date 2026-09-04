# Arasaka KDE

Arasaka KDE is a reproducible, safety-oriented KDE Plasma 6 rice for TUXEDO OS. The repository owns declarative assets and narrow deployment tools while snapshots protect live user configuration during changes.

The implementation is in progress. The project foundation currently provides shared shell utilities and a test harness; deployment commands will be added by subsequent tasks.

## Development

Run all shell and Python tests:

```sh
make test
```

The Makefile also exposes the planned operational entry points:

```sh
make doctor
make dry-run
make apply
make rollback SNAPSHOT=<snapshot-id>
```

See `docs/superpowers/specs/2026-09-04-arasaka-kde-rice-design.md` for the approved design and `docs/superpowers/plans/2026-09-04-arasaka-kde-rice.md` for the implementation plan.
