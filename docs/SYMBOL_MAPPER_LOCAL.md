# Singh360 Symbol Mapper - Local Integration

Symbol Mapper is an independent, reviewed workflow inside Singh360 Draft. It accepts one PDF page, lets the user define symbol classes and legend-icon crops, detects candidates, requires review for uncertain results, exports an original-size marked PDF, and can add the reviewed result as a new Singh360 drawing page.

## Safety boundaries

- The uploaded source PDF is copied into `.docs/symbol_mapper/<session>/source.pdf` and never modified in place.
- Exact text plus an enclosing vector marker may be pre-accepted.
- Text-only and visual-template-only candidates remain in **Review** until the user accepts or rejects them.
- Final output contains accepted candidates only.
- Adding a page is explicit. The page is appended with sheet code `NEW`, includes the standard title block, and activates the existing renumber reminder.
- No customer PDF, workbook, screenshot, `.docs` content, export, token, or credential is committed by the installer.
- The local installer has no Google Cloud, SSH, Docker deployment, or `start-live.ps1` command.

## Local use

1. Start Singh360 Draft locally on port 8766.
2. Open a project.
3. Select the **Symbols** ribbon tab.
4. Click **Open Symbol Mapper**.
5. Upload a one-page PDF.
6. Add one row per symbol, enter its printed code, choose the color/pattern, and optionally drag a tight box around the legend icon.
7. Run detection.
8. Review every orange/gray candidate. Accept or reject it. Use **Add missing marker** to drag a box around any symbol the detector missed.
9. Render accepted highlights.
10. Download the original-size PDF or click **Add reviewed page at end**.

The added page is a normal canvas page. It can be moved, copied, excluded, renamed, renumbered, or deleted with the existing page controls.

## Test commands

```powershell
.\.venv\Scripts\python.exe -m py_compile server.py core\symbol_mapper.py
.\.venv\Scripts\python.exe scripts\smoke_symbol_mapper.py
.\.venv\Scripts\python.exe scripts\smoke_symbol_mapper_api.py
Push-Location frontend
npm run build
Pop-Location
git diff --check
```

## Storage

Session data is local runtime data:

```text
.docs/
  symbol_mapper/
    <24-character session id>/
      source.pdf
      source.png
      session.json
      detection.json
      review.pdf
      review.png
      final.pdf
      final.png
```

Delete a session through the API or remove it only after confirming its output is no longer needed. Project pages use a copied project asset, so deleting an old session does not remove a page already added to a Singh360 project.
