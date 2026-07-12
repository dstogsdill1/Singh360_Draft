from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path(__file__).resolve().parent
TEMPLATES = TOOLS / "templates"
DOCS = ROOT / "docs"
STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")
BACKUP = ROOT / ".docs" / "archive" / f"current_app_repo_reset_{STAMP}"
REPORT = BACKUP / "cleanup_report.txt"

LEGACY = [
    "main_generator.py", "pipeline_cli.py", "config.py", "web", "ems",
    "core/ingestion.py", "core/data_orchestrator.py", "core/schedule_adapter.py",
    "core/idf_builder.py", "core/model.py", "core/merge.py", "core/extractors",
    "engines/doc_templates", "engines/smartdraw_vson.py", "engines/visio_vsdx.py",
    "engines/rdm_layout_xml.py", "engines/drawing_package.py",
    "engines/svg_diagram.py", "engines/spatial_layout.py", "engines/title_block.py",
]

KEEP_ROOT = {
    ".gitignore", "AGENTS.md", "README.md", "requirements.txt", "server.py",
    "start-local.ps1", "start-live.ps1", "START_SINGH360.bat",
    "RESET_TO_CURRENT_APP.bat",
}
PREFIX_JUNK = (
    "README_", "ROLLBACK_", "INSTALL_", "RUN_", "PUBLISH_", "PUSH_",
    "OPEN_", "SEND_", "IMPORT_", "ENABLE_",
)
NAME_JUNK = {
    "readme", "KANBAN.md", "Microsoft.Services.Store.winmd", "temp.py",
    "fix_dashboard.py", "singh360-rebuild-hero.png",
    "singh360-repaired-homepage-top.png",
}


def log(text=""):
    print(text)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    with REPORT.open("a", encoding="utf-8") as fh:
        fh.write(text + "\n")


def backup(path: Path):
    if not path.exists():
        return
    dest = BACKUP / "files" / path.relative_to(ROOT)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if path.is_dir():
        shutil.copytree(path, dest, dirs_exist_ok=True)
    else:
        shutil.copy2(path, dest)


def remove(path: Path):
    if not path.exists():
        return
    backup(path)
    rel = path.relative_to(ROOT).as_posix()
    shutil.rmtree(path) if path.is_dir() else path.unlink()
    log(f"Removed (backed up): {rel}")


def replace(path: Path, template_name: str):
    backup(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TEMPLATES / template_name, path)
    log(f"Updated: {path.relative_to(ROOT).as_posix()}")


def run(cmd, cwd=ROOT):
    log("$ " + " ".join(map(str, cmd)))
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode:
        raise RuntimeError(f"Command failed: {' '.join(map(str, cmd))}")


def patch_server():
    path = ROOT / "server.py"
    text = path.read_text(encoding="utf-8-sig")
    old = text
    text = re.sub(r'^WEB_DIR\s*=\s*HERE\s*/\s*"web"\s*\n', "", text, flags=re.M)
    text = text.replace(', "/editor"', "").replace('"/editor", ', "")
    text = re.sub(
        r'\n@app\.get\("/editor"\)\ndef legacy_editor_index\(\):\n(?:[ \t]+.*\n)+',
        "\n", text, count=1,
    )
    text = re.sub(r'^.*Legacy fallback.*\n', "", text, flags=re.M)
    text = re.sub(r'^.*legacy fallback.*\n', "", text, flags=re.M)
    text = re.sub(r'^.*href="/editor".*\n', "", text, flags=re.M)
    if text != old:
        backup(path)
        path.write_text(text, encoding="utf-8")
        log("Patched server.py: removed legacy /editor fallback.")
    return "/editor" not in text and "WEB_DIR" not in text


def patch_smoke_routes():
    path = ROOT / "scripts" / "smoke_routes.py"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    old = text
    text = re.sub(
        r'\n\s*r_editor = client\.get\("/editor"\)\n\s*print\(f"GET /editor.*?\n',
        "\n", text, count=1,
    )
    if text != old:
        backup(path)
        path.write_text(text, encoding="utf-8")
        log("Updated smoke_routes.py.")


def clean_docs():
    DOCS.mkdir(parents=True, exist_ok=True)
    for child in list(DOCS.iterdir()):
        if child.name != "component-library":
            remove(child)
    replace(DOCS / "index.html", "docs_index.html")
    replace(DOCS / "README.md", "docs_README.md")
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")
    log("Created docs/.nojekyll")


def keep_ppt(path: Path):
    name = path.name.lower()
    return path.suffix.lower() == ".pptx" and (
        "singh360_component_library_real" in name
        or "singh360 component library real" in name
    )


