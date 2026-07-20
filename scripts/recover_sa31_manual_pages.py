"""Recover SA31 manual drawing pages from the newest valid project backup.

This script is intentionally narrow:
- restores only EMS 18.0 (LCP-1 Wiring Schematic)
- restores only EMS 20.0 (Interior Device Location)
- leaves EMS 19.0 and every unrelated page unchanged
- never reimports a workbook
- backs up the current project before writing
- refuses to save unless both recovered pages contain real manual content

It also exposes a manual-page matching guard for future SA31 workbook refreshes.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_PROJECT_ID = "4acaef6006dd4620"
TARGETS = {
    "EMS 18.0": ("lcp-1", "wiring", "schematic"),
    "EMS 20.0": ("interior", "device", "location"),
}
MANUAL_TYPES = {"canvas", "hybrid", "underlay", "image", "image-layout"}
PLACEHOLDER_PHRASES = {
    "drawing to be inserted",
    "image to be inserted",
    "insert/crop pdf schematic in app as needed",
    "manual plan/device location page",
}


class RecoveryError(RuntimeError):
    pass


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def _code(page: dict[str, Any]) -> str:
    return str(page.get("displaySheetCode") or page.get("sheetCode") or "").strip()


def _title_blob(page: dict[str, Any]) -> str:
    return _norm(" ".join([
        str(page.get("sheetTitle") or ""),
        str(page.get("sheetTab") or ""),
        str(page.get("sourceSheet") or ""),
        str(page.get("notes") or ""),
    ]))


def _block_text(page: dict[str, Any]) -> str:
    values: list[str] = []
    for block in page.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        values.append(str(block.get("text") or ""))
        for key in ("grid", "rows"):
            for row in block.get(key) or []:
                if isinstance(row, list):
                    values.extend(str(cell or "") for cell in row)
    return _norm(" ".join(values))


def _manual_score(page: dict[str, Any]) -> int:
    score = 0
    canvas = page.get("canvasObjects")
    if isinstance(canvas, list):
        score += 120 * len(canvas)
        for obj in canvas:
            if not isinstance(obj, dict):
                continue
            if str(obj.get("src") or obj.get("url") or "").strip():
                score += 80
            if str(obj.get("type") or "").lower() in {"image", "fabricimage"}:
                score += 40

    assets = page.get("assets")
    if isinstance(assets, list):
        score += 50 * len(assets)

    underlays = page.get("underlays")
    if isinstance(underlays, list):
        score += 50 * len(underlays)

    for block in page.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type") or "").lower()
        if block_type in {"image", "canvas", "underlay", "imageplaceholder", "underlayplaceholder"}:
            score += 60
        if str(block.get("src") or block.get("url") or "").strip():
            score += 80

    if str(page.get("pageType") or "").lower() in MANUAL_TYPES:
        score += 20

    text = _block_text(page)
    if text and not all(phrase in text for phrase in PLACEHOLDER_PHRASES):
        score += min(30, len(text) // 20)

    if any(phrase in text for phrase in PLACEHOLDER_PHRASES) and score < 100:
        score -= 100

    return score


def _is_real_manual(page: dict[str, Any]) -> bool:
    return _manual_score(page) >= 100


def _page_digest(page: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(page, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _find_page(project: dict[str, Any], code: str, keywords: tuple[str, ...]) -> dict[str, Any] | None:
    pages = [page for page in project.get("pages") or [] if isinstance(page, dict)]

    exact = [
        page for page in pages
        if _norm(_code(page)) == _norm(code)
    ]
    if exact:
        return max(exact, key=_manual_score)

    keyword_matches = [
        page for page in pages
        if all(keyword in _title_blob(page) for keyword in keywords)
    ]
    if keyword_matches:
        return max(keyword_matches, key=_manual_score)

    return None


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RecoveryError(f"Could not read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RecoveryError(f"Project file is not a JSON object: {path}")
    return value


def _backup_candidates(repo: Path, current_path: Path) -> list[Path]:
    root = repo / ".docs" / "patch_backups"
    candidates: list[Path] = []
    if root.is_dir():
        candidates.extend(root.glob("sa31_full_workbook_refresh_*/project.json"))
        candidates.extend(root.glob("lcp_panel_split_*/project.json"))
        candidates.extend(root.glob("**/project.json"))

    unique: dict[Path, Path] = {}
    for path in candidates:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved == current_path.resolve() or not path.is_file():
            continue
        unique[resolved] = path

    return sorted(
        unique.values(),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def _find_recovery_source(
    repo: Path,
    current_path: Path,
) -> tuple[Path, dict[str, Any], dict[str, dict[str, Any]]]:
    inspected: list[str] = []

    for path in _backup_candidates(repo, current_path):
        try:
            project = _load_json(path)
        except RecoveryError:
            continue

        recovered: dict[str, dict[str, Any]] = {}
        summary: list[str] = []
        for code, keywords in TARGETS.items():
            page = _find_page(project, code, keywords)
            score = _manual_score(page) if page else 0
            summary.append(f"{code}={score}")
            if page and _is_real_manual(page):
                recovered[code] = page

        inspected.append(f"{path}: {', '.join(summary)}")
        if len(recovered) == len(TARGETS):
            return path, project, recovered

    details = "\n".join(inspected[:20]) or "No project backups were found."
    raise RecoveryError(
        "No single project backup contained both a real LCP-1 schematic and a real "
        "Interior Device Location page.\nInspected backups:\n" + details
    )


def _restore_page_payload(
    current_page: dict[str, Any],
    backup_page: dict[str, Any],
    code: str,
) -> dict[str, Any]:
    restored = copy.deepcopy(backup_page)

    restored["id"] = current_page.get("id") or backup_page.get("id")
    restored["order"] = current_page.get("order")
    restored["include"] = True
    restored["sheetCode"] = code
    restored["displaySheetCode"] = code

    for key in ("pageNumber", "pageTotal"):
        if key in current_page:
            restored[key] = current_page[key]

    restored["pageGroupId"] = restored["id"]
    restored["continuationOf"] = None
    restored["continuationIndex"] = 0
    restored["generatedContinuation"] = False
    return restored


def recover_pages(repo: Path, project_id: str, *, apply: bool) -> dict[str, Any]:
    from core.project_store import ProjectStore

    docs = repo / ".docs"
    store = ProjectStore(docs)
    current = store.load(project_id)
    if current is None:
        raise RecoveryError(f"Project {project_id} was not found.")

    current_path = store.read_path(project_id)
    if current_path is None or not current_path.is_file():
        raise RecoveryError(f"Could not locate the active project.json for {project_id}.")

    source_path, _, source_pages = _find_recovery_source(repo, current_path)

    current_pages = [
        copy.deepcopy(page)
        for page in current.get("pages") or []
        if isinstance(page, dict)
    ]
    before_digests = {
        str(page.get("id") or f"order-{page.get('order')}"): _page_digest(page)
        for page in current_pages
    }

    restored_codes: list[str] = []
    result_pages: list[dict[str, Any]] = []
    for page in current_pages:
        code = _code(page)
        target_code = next(
            (candidate for candidate in TARGETS if _norm(candidate) == _norm(code)),
            None,
        )
        if not target_code:
            result_pages.append(page)
            continue

        restored = _restore_page_payload(page, source_pages[target_code], target_code)
        result_pages.append(restored)
        restored_codes.append(target_code)

    for code in TARGETS:
        if code in restored_codes:
            continue
        backup_page = source_pages[code]
        order = 1 + max(
            (
                int(page.get("order") or 0)
                for page in result_pages
                if _norm(_code(page)) < _norm(code)
            ),
            default=0,
        )
        placeholder = {
            "id": f"recovered_{code.lower().replace(' ', '_').replace('.', '_')}",
            "order": order,
            "pageNumber": order,
            "pageTotal": len(result_pages) + 1,
        }
        result_pages.append(_restore_page_payload(placeholder, backup_page, code))
        restored_codes.append(code)

    result_pages.sort(key=lambda page: int(page.get("order") or 0))
    for order, page in enumerate(result_pages, start=1):
        page["order"] = order
        page["pageNumber"] = order
        page["pageTotal"] = len(result_pages)

    repaired = copy.deepcopy(current)
    repaired["pages"] = result_pages

    verification: dict[str, Any] = {}
    for code, keywords in TARGETS.items():
        page = _find_page(repaired, code, keywords)
        if page is None or not _is_real_manual(page):
            raise RecoveryError(f"Recovered {code} still does not contain real manual content.")
        verification[code] = {
            "title": page.get("sheetTitle"),
            "score": _manual_score(page),
            "canvasObjects": len(page.get("canvasObjects") or []),
            "assets": len(page.get("assets") or []),
            "blocks": len(page.get("blocks") or []),
        }

    target_ids = {
        str(page.get("id") or "")
        for page in result_pages
        if _norm(_code(page)) in {_norm(code) for code in TARGETS}
    }
    changed_unrelated: list[str] = []
    for page in result_pages:
        page_id = str(page.get("id") or "")
        if page_id in target_ids:
            continue
        before = before_digests.get(page_id)
        if before and before != _page_digest(page):
            changed_unrelated.append(f"{_code(page)} ({page_id})")
    if changed_unrelated:
        raise RecoveryError(
            "The recovery would change unrelated pages: " + ", ".join(changed_unrelated)
        )

    if not apply:
        print(f"[DRY RUN] Recovery source: {source_path}")
        print(json.dumps(verification, indent=2))
        return {
            "source": str(source_path),
            "verification": verification,
            "applied": False,
        }

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = docs / "patch_backups" / f"manual_page_recovery_{project_id}_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(current_path, backup_dir / "project.json")

    repaired["lastSavedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    saved_path = store.save(project_id, repaired)

    print(f"[OK] Recovery source backup: {source_path}")
    print(f"[OK] Current-project safety backup: {backup_dir}")
    print(f"[OK] Restored pages: {', '.join(restored_codes)}")
    print(f"[OK] Saved repaired project: {saved_path}")
    print(json.dumps(verification, indent=2))

    return {
        "source": str(source_path),
        "backup": str(backup_dir),
        "savedPath": str(saved_path),
        "verification": verification,
        "applied": True,
    }


def _manual_candidate(page: dict[str, Any]) -> bool:
    if str(page.get("pageType") or "").lower() in MANUAL_TYPES:
        return True
    for block in page.get("blocks") or []:
        if isinstance(block, dict) and str(block.get("type") or "").lower() in {
            "canvas", "image", "imageplaceholder", "underlay", "underlayplaceholder"
        }:
            return True
    return False


def install_manual_page_guard(refresh_core_module: Any) -> None:
    if getattr(refresh_core_module, "_manual_guard_installed", False):
        return

    original_match = refresh_core_module._match_existing
    original_merge = refresh_core_module.merge_projects

    def safe_match(
        candidate_page: dict[str, Any],
        existing_pages: list[dict[str, Any]],
        used: set[str],
    ) -> dict[str, Any] | None:
        code = _norm(_code(candidate_page))
        exact = next(
            (
                page for page in existing_pages
                if str(page.get("id") or "") not in used
                and _norm(_code(page)) == code
            ),
            None,
        )
        if exact is not None:
            return exact

        if _manual_candidate(candidate_page):
            return None

        return original_match(candidate_page, existing_pages, used)

    def safe_merge(
        existing: dict[str, Any],
        candidate: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        old_match = refresh_core_module._match_existing
        refresh_core_module._match_existing = safe_match
        try:
            result, summary = original_merge(existing, candidate)
        finally:
            refresh_core_module._match_existing = old_match

        final_pages = result.get("pages") or []
        final_ids = {str(page.get("id") or "") for page in final_pages if isinstance(page, dict)}
        final_codes = {_norm(_code(page)) for page in final_pages if isinstance(page, dict)}

        preserved: list[str] = []
        for old_page in existing.get("pages") or []:
            if not isinstance(old_page, dict) or not _is_real_manual(old_page):
                continue
            page_id = str(old_page.get("id") or "")
            page_code = _norm(_code(old_page))
            if page_id in final_ids or page_code in final_codes:
                continue
            final_pages.append(copy.deepcopy(old_page))
            preserved.append(_code(old_page))

        if preserved:
            final_pages.sort(key=lambda page: int(page.get("order") or 0))
            for order, page in enumerate(final_pages, start=1):
                page["order"] = order
            result["pages"] = final_pages

            archived = result.get("archivedPages") or []
            preserved_ids = {
                str(page.get("id") or "")
                for page in final_pages
            }
            result["archivedPages"] = [
                page for page in archived
                if str(page.get("id") or "") not in preserved_ids
            ]
            summary["preservedUnindexedManual"] = preserved

        return result, summary

    refresh_core_module._match_existing = safe_match
    refresh_core_module.merge_projects = safe_merge
    refresh_core_module._manual_guard_installed = True


def self_test() -> None:
    good_lcp = {
        "id": "lcp1",
        "order": 1,
        "sheetCode": "EMS 18.0",
        "displaySheetCode": "EMS 18.0",
        "sheetTitle": "LCP-1 Wiring Schematic",
        "pageType": "canvas",
        "canvasObjects": [{"type": "image", "src": "/assets/lcp1.png"}],
        "blocks": [],
    }
    good_interior = {
        "id": "interior",
        "order": 2,
        "sheetCode": "EMS 20.0",
        "displaySheetCode": "EMS 20.0",
        "sheetTitle": "Interior Device Location",
        "pageType": "canvas",
        "canvasObjects": [{"type": "image", "src": "/assets/interior.png"}],
        "blocks": [],
    }
    blank_lcp = {
        "id": "current18",
        "order": 1,
        "sheetCode": "EMS 18.0",
        "displaySheetCode": "EMS 18.0",
        "sheetTitle": "LCP-1 Wiring Schematic",
        "pageType": "canvas",
        "canvasObjects": [],
        "blocks": [{"type": "imagePlaceholder", "text": "DRAWING TO BE INSERTED"}],
    }
    wrong_interior = {
        "id": "current20",
        "order": 2,
        "sheetCode": "EMS 20.0",
        "displaySheetCode": "EMS 20.0",
        "sheetTitle": "Interior Device Location",
        "pageType": "canvas",
        "canvasObjects": [{"type": "image", "src": "/assets/lcp1.png"}],
        "blocks": [],
    }

    assert _is_real_manual(good_lcp)
    assert _is_real_manual(good_interior)
    assert not _is_real_manual(blank_lcp)

    restored18 = _restore_page_payload(blank_lcp, good_lcp, "EMS 18.0")
    restored20 = _restore_page_payload(wrong_interior, good_interior, "EMS 20.0")
    assert restored18["id"] == "current18"
    assert restored18["canvasObjects"][0]["src"].endswith("lcp1.png")
    assert restored20["id"] == "current20"
    assert restored20["canvasObjects"][0]["src"].endswith("interior.png")
    print("[OK] Manual-page recovery and identity-preservation self-test")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=str(ROOT))
    parser.add_argument("--project", default=DEFAULT_PROJECT_ID)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0

    repo = Path(args.repo).expanduser().resolve()
    if not (repo / "server.py").is_file():
        raise RecoveryError(f"Singh360 repository not found: {repo}")

    recover_pages(repo, args.project, apply=args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
