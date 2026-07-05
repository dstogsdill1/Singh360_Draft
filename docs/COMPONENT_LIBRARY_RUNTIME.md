# Component Library Runtime (Local `.docs`)

The `.docs` folder is **local runtime data only**. It is gitignored and should
never be treated as source code or as a permanent artifact store.

## Active runtime roots

```text
.docs/
  projects/
  exports/
  library/
    components/          # source images/PDFs you add
    symbols/             # approved real B/W symbols (from Component Builder workflow)
    thumbnails/          # generated previews only
    manifest.json
    aliases.json
    connector_styles.json
  archive/
```

## What each folder means

- `.docs/library/components`  
  Your source component files (PNG/JPG/SVG/PDF). Refresh scans this folder only.

- `.docs/library/symbols`  
  Approved black/white symbols only. This pass does **not** auto-generate these.

- `.docs/library/thumbnails`  
  Generated previews only. Safe to rebuild; not scanned as source.

## What not to delete

- Keep `manifest.json`, `aliases.json`, and `connector_styles.json`.
- Keep source files under `components/`.
- Avoid manually editing `manifest.json` unless debugging with backups.

## Why fake generated symbols were removed

Previous `*.symbol.svg` files generated from generic templates did not represent
real equipment geometry and were therefore not approved.

They are archived by `scripts/cleanup_fake_symbols.py` and manifest references
are cleared with `symbolStatus: "not_built"`.

## Common tasks

- Inspect runtime state:
  - `python scripts/inspect_runtime_workspace.py`
- Cleanup legacy runtime folders (dry-run first):
  - `python scripts/cleanup_runtime_workspace.py --dry-run`
  - `python scripts/cleanup_runtime_workspace.py --apply`
- Archive fake generated symbols:
  - `python scripts/cleanup_fake_symbols.py --dry-run`
  - `python scripts/cleanup_fake_symbols.py --apply`

## Important guardrails

- Refresh Library scans only `.docs/library/components`.
- Refresh Library does not generate `*.symbol.svg`.
- Rebuild Thumbnails writes only to `.docs/library/thumbnails`.
- Legacy folders are archived, not silently deleted.