def clean_root():
    for path in list(ROOT.iterdir()):
        if not path.is_file() or path.name in KEEP_ROOT or keep_ppt(path):
            continue
        junk = (
            path.name in NAME_JUNK
            or path.name.startswith(PREFIX_JUNK)
            or path.suffix.lower() in {".zip", ".pdf", ".txt", ".pptx"}
        )
        if junk:
            remove(path)


def clean_legacy():
    server_clean = patch_server()
    patch_smoke_routes()
    for rel in LEGACY:
        if rel == "web" and not server_clean:
            log("Kept web/: server still references it.")
            continue
        remove(ROOT / rel)
    init_path = ROOT / "__init__.py"
    backup(init_path)
    init_path.write_text("# Singh360 Draft package\n", encoding="utf-8")
    log("Updated __init__.py")


def ensure_gitignore():
    path = ROOT / ".gitignore"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = [
        ".docs/", "*.pptx", "Singh360_Component_Library_Real*.pptx",
        "Singh360 Component Library Real*.pptx",
    ]
    add = [x for x in lines if not re.search(rf"(?m)^{re.escape(x)}$", text)]
    if add:
        backup(path)
        with path.open("a", encoding="utf-8") as fh:
            fh.write("\n# Local runtime and personal PowerPoint palettes\n")
            fh.write("\n".join(add) + "\n")
        log("Updated .gitignore")


def restore():
    src_root = BACKUP / "files"
    if not src_root.exists():
        return
    log("Validation failed. Restoring backup.")
    for src in sorted(src_root.rglob("*")):
        if src.is_file():
            dest = ROOT / src.relative_to(src_root)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
    log("Backup restored; no commit made.")


def validate():
    py = ROOT / ".venv" / "Scripts" / "python.exe"
    python = str(py) if py.exists() else sys.executable
    run([python, "-m", "compileall", "server.py", "core", "engines", "scripts"])
    frontend = ROOT / "frontend"
    if (frontend / "package.json").exists():
        npm = "npm.cmd" if os.name == "nt" else "npm"
        run([npm, "run", "build"], cwd=frontend)
    for name in ("smoke_routes.py", "smoke_component_library.py"):
        smoke = ROOT / "scripts" / name
        if smoke.exists():
            run([python, str(smoke)])


def main():
    if not (ROOT / ".git").exists() or not (ROOT / "server.py").exists():
        print("Extract this pack into the Singh360_SmartDraw repository root.")
        return 1
    if not (DOCS / "component-library").exists():
        print("docs/component-library is missing. Stop and publish the catalog first.")
        return 1

    BACKUP.mkdir(parents=True, exist_ok=True)
    log(f"Repository: {ROOT}")
    log(f"Backup: {BACKUP}")
    log("Git status before reset:")
    status = subprocess.run(
        ["git", "status", "--short"], cwd=ROOT, text=True, capture_output=True
    )
    log(status.stdout.rstrip())

    print("\nKeeps .docs and docs/component-library.")
    print("Removes old public docs, legacy generator code, /editor, and root clutter.")
    print("Everything removed is copied to .docs/archive first.")
    if input("\nType RESET to continue: ").strip() != "RESET":
        print("Cancelled.")
        return 0

    try:
        clean_docs()
        replace(ROOT / "README.md", "README.md")
        replace(ROOT / "AGENTS.md", "AGENTS.md")
        ensure_gitignore()
        clean_root()
        clean_legacy()
        validate()
    except Exception as exc:
        log(f"ERROR: {exc}")
        restore()
        print(f"\nFAILED AND RESTORED: {exc}")
        print(f"Report: {REPORT}")
        return 1

    print("\nValidation passed.")
    subprocess.run(["git", "status", "--short"], cwd=ROOT)
    print(f"\nBackup: {BACKUP}")
    if input("\nType PUSH to commit and push, or Enter to stop: ").strip() != "PUSH":
        print("Stopped before commit. Review with git status and git diff --stat.")
        return 0

    run(["git", "add", "-A"])
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=ROOT, text=True, capture_output=True,
    ).stdout.strip()
    if not staged:
        print("Nothing to commit.")
        return 0
    run(["git", "commit", "-m", "Remove legacy generator and reset Pages to current app"])
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=ROOT, text=True
    ).strip() or "main"
    run(["git", "push", "origin", branch])
    print("\nPushed. GitHub Pages should redeploy in 1-3 minutes.")
    print("https://dstogsdill1.github.io/Singh360_SmartDraw/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
