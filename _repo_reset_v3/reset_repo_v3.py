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
BACKUP = ROOT / ".docs" / "archive" / f"current_app_repo_reset_v3_{STAMP}"
REPORT = BACKUP / "cleanup_report.txt"
SUCCESS_FLAG = ROOT / ".reset_v3_success"
ARCHIVE_POINTER = ROOT / ".reset_v3_archive_path"

LEGACY_FILES = [
    "main_generator.py", "pipeline_cli.py", "config.py",
    "core/ingestion.py", "core/data_orchestrator.py", "core/schedule_adapter.py",
    "core/idf_builder.py", "core/model.py", "core/merge.py",
    "engines/smartdraw_vson.py", "engines/visio_vsdx.py",
    "engines/rdm_layout_xml.py", "engines/drawing_package.py",
    "engines/svg_diagram.py", "engines/spatial_layout.py", "engines/title_block.py",
]
LEGACY_DIRS = ["web", "core/extractors", "engines/doc_templates"]

KEEP_ROOT = {
    ".gitignore", "AGENTS.md", "README.md", "requirements.txt", "server.py",
    "start-local.ps1", "start-live.ps1", "START_SINGH360.bat",
    "RESET_TO_CURRENT_APP_V3.bat",
}
PREFIX_JUNK = (
    "README_", "ROLLBACK_", "INSTALL_", "RUN_", "PUBLISH_", "PUSH_",
    "OPEN_", "SEND_", "IMPORT_", "ENABLE_", "RESET_TO_CURRENT_APP",
)
NAME_JUNK = {
    "readme", "KANBAN.md", "Microsoft.Services.Store.winmd", "temp.py",
    "fix_dashboard.py", "singh360-rebuild-hero.png",
    "singh360-repaired-homepage-top.png",
}


def log(text: str = "") -> None:
    print(text)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    with REPORT.open("a", encoding="utf-8") as fh:
        fh.write(text + "\n")


def run(cmd: list[str], cwd: Path = ROOT, check: bool = True, env=None):
    log("$ " + " ".join(map(str, cmd)))
    result = subprocess.run(cmd, cwd=cwd, env=env)
    if check and result.returncode:
        raise RuntimeError(f"Command failed: {' '.join(map(str, cmd))}")
    return result


