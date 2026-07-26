"""Transactional creation and backup services for schema-V2 projects."""
from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from .project_store import ProjectStore, slugify
from .template_platform import (
    ProfileRegistry, TemplatePlatformError, TemplateRegistry,
    WorkbookDocumentStore, apply_standard_sheet_style, atomic_json_write,
    sha256_file, utcnow, workbook_to_document,
)


class ProjectTemplateService:
    def __init__(self, store: ProjectStore, profiles: ProfileRegistry, templates: TemplateRegistry):
        self.store = store
        self.profiles = profiles
        self.templates = templates

    def create(self, body: dict[str, Any]) -> dict[str, Any]:
        profile = self.profiles.get(str(body.get("profileId") or ""))
        template = self.templates.get(str(body.get("templateId") or ""))
        if profile["id"] not in template.get("supportedProfiles", []):
            raise TemplatePlatformError(f"Template does not support profile {profile['id']}.")
        metadata = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}
        name = str(metadata.get("projectName") or "").strip()
        if not name:
            raise TemplatePlatformError("Project name is required.")
        project_id = uuid.uuid4().hex[:16]
        project_dir = self.store.projects_dir / f"{slugify(name)}__{project_id}"
        if project_dir.exists():
            raise TemplatePlatformError("Generated project folder already exists; retry creation.")
        try:
            self.store.ensure_folders(project_dir)
            source_template = Path(template["absoluteRuntimePath"])
            workbook_path = project_dir / "sources" / "workbook" / source_template.name
            shutil.copy2(source_template, workbook_path)
            self._apply_profile(workbook_path, profile, metadata, project_id)
            document = workbook_to_document(workbook_path)
            WorkbookDocumentStore(project_dir).create(document)
            source_manifest = {"schemaVersion": 1, "sources": [], "conversionQueue": []}
            atomic_json_write(project_dir / "source_library.json", source_manifest)
            project = {
                "id": project_id, "schemaVersion": 2, "metadata": metadata,
                "projectProfileId": profile["id"], "projectTemplateId": template["templateId"],
                "projectTemplateVersion": template["version"], "projectTemplateHash": template["sha256"],
                "workbookDocument": {"path": "data/workbook.json", "revision": document["revision"]},
                "sourceLibrary": {"path": "source_library.json"}, "worksheets": [],
                "pages": [], "sources": [], "lastCompile": None, "compileWarnings": [],
                "sourceWorkbookName": workbook_path.name,
                "workbookSync": {"mode": "project-workbook", "workbook": str(workbook_path), "status": "in_sync", "workbookHash": sha256_file(workbook_path)},
                "createdAt": utcnow(),
            }
            self.store.save(project_id, project)
            return project
        except Exception as exc:
            failure_root = self.store.docs / "failure_logs"
            failure_root.mkdir(parents=True, exist_ok=True)
            atomic_json_write(failure_root / f"project_create_{project_id}_{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.json", {
                "projectId": project_id, "projectFolder": str(project_dir), "error": str(exc), "failedAt": utcnow(),
            })
            if project_dir.exists():
                shutil.rmtree(project_dir)
            raise

    def _apply_profile(self, workbook_path: Path, profile: dict[str, Any], metadata: dict[str, Any], project_id: str) -> None:
        wb = load_workbook(workbook_path)
        for name in profile["dataSheets"]:
            ws = wb[name] if name in wb.sheetnames else wb.create_sheet(name)
            if ws.max_row == 1 and ws.max_column == 1 and ws["A1"].value is None:
                ws.append([name.replace("_", " ")])
                ws.append(["Field", "Value", "Source / Notes"])
                ws.append(["", "", ""])
            apply_standard_sheet_style(ws)
        meta = wb["00_PROJECT_META"]
        for merged in list(meta.merged_cells.ranges):
            meta.unmerge_cells(str(merged))
        meta.delete_rows(1, meta.max_row)
        meta.append(["SINGH360 PROJECT METADATA", "", ""])
        meta.append(["Field", "Value", "Source / Notes"])
        mapping = [("Project ID", project_id), ("Project Name", metadata.get("projectName", "")),
                   ("Store / Site Number", metadata.get("storeNumber", "")), ("Client", metadata.get("client", "")),
                   ("Location", metadata.get("location", "")), ("Address", metadata.get("address", "")),
                   ("Project Profile", profile["id"]), ("Purpose", metadata.get("purpose", "")),
                   ("Scope Summary", metadata.get("scopeSummary", "")), ("Drawing Prefix", metadata.get("drawingPrefix", "")),
                   ("Revision", metadata.get("revision", "")), ("Drawn By", metadata.get("drawnBy", "")),
                   ("Checked By", metadata.get("checkedBy", ""))]
        for row in mapping:
            meta.append([row[0], row[1], "User supplied"])
        apply_standard_sheet_style(meta)
        index = wb["00_INDEX"]
        for merged in list(index.merged_cells.ranges):
            index.unmerge_cells(str(merged))
        index.delete_rows(1, index.max_row)
        index.append(["SINGH360 DRAWING INDEX", "", "", "", ""])
        index.append(["Page ID", "Family", "Include", "Issue Status", "Sheet Title"])
        for family in profile["defaultIncludedFamilies"]:
            page_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{profile['id']}|{family}|base").hex[:20]
            index.append([f"generated-{page_id}", family, "YES", "DRAFT", family])
        apply_standard_sheet_style(index)
        profile_ws = wb["00_TEMPLATE_PROFILE"]
        for merged in list(profile_ws.merged_cells.ranges):
            profile_ws.unmerge_cells(str(merged))
        profile_ws.delete_rows(1, profile_ws.max_row)
        profile_ws.append(["SINGH360 TEMPLATE PROFILE", "", ""])
        profile_ws.append(["Profile ID", "Profile Version", "Style Profile"])
        profile_ws.append([profile["id"], profile["version"], profile["styleProfile"]])
        apply_standard_sheet_style(profile_ws)
        wb.save(workbook_path)
        wb.close()
