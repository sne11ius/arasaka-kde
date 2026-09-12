# Stream Deck Konsole appearance

The showcase uses the Quake Konsole design from
[sne11ius/streamdeck-scripts](https://github.com/sne11ius/streamdeck-scripts),
licensed under EUPL-1.2.

`quake.qss` is a byte-for-byte snapshot of the requested local working-tree file
`konsole-config/quake.qss` (repository base `ef19572`). Its SHA-256 is
`75a785f9f6a5b482df7b1eeec62162fa32463a68fc7fa025fadca19542be9b51`.
The stylesheet was not yet committed upstream when imported.

The tour applies the accompanying native settings from `install-konsole-style.sh`:
`AlwaysHideSplitHeader`, `SplitDragHandleMedium` (5 logical pixels), hidden
toolbars, and bottom tabs. It uses the borderless, keep-above, full-width and
75.5%-height geometry from `konsole-quake-toggle.sh`, with the managed tiler's
existing PID-scoped Quake exception. The demo panes contain disposable project
commands and directories.
