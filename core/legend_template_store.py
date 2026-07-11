"""core/legend_template_store.py — editable symbol legend templates.

Storage:
    .docs/library/legend_templates/
        manifest.json
        <template_id>.json
"""
from __future__ import annotations

import json
import re
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slug(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (name or "").strip()).strip("-")
    return s[:48] or "legend"


class LegendTemplateStore:
    def __init__(self, docs_dir: Path) -> None:
        self.root = docs_dir / "library" / "legend_templates"
        self.manifest_path = self.root / "manifest.json"
        self.ensure()

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        if not self.manifest_path.exists():
            self.manifest_path.write_text(
                json.dumps({"version": 1, "templates": []}, indent=2),
                encoding="utf-8",
            )

    def _read_manifest(self) -> dict[str, Any]:
        self.ensure()
        try:
            return json.loads(self.manifest_path.read_text(encoding="utf-8-sig"))
        except Exception:
            return {"version": 1, "templates": []}

    def _write_manifest(self, data: dict[str, Any]) -> None:
        self.manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def list_templates(self) -> list[dict[str, Any]]:
        manifest = self._read_manifest()
        return list(manifest.get("templates") or [])

    def get_template(self, template_id: str) -> dict[str, Any] | None:
        path = self.root / f"{template_id}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            return None

    def save_template(
        self,
        *,
        name: str,
        category: str,
        title: str,
        rows: list[dict[str, Any]],
        template_id: str | None = None,
    ) -> dict[str, Any]:
        self.ensure()
        manifest = self._read_manifest()
        entries = list(manifest.get("templates") or [])
        tid = template_id or f"{_slug(name)}-{uuid.uuid4().hex[:8]}"
        payload = {
            "id": tid,
            "name": name.strip() or "Symbol Legend",
            "category": category or "custom",
            "title": title or "Symbol Legend",
            "rows": deepcopy(rows),
            "layout": {
                "background": "#ffffff",
                "border": "#333333",
                "fontSize": 9,
                "rowHeight": 28,
                "iconWidth": 32,
            },
            "updatedAt": _ts(),
        }
        (self.root / f"{tid}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        entry = {
            "id": tid,
            "name": payload["name"],
            "category": payload["category"],
            "rowCount": len(rows),
            "updatedAt": payload["updatedAt"],
        }
        entries = [e for e in entries if e.get("id") != tid]
        entries.insert(0, entry)
        manifest["templates"] = entries
        self._write_manifest(manifest)
        return entry

    def delete_template(self, template_id: str) -> bool:
        manifest = self._read_manifest()
        entries = [e for e in (manifest.get("templates") or []) if e.get("id") != template_id]
        if len(entries) == len(manifest.get("templates") or []):
            return False
        manifest["templates"] = entries
        self._write_manifest(manifest)
        path = self.root / f"{template_id}.json"
        if path.exists():
            path.unlink()
        return True

    def rename_template(self, template_id: str, new_name: str) -> bool:
        payload = self.get_template(template_id)
        if payload is None:
            return False
        payload["name"] = new_name.strip() or payload.get("name", "Symbol Legend")
        payload["updatedAt"] = _ts()
        (self.root / f"{template_id}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        manifest = self._read_manifest()
        for e in manifest.get("templates") or []:
            if e.get("id") == template_id:
                e["name"] = payload["name"]
                e["updatedAt"] = payload["updatedAt"]
                break
        self._write_manifest(manifest)
        return True
