"""Reusable page-template storage for Singh360 Draft.

Templates are project-independent. Saving the same template name updates the
existing template instead of creating another duplicate.
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

_STRIP_ON_SAVE = {
    "id",
    "order",
    "include",
    "sheetCode",
    "displaySheetCode",
    "sheetTab",
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
    "renderMode",
    "sourceSheet",
    "sourceRange",
    "printArea",
}

_NESTED_SOURCE_KEYS = {
    "sourceWorksheetId",
    "sourceSheet",
    "sourceRange",
}


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonical_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip()).casefold()


def _safe_entry_time(entry: dict[str, Any]) -> str:
    return str(entry.get("updatedAt") or entry.get("createdAt") or "")


def _remove_nested_source_links(value: Any) -> Any:
    if isinstance(value, list):
        return [_remove_nested_source_links(item) for item in value]
    if not isinstance(value, dict):
        return value
    return {
        key: _remove_nested_source_links(item)
        for key, item in value.items()
        if key not in _NESTED_SOURCE_KEYS
    }


class PageTemplateStore:
    def __init__(self, docs_dir: Path) -> None:
        self.docs_dir = Path(docs_dir)
        self.root = self.docs_dir / "library" / "page_templates"
        self.thumb_dir = self.root / "thumbnails"
        self.manifest_path = self.root / "manifest.json"
        self.ensure()

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.thumb_dir.mkdir(parents=True, exist_ok=True)
        if not self.manifest_path.exists():
            self.manifest_path.write_text(
                json.dumps({"version": 2, "templates": []}, indent=2),
                encoding="utf-8",
            )

    def _read_manifest(self) -> dict[str, Any]:
        self.ensure()
        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except Exception:
            data = {"version": 2, "templates": []}
        if not isinstance(data, dict):
            data = {"version": 2, "templates": []}
        if not isinstance(data.get("templates"), list):
            data["templates"] = []
        return data

    def _write_manifest(self, data: dict[str, Any]) -> None:
        data["version"] = 2
        self.manifest_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _payload_path(self, template_id: str) -> Path:
        return self.root / f"{template_id}.json"

    def _delete_files(self, template_id: str) -> None:
        for path in (
            self._payload_path(template_id),
            self.thumb_dir / f"{template_id}.png",
        ):
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                pass

    def repair_duplicates(self) -> dict[str, int]:
        """Collapse duplicate names and remove orphaned manifest/files.

        The newest entry for each case-insensitive, whitespace-normalized name
        wins. This repairs the duplicates already created by older builds.
        """
        manifest = self._read_manifest()
        entries = [entry for entry in manifest.get("templates") or [] if isinstance(entry, dict)]

        newest_by_name: dict[str, dict[str, Any]] = {}
        duplicates: list[dict[str, Any]] = []

        for entry in entries:
            template_id = str(entry.get("id") or "")
            if not template_id or not self._payload_path(template_id).is_file():
                duplicates.append(entry)
                continue
            key = _canonical_name(str(entry.get("name") or template_id))
            prior = newest_by_name.get(key)
            if prior is None:
                newest_by_name[key] = entry
                continue
            if _safe_entry_time(entry) >= _safe_entry_time(prior):
                duplicates.append(prior)
                newest_by_name[key] = entry
            else:
                duplicates.append(entry)

        kept = list(newest_by_name.values())
        kept_ids = {str(entry.get("id") or "") for entry in kept}

        removed_ids: set[str] = set()
        for duplicate in duplicates:
            template_id = str(duplicate.get("id") or "")
            if template_id and template_id not in kept_ids:
                removed_ids.add(template_id)
                self._delete_files(template_id)

        for payload in self.root.glob("*.json"):
            if payload.name == self.manifest_path.name:
                continue
            if payload.stem not in kept_ids:
                removed_ids.add(payload.stem)
                self._delete_files(payload.stem)

        changed = kept != entries or bool(removed_ids) or manifest.get("version") != 2
        if changed:
            manifest["templates"] = kept
            self._write_manifest(manifest)

        return {
            "kept": len(kept),
            "removed": len(removed_ids),
        }

    def list_templates(self) -> list[dict[str, Any]]:
        self.repair_duplicates()
        manifest = self._read_manifest()
        out: list[dict[str, Any]] = []
        for entry in manifest.get("templates") or []:
            if not isinstance(entry, dict):
                continue
            template_id = str(entry.get("id") or "")
            thumbnail = self.thumb_dir / f"{template_id}.png"
            out.append(
                {
                    **entry,
                    "hasThumbnail": thumbnail.exists(),
                    "thumbnailUrl": (
                        f"/api/lib/page-templates/{template_id}/thumbnail"
                        if thumbnail.exists()
                        else None
                    ),
                }
            )
        return sorted(out, key=lambda entry: (entry.get("name") or "").casefold())

    def get_template(self, template_id: str) -> dict[str, Any] | None:
        path = self._payload_path(template_id)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    def save_template(
        self,
        page: dict[str, Any],
        name: str,
        *,
        thumbnail_png: bytes | None = None,
        template_id: str | None = None,
    ) -> dict[str, Any]:
        self.ensure()
        self.repair_duplicates()

        clean_name = (name or page.get("sheetTitle") or "Page Template").strip() or "Page Template"
        canonical = _canonical_name(clean_name)
        manifest = self._read_manifest()
        templates: list[dict[str, Any]] = [
            entry for entry in (manifest.get("templates") or []) if isinstance(entry, dict)
        ]

        existing = next(
            (
                entry
                for entry in templates
                if _canonical_name(str(entry.get("name") or "")) == canonical
            ),
            None,
        )

        template_id = template_id or (str(existing.get("id")) if existing else None)
        template_id = template_id or uuid.uuid4().hex[:12]

        payload = deepcopy(page)
        for key in _STRIP_ON_SAVE:
            payload.pop(key, None)
        payload = _remove_nested_source_links(payload)
        payload["templateName"] = clean_name
        payload["savedAt"] = _ts()

        canvas_objects = payload.get("canvasObjects")
        if isinstance(canvas_objects, list) and canvas_objects:
            page_type = str(payload.get("pageType") or "")
            if page_type not in {"hybrid", "underlay"}:
                payload["pageType"] = "canvas"

        self._payload_path(template_id).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        thumbnail_path = self.thumb_dir / f"{template_id}.png"
        if thumbnail_png:
            thumbnail_path.write_bytes(thumbnail_png)

        now = _ts()
        created_at = str(existing.get("createdAt")) if existing else now
        entry = {
            "id": template_id,
            "name": clean_name,
            "createdAt": created_at,
            "updatedAt": now,
            "pageType": payload.get("pageType", "canvas"),
            "layoutProfile": payload.get("layoutProfile", ""),
            "dimensions": {"templateId": payload.get("templateId", "ansi-b-standard")},
            "hasThumbnail": thumbnail_path.exists(),
        }

        templates = [
            item
            for item in templates
            if str(item.get("id") or "") != template_id
            and _canonical_name(str(item.get("name") or "")) != canonical
        ]
        templates.append(entry)
        manifest["templates"] = templates
        self._write_manifest(manifest)

        return {
            **entry,
            "thumbnailUrl": (
                f"/api/lib/page-templates/{template_id}/thumbnail"
                if thumbnail_path.exists()
                else None
            ),
        }

    def rename_template(self, template_id: str, new_name: str) -> bool:
        manifest = self._read_manifest()
        clean_name = new_name.strip()
        if not clean_name:
            return False

        found = False
        for entry in manifest.get("templates") or []:
            if isinstance(entry, dict) and entry.get("id") == template_id:
                entry["name"] = clean_name
                entry["updatedAt"] = _ts()
                found = True
                break
        if not found:
            return False

        self._write_manifest(manifest)
        path = self._payload_path(template_id)
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                payload["templateName"] = clean_name
                payload["savedAt"] = _ts()
                path.write_text(
                    json.dumps(payload, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            except Exception:
                pass

        self.repair_duplicates()
        return True

    def delete_template(self, template_id: str) -> bool:
        manifest = self._read_manifest()
        before = len(manifest.get("templates") or [])
        manifest["templates"] = [
            entry
            for entry in (manifest.get("templates") or [])
            if not isinstance(entry, dict) or entry.get("id") != template_id
        ]
        if len(manifest["templates"]) == before:
            return False
        self._write_manifest(manifest)
        self._delete_files(template_id)
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
        page_id = new_page_id or f"page_{uuid.uuid4().hex[:12]}"
        page["id"] = page_id
        page["order"] = order
        page["include"] = True
        page["sheetCode"] = sheet_code
        page["displaySheetCode"] = sheet_code
        page["sheetTitle"] = sheet_title or payload.get("templateName") or "From Template"
        page["sheetTab"] = ""
        page["pageGroupId"] = page_id
        page["continuationOf"] = None
        page["continuationIndex"] = 0
        page["generatedContinuation"] = False
        page["canvasObjects"] = list(page.get("canvasObjects") or [])
        page["blocks"] = list(page.get("blocks") or [])
        page.pop("renderMode", None)
        page.pop("linkedWorksheetId", None)
        return page

    @staticmethod
    def decode_thumbnail_data_url(data_url: str) -> bytes | None:
        if not data_url or "," not in data_url:
            return None
        try:
            header, raw = data_url.split(",", 1)
            if "base64" not in header.lower():
                return None
            return base64.b64decode(raw, validate=True)
        except Exception:
            return None
