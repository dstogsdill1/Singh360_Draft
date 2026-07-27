---
mode: agent
description: Verify and publish a completed Singh360 Draft change safely.
---

Read the root `AGENTS.md`. Reinspect the branch, `HEAD`, status, and complete
diff. Run only the requested relevant checks with sanitized disposable data.
Never use `.docs/`, customer projects, workbooks, PDFs, exports, or runtime data
as fixtures. Never run **SAVE + WRITE EXCEL** unless explicitly requested.
Stage every valid related source and instruction file by explicit path, while
excluding `.docs/`, `.local_backups/`, `.tmp/`, workbooks, customer data, PDFs,
exports, credentials, and generated output. Review the staged file list and
diff, commit with the user-specified message, push the current branch without
switching, and report direct evidence. Never claim success without evidence.