def backup(path: Path) -> None:
    if not path.exists():
        return
    dest = BACKUP / "files" / path.relative_to(ROOT)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        if path.is_dir():
            shutil.copytree(path, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(path, dest)
    except (PermissionError, OSError) as exc:
        log(f"Backup skipped for locked path {path.relative_to(ROOT)}: {exc}")


def add_gitignore(line: str) -> None:
    path = ROOT / ".gitignore"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if re.search(rf"(?m)^{re.escape(line)}$", text):
        return
    backup(path)
    with path.open("a", encoding="utf-8") as fh:
        fh.write("\n" + line + "\n")
    log(f"Added to .gitignore: {line}")


def git_remove_cached(rel: str) -> None:
    subprocess.run(
        ["git", "rm", "-r", "--cached", "-f", "--ignore-unmatch", "--", rel],
        cwd=ROOT,
        check=False,
    )
    add_gitignore(rel.rstrip("/") + "/")


def remove_file_or_dir(path: Path) -> None:
    if not path.exists():
        return
    backup(path)
    rel = path.relative_to(ROOT).as_posix()
    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        log(f"Removed (backed up): {rel}")
    except (PermissionError, OSError) as exc:
        log(f"Could not physically remove {rel}; leaving local ignored copy: {exc}")
        git_remove_cached(rel)


def replace(path: Path, template_name: str) -> None:
    backup(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TEMPLATES / template_name, path)
    log(f"Updated: {path.relative_to(ROOT).as_posix()}")


def repair_previous_failed_runs() -> None:
    for rel in ("RESET_TO_CURRENT_APP.bat", "ems"):
        subprocess.run(
            ["git", "restore", "--worktree", "--", rel],
            cwd=ROOT,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    log("Repaired residual tracked deletions from prior failed reset, when present.")


def patch_server() -> bool:
    path = ROOT / "server.py"
    text = path.read_text(encoding="utf-8-sig")
    old = text

    text = text.replace(
        "packages. The legacy /editor page is retained only as a fallback.",
        "packages.",
    )
    text = re.sub(r'^WEB_DIR\s*=\s*HERE\s*/\s*"web"\s*\n', "", text, flags=re.M)
    text = text.replace(', "/editor"', "").replace('"/editor", ', "")

    text = re.sub(
        r'\n@app\.get\("/editor"\)\ndef legacy_editor_index\(\):\n(?:[ \t]+.*\n)+',
        "\n",
        text,
        count=1,
    )
    text = re.sub(
        r'\n\s*<p>Legacy fallback editor remains available at <a href="/editor">/editor</a>\.</p>',
        "",
        text,
        count=1,
    )

    title_pattern = (
        r'def serve_title_block\(\):\n'
        r'(?:[ \t]+.*\n)+?'
        r'[ \t]+abort\(404\)'
    )
    title_replacement = (
        'def serve_title_block():\n'
        '    # Serve the master title block from the current repository root.\n'
        '    candidate = HERE / "title_block.png"\n'
        '    if candidate.is_file():\n'
        '        return send_file(candidate)\n'
        '    abort(404)'
    )
    text = re.sub(title_pattern, title_replacement, text, count=1)

    if text != old:
        backup(path)
        path.write_text(text, encoding="utf-8")
        log("Patched server.py: removed legacy editor/web fallback.")

    return "/editor" not in text and "WEB_DIR" not in text


def patch_smokes() -> None:
    routes = ROOT / "scripts" / "smoke_routes.py"
    if routes.exists():
        text = routes.read_text(encoding="utf-8")
        old = text
        text = re.sub(
            r'\n\s*r_editor = client\.get\("/editor"\)\n\s*print\(f"GET /editor.*?\n',
            "\n",
            text,
            count=1,
        )
        if text != old:
            backup(routes)
            routes.write_text(text, encoding="utf-8")
            log("Updated smoke_routes.py.")

    replace(
        ROOT / "scripts" / "smoke_component_library.py",
        "smoke_component_library.py",
    )


def clean_docs() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    for child in list(DOCS.iterdir()):
        if child.name != "component-library":
            remove_file_or_dir(child)
    replace(DOCS / "index.html", "docs_index.html")
    replace(DOCS / "README.md", "docs_README.md")
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")
    log("Created docs/.nojekyll")


def keep_ppt(path: Path) -> bool:
    name = path.name.lower()
    return path.suffix.lower() == ".pptx" and (
        "singh360_component_library_real" in name
        or "singh360 component library real" in name
    )


def clean_root() -> None:
    for path in list(ROOT.iterdir()):
        if not path.is_file() or path.name in KEEP_ROOT or keep_ppt(path):
            continue
        junk = (
            path.name in NAME_JUNK
            or path.name.startswith(PREFIX_JUNK)
            or path.suffix.lower() in {".zip", ".pdf", ".txt", ".pptx"}
        )
        if junk:
            remove_file_or_dir(path)

    for old_tool in ("_repo_reset", "_repo_reset_v2"):
        remove_file_or_dir(ROOT / old_tool)


def clean_legacy() -> None:
    server_clean = patch_server()
    patch_smokes()

    ems = ROOT / "ems"
    if ems.exists():
        log("Removing legacy ems/ from Git index; locked local copy may remain.")
        git_remove_cached("ems")
        archive_target = BACKUP / "locked_local_legacy" / "ems"
        archive_target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(ems), str(archive_target))
            log(f"Moved local ems/ to {archive_target}")
        except (PermissionError, OSError) as exc:
            log(f"Local ems/ remains ignored because Windows locked it: {exc}")

    for rel in LEGACY_FILES:
        remove_file_or_dir(ROOT / rel)
    for rel in LEGACY_DIRS:
        if rel == "web" and not server_clean:
            log("Kept web/: server still references it.")
            continue
        remove_file_or_dir(ROOT / rel)

    init_path = ROOT / "__init__.py"
    backup(init_path)
    init_path.write_text("# Singh360 Draft package\n", encoding="utf-8")
    log("Updated __init__.py")


def ensure_gitignore() -> None:
    for line in (
        ".docs/",
        "*.pptx",
        "Singh360_Component_Library_Real*.pptx",
        "Singh360 Component Library Real*.pptx",
        "ems/",
        "engines/doc_templates/",
    ):
        add_gitignore(line)


def restore() -> None:
    files = BACKUP / "files"
    if files.exists():
        log("Validation failed. Restoring file backup.")
        for src in sorted(files.rglob("*")):
            if src.is_file():
                dest = ROOT / src.relative_to(files)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
    subprocess.run(["git", "reset"], cwd=ROOT, check=False)
    repair_previous_failed_runs()
    log("Backup restored; no commit made.")


def validate() -> None:
    py = ROOT / ".venv" / "Scripts" / "python.exe"
    python = str(py) if py.exists() else sys.executable
    env = os.environ.copy()
    env["SINGH360_PORT"] = "8766"
    env["SINGH360_SKIP_SERVE"] = "1"

    run(
        [python, "-m", "compileall", "server.py", "core", "engines", "scripts"],
        env=env,
    )
    frontend = ROOT / "frontend"
    if (frontend / "package.json").exists():
        npm = "npm.cmd" if os.name == "nt" else "npm"
        run([npm, "run", "build"], cwd=frontend, env=env)

    for name in ("smoke_routes.py", "smoke_component_library.py"):
        smoke = ROOT / "scripts" / name
        if smoke.exists():
            run([python, str(smoke)], env=env)


def main() -> int:
    if not (ROOT / ".git").exists() or not (ROOT / "server.py").exists():
        print("Extract this pack into the Singh360_SmartDraw repository root.")
        return 1
    if not (DOCS / "component-library").exists():
        print("docs/component-library is missing. Publish the catalog first.")
        return 1

    SUCCESS_FLAG.unlink(missing_ok=True)
    repair_previous_failed_runs()

    BACKUP.mkdir(parents=True, exist_ok=True)
    ARCHIVE_POINTER.write_text(str(BACKUP), encoding="utf-8")
    log(f"Repository: {ROOT}")
    log(f"Backup: {BACKUP}")
    status = subprocess.run(
        ["git", "status", "--short"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    log("Git status before reset:")
    log(status.stdout.rstrip())

    print("\nV3 replaces the obsolete legacy-library smoke with a current /api/lib smoke.")
    print("It also repairs the leftover deletions from the failed V2 run.")
    print("Everything removed is backed up first.")
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
        cwd=ROOT,
        text=True,
        capture_output=True,
    ).stdout.strip()
    if not staged:
        print("Nothing to commit.")
        return 0

    run(
        [
            "git",
            "commit",
            "-m",
            "Remove legacy generator and reset Pages to current app",
        ]
    )
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"],
        cwd=ROOT,
        text=True,
    ).strip() or "main"
    run(["git", "push", "origin", branch])

    SUCCESS_FLAG.write_text("ok", encoding="utf-8")
    print("\nPushed. GitHub Pages should redeploy in 1-3 minutes.")
    print("https://dstogsdill1.github.io/Singh360_SmartDraw/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
