"""core/page_template_store.py — PHASE F: user-saved reusable page templates.

Storage layout (mirrors component library V2 conventions):

    .docs/library/page_templates/
        manifest.json
        <template_id>.json
        thumbnails/<template_id>.png   (optional)
"""
from __future__ import annotations

import base64
import json
import re
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Fields stripped when saving a page as a template (project-specific identity).
_STRIP_ON_SAVE = {
    "id",
    "order",
    "include",
    "sheetCode",
    "displaySheetCode",
    "linkedWorksheetId",
    "pageGroupId",
    "continuationOf",
    "continuationIndex",
    "generatedContinuation",
    "pageNumber",
    "pageTotal",
    "sourceRevision",
    "importedFrom",
    "layoutWarnings",
    "archivedAt",
}


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slug(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (name or "").strip()).strip("-")
    return s[:48] or "template"


class PageTemplateStore:
    def __init__(self, docs_dir: Path) -> None:
        self.root = docs_dir / "library" / "page_templates"
        self.thumb_dir = self.root / "thumbnails"
        self.manifest_path = self.root / "manifest.json"
        self.ensure()

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.thumb_dir.mkdir(parents=True, exist_ok=True)
        if not self.manifest_path.exists():
            self.manifest_path.write_text(
                json.dumps({"version": 1, "templates": []}, indent=2),
                encoding="utf-8",
            )

    def _read_manifest(self) -> dict[str, Any]:
        self.ensure()
        try:
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return {"version": 1, "templates": []}

    def _write_manifest(self, data: dict[str, Any]) -> None:
        self.manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def list_templates(self) -> list[dict[str, Any]]:
        manifest = self._read_manifest()
        out: list[dict[str, Any]] = []
        for entry in manifest.get("templates") or []:
            tid = entry.get("id", "")
            thumb = self.thumb_dir / f"{tid}.png"
            out.append(
                {
                    **entry,
                    "hasThumbnail": thumb.exists(),
                    "thumbnailUrl": f"/api/lib/page-templates/{tid}/thumbnail" if thumb.exists() else None,
                }
            )
        return sorted(out, key=lambda e: (e.get("name") or "").lower())

    def _payload_path(self, template_id: str) -> Path:
        return self.root / f"{template_id}.json"

    def get_template(self, template_id: str) -> dict[str, Any] | None:
        path = self._payload_path(template_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def save_template(
        self,
        page: dict[str, Any],
        name: str,
        *,
        thumbnail_png: bytes | None = None,
        template_id: str | None = None,
    ) -> dict[str, Any]:
        self.ensure()
        tid = template_id or uuid.uuid4().hex[:12]
        clean_name = (name or page.get("sheetTitle") or "Page Template").strip() or "Page Template"
        payload = deepcopy(page)
        for key in _STRIP_ON_SAVE:
            payload.pop(key, None)
        payload["templateName"] = clean_name
        payload["savedAt"] = _ts()

        self._payload_path(tid).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        if thumbnail_png:
            (self.thumb_dir / f"{tid}.png").write_bytes(thumbnail_png)

        manifest = self._read_manifest()
        templates: list[dict[str, Any]] = list(manifest.get("templates") or [])
        entry = {
            "id": tid,
            "name": clean_name,
            "createdAt": _ts(),
            "pageType": page.get("pageType", "canvas"),
            "layoutProfile": page.get("layoutProfile", ""),
            "dimensions": {"templateId": page.get("templateId", "ansi-b-standard")},
            "hasThumbnail": bool(thumbnail_png),
        }
        templates = [t for t in templates if t.get("id") != tid]
        templates.append(entry)
        manifest["templates"] = templates
        self._write_manifest(manifest)
        return entry

    def rename_template(self, template_id: str, new_name: str) -> bool:
        manifest = self._read_manifest()
        found = False
        for entry in manifest.get("templates") or []:
            if entry.get("id") == template_id:
                entry["name"] = new_name.strip() or entry.get("name", "Template")
                found = True
                break
        if not found:
            return False
        self._write_manifest(manifest)
        path = self._payload_path(template_id)
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                payload["templateName"] = new_name.strip()
                path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            except Exception:
                pass
        return True

    def delete_template(self, template_id: str) -> bool:
        manifest = self._read_manifest()
        before = len(manifest.get("templates") or [])
        manifest["templates"] = [
            t for t in (manifest.get("templates") or []) if t.get("id") != template_id
        ]
        if len(manifest["templates"]) == before:
            return False
        self._write_manifest(manifest)
        path = self._payload_path(template_id)
        if path.exists():
            path.unlink()
        thumb = self.thumb_dir / f"{template_id}.png"
        if thumb.exists():
            thumb.unlink()
        return True

    def page_from_template(
        self,
        template_id: str,
        *,
        new_page_id: str | None = None,
        order: int = 1,
        sheet_code: str = "NEW",
        sheet_title: str | None = None,
    ) -> dict[str, Any] | None:
        payload = self.get_template(template_id)
        if payload is None:
            return None
        page = deepcopy(payload)
        page["id"] = new_page_id or f"page_{uuid.uuid4().hex[:12]}"
        page["order"] = order
        page["include"] = True
        page["sheetCode"] = sheet_code
        page["displaySheetCode"] = sheet_code
        page["sheetTitle"] = sheet_title or payload.get("templateName") or "From Template"
        page["pageGroupId"] = page["id"]
        page["continuationOf"] = None
        page["continuationIndex"] = 0
        page["generatedContinuation"] = False
        page["canvasObjects"] = list(page.get("canvasObjects") or [])
        page["blocks"] = list(page.get("blocks") or [])
        return page

    @staticmethod
    def decode_thumbnail_data_url(data_url: str) -> bytes | None:
        if not data_url or "," not in data_url:
            return None
        try:
            raw = data_url.split(",", 1)[1]
            return base64.b64decode(raw)
        except Exception:
            return None
