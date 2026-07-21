# Singh360 Symbol Mapper — Simple Workflow

The Symbol Mapper is a separate workspace inside Singh360 Draft.

## Workflow

1. Upload one single-page PDF.
2. The app finds the printed `SYMBOLS KEY` or `SYMBOL LEGEND` automatically.
3. The discovered rows appear with their actual icon, code, and description.
4. Check only the symbols you want.
5. Click a ready-made color: Red, Green, Yellow, Blue, Orange, Purple,
   Cyan, Pink, or a two-color split such as Red / Green or Red / Blue.
6. The selected colors are shown directly over the symbol key.
7. Click **Run selected symbols**.
8. Only uncertain matches appear under **Needs a quick check**. Choose Include or
   Ignore; you do not draw boxes around every occurrence.
9. Click **Create highlighted page**, then download the original-size PDF or add
   the page to the end of the open Singh360 project.

## What was deliberately removed

- No manual icon crop for every legend row.
- No Primary Color / Secondary Color fields.
- No marker-size control.
- No source-outline selector.
- No visible template-correlation or detector jargon.
- No fake or disabled ribbon buttons.

## Detection and output

The app reads the key from the PDF text coordinates and enclosing vector shapes.
Exact text inside the expected circle or square is accepted automatically.
Unboxed or ambiguous text is held for the small quick-check list. The uploaded
PDF is never overwritten; the final output is a reviewed copy with the original
page dimensions preserved.

Runtime sessions remain under `.docs/symbol_mapper/` and are not committed.
