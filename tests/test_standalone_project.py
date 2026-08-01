from __future__ import annotations

from copy import deepcopy
import unittest

from core.standalone_project import (
    archive_page,
    archive_project,
    create_standalone_project,
    migrate_project_to_standalone,
    normalize_standalone_project,
    restore_page,
    restore_project,
)


NOW = "2026-08-01T12:00:00Z"
LATER = "2026-08-02T12:00:00Z"


def drawing(page_id: str, order: int, *, include: bool = True) -> dict:
    return {
        "id": page_id,
        "order": order,
        "include": include,
        "sheetCode": f"D-{order}",
        "displaySheetCode": f"D-{order}",
        "sheetTitle": f"Drawing {page_id}",
        "sheetTab": f"Drawing {page_id}",
        "pageType": "canvas",
        "templateId": "ansi-b-standard",
        "blocks": [],
        "canvasObjects": [{"id": f"object-{page_id}", "type": "rect"}],
        "notes": f"note-{page_id}",
    }


class StandaloneProjectTests(unittest.TestCase):
    def test_generator_is_deterministic_for_minimal_and_full_profiles(self) -> None:
        metadata = {"projectName": "Synthetic Project", "client": "Example Client"}
        first = create_standalone_project(
            "synthetic-id", metadata, profile="minimal", now=NOW, rows_per_index_page=12
        )
        second = create_standalone_project(
            "synthetic-id", metadata, profile="minimal", now=NOW, rows_per_index_page=12
        )
        self.assertEqual(first, second)
        self.assertEqual("standalone_layout", first["projectMode"])
        self.assertEqual("automatic", first["managedPagePolicy"])
        self.assertEqual("disabled", first["workbookSync"]["status"])
        self.assertEqual([], first["worksheets"])
        self.assertEqual(
            ["synthetic-id__managed_cover", "synthetic-id__managed_sheet_index"],
            [page["id"] for page in first["pages"]],
        )
        self.assertEqual(["cover", "index"], [page["pageType"] for page in first["pages"]])
        self.assertEqual([1, 2], [page["pageNumber"] for page in first["pages"]])

        full = create_standalone_project(
            "synthetic-id", metadata, profile="full", now=NOW, rows_per_index_page=12
        )
        self.assertEqual([page["id"] for page in first["pages"]], [page["id"] for page in full["pages"][:2]])
        self.assertEqual("synthetic-id__layout_001", full["pages"][2]["id"])
        self.assertEqual("canvas", full["pages"][2]["pageType"])
        self.assertEqual("", full["pages"][2]["sheetCode"])
        with self.assertRaises(ValueError):
            create_standalone_project("bad", profile="demo", now=NOW)

    def test_normalization_preserves_existing_managed_ids_and_user_payloads(self) -> None:
        cover = {
            "id": "stable-cover",
            "order": 8,
            "include": True,
            "sheetCode": "C-001",
            "sheetTitle": "Existing Cover",
            "sheetTab": "Cover / Project Info",
            "pageType": "cover",
            "templateId": "custom-template",
            "blocks": [{"id": "cover-block", "type": "cover", "text": "legacy"}],
            "canvasObjects": [{"id": "cover-overlay", "type": "text"}],
            "custom": {"keep": True},
        }
        index = {
            "id": "stable-index",
            "order": 9,
            "include": True,
            "sheetCode": "I-001",
            "sheetTitle": "Existing Index",
            "sheetTab": "00_INDEX",
            "pageType": "Sheet Index",
            "renderMode": "excel_exact",
            "linkedWorksheetId": "worksheet-index",
            "blocks": [{"id": "source-index", "type": "excelRange", "grid": [["legacy"]]}],
            "canvasObjects": [],
        }
        project = {
            "id": "legacy-id",
            "metadata": {"projectName": "Legacy"},
            "pages": [drawing("page-b", 2), cover, drawing("page-a", 1), index],
            "worksheets": [{"id": "worksheet-index", "grid": [["must not drive pagination"]]}],
            "assets": [{"id": "asset-1", "url": "assets/a.png"}],
            "savedAssemblies": [{"id": "assembly-1", "objects": [{"id": "nested"}]}],
            "modified": "2020-01-01T00:00:00Z",
        }
        untouched = deepcopy(project)
        normalized = normalize_standalone_project(project, now=NOW, rows_per_index_page=46)

        self.assertEqual(untouched, project, "normalization must not mutate the caller")
        self.assertEqual(["stable-cover", "stable-index", "page-a", "page-b"], [p["id"] for p in normalized["pages"]])
        normalized_cover = normalized["pages"][0]
        normalized_index = normalized["pages"][1]
        self.assertEqual([{"id": "cover-overlay", "type": "text"}], normalized_cover["canvasObjects"])
        self.assertEqual({"keep": True}, normalized_cover["custom"])
        self.assertEqual("custom-template", normalized_cover["templateId"])
        self.assertEqual("generated_index", normalized_index["renderMode"])
        self.assertEqual("stable-index", normalized_index["id"])
        self.assertEqual("worksheet-index", normalized_index["linkedWorksheetId"])
        self.assertEqual(project["assets"], normalized["assets"])
        self.assertEqual(project["savedAssemblies"], normalized["savedAssemblies"])
        self.assertEqual(normalized, normalize_standalone_project(normalized, now=LATER))

    def test_sheet_index_pagination_is_project_driven_and_stable(self) -> None:
        project = create_standalone_project(
            "pagination", {"projectName": "Pagination"}, profile="minimal", now=NOW, rows_per_index_page=10
        )
        project["worksheets"] = [{"id": "00_INDEX", "grid": [["wrong", "data"]]}]
        project["pages"].extend(drawing(f"page-{number:03d}", number + 2) for number in range(1, 36))
        normalized = normalize_standalone_project(project, now=NOW, rows_per_index_page=10)
        index_pages = [page for page in normalized["pages"] if page.get("managedPage") == "index"]
        self.assertEqual(4, len(index_pages))
        self.assertEqual([0, 1, 2, 3], [int(page.get("continuationIndex") or 0) for page in index_pages])
        self.assertEqual([10, 10, 10, 10], [page["indexRowsOnPage"] for page in index_pages])
        self.assertEqual(40, len([page for page in normalized["pages"] if page.get("include", True)]))
        identities = [(page["id"], page["sheetCode"]) for page in index_pages]
        again = normalize_standalone_project(normalized, now=LATER)
        self.assertEqual(identities, [(page["id"], page["sheetCode"]) for page in again["pages"] if page.get("managedPage") == "index"])
        self.assertEqual(normalized, again)

    def test_surplus_generated_index_pages_are_recoverably_archived(self) -> None:
        project = create_standalone_project(
            "retired-index", profile="minimal", now=NOW, rows_per_index_page=5
        )
        project["pages"].extend(drawing(f"page-{number}", number + 2) for number in range(12))
        expanded = normalize_standalone_project(project, now=NOW, rows_per_index_page=5)
        generated = [page for page in expanded["pages"] if page.get("generatedIndexContinuation")]
        self.assertTrue(generated)
        protected_id = generated[-1]["id"]
        generated[-1]["canvasObjects"] = [{"id": "unexpected-overlay", "type": "text"}]
        for candidate in expanded["pages"]:
            if not candidate.get("appManaged"):
                candidate["include"] = False
        contracted = normalize_standalone_project(expanded, now=LATER, rows_per_index_page=5)
        self.assertNotIn(protected_id, [page["id"] for page in contracted["pages"]])
        retired = next(page for page in contracted["archivedPages"] if page["id"] == protected_id)
        self.assertEqual([{"id": "unexpected-overlay", "type": "text"}], retired["canvasObjects"])
        self.assertEqual("App-managed Sheet Index continuation no longer required.", retired["archivedReason"])
        self.assertEqual(contracted, normalize_standalone_project(contracted, now="2026-08-03T00:00:00Z"))

    def test_archived_index_continuations_revive_without_duplicate_ids(self) -> None:
        project = create_standalone_project(
            "revived-index", profile="minimal", now=NOW, rows_per_index_page=5
        )
        project["pages"].extend(drawing(f"page-{number}", number + 2) for number in range(12))
        expanded = normalize_standalone_project(project, now=NOW, rows_per_index_page=5)
        continuation = next(page for page in expanded["pages"] if page.get("generatedIndexContinuation"))
        continuation_id = continuation["id"]
        continuation["canvasObjects"] = [{"id": "preserved-index-overlay", "type": "text"}]

        for page in expanded["pages"]:
            if not page.get("appManaged"):
                page["include"] = False
        contracted = normalize_standalone_project(expanded, now=LATER, rows_per_index_page=5)
        self.assertIn(continuation_id, [page["id"] for page in contracted["archivedPages"]])

        for page in contracted["pages"]:
            if not page.get("appManaged"):
                page["include"] = True
        reexpanded = normalize_standalone_project(
            contracted, now="2026-08-03T00:00:00Z", rows_per_index_page=5
        )
        ids = [page["id"] for page in [*reexpanded["pages"], *reexpanded["archivedPages"]]]
        self.assertEqual(len(ids), len(set(ids)))
        revived = next(page for page in reexpanded["pages"] if page["id"] == continuation_id)
        self.assertEqual(
            [{"id": "preserved-index-overlay", "type": "text"}],
            revived["canvasObjects"],
        )
        self.assertEqual(
            reexpanded,
            normalize_standalone_project(
                reexpanded, now="2026-08-04T00:00:00Z", rows_per_index_page=5
            ),
        )

    def test_migration_detaches_workbook_metadata_and_is_idempotent(self) -> None:
        project = {
            "id": "legacy-project",
            "metadata": {
                "projectName": "Legacy",
                "sourceFile": "linked.xlsm",
                "linkedProjectRoot": "X:/Customer/MetadataRoot",
                "workbookHash": "metadata-hash",
            },
            "pages": [drawing("stable-page", 1)],
            "assets": [{"id": "asset"}],
            "savedAssemblies": [{"id": "saved"}],
            "sources": [{"id": "source-copy", "type": "workbook", "path": "sources/workbook/copy.xlsm"}],
            "projectRoot": "X:/Customer/Project",
            "linkedProjectRoot": "X:/Customer/Project",
            "sourceWorkbookName": "linked.xlsm",
            "workbookHash": "abc123",
            "workbookSync": {
                "status": "in_sync",
                "workbook": "X:/Customer/Project/linked.xlsm",
                "baselineWorkbookHash": "def456",
            },
        }
        original = deepcopy(project)
        migrated = migrate_project_to_standalone(project, now=NOW, canonical_display_name="Canonical")
        self.assertEqual(original, project)
        self.assertEqual("standalone_layout", migrated["projectMode"])
        self.assertEqual("Canonical", migrated["projectDisplayName"])
        self.assertEqual("", migrated["projectRoot"])
        self.assertEqual("", migrated["linkedProjectRoot"])
        self.assertEqual("", migrated["sourceWorkbookName"])
        self.assertEqual("", migrated["workbookHash"])
        self.assertEqual("", migrated["metadata"]["sourceFile"])
        self.assertEqual("", migrated["metadata"]["linkedProjectRoot"])
        self.assertEqual("", migrated["metadata"]["workbookHash"])
        self.assertEqual("disabled", migrated["workbookSync"]["status"])
        self.assertEqual("automatic", migrated["managedPagePolicy"])
        legacy = migrated["legacyWorkbookReference"]
        self.assertEqual("X:/Customer/Project", legacy["projectRoot"])
        self.assertEqual("linked.xlsm", legacy["sourceWorkbookName"])
        self.assertEqual("abc123", legacy["workbookHash"])
        self.assertEqual("linked.xlsm", legacy["metadataSourceFile"])
        self.assertEqual("X:/Customer/MetadataRoot", legacy["metadata"]["linkedProjectRoot"])
        self.assertEqual("metadata-hash", legacy["metadata"]["workbookHash"])
        self.assertEqual(project["assets"], migrated["assets"])
        self.assertEqual(project["savedAssemblies"], migrated["savedAssemblies"])
        self.assertEqual(project["sources"], migrated["sources"])
        self.assertIn("stable-page", [page["id"] for page in migrated["pages"]])
        self.assertEqual(migrated, migrate_project_to_standalone(migrated, now=LATER, canonical_display_name="Canonical"))

    def test_detach_only_preserves_sa31_pages_exactly(self) -> None:
        pages = [drawing("sa31-b", 9), drawing("sa31-a", 2, include=False)]
        pages[0]["canvasObjects"] = [{"type": "textbox", "text": "NaN"}]
        archived_pages = [{**drawing("sa31-retired", 12), "notes": "undefined"}]
        project = {
            "id": "sa31-synthetic",
            "metadata": {"projectName": "SA31"},
            "pages": deepcopy(pages),
            "archivedPages": deepcopy(archived_pages),
            "assets": [{"id": "sa31-asset"}],
            "savedAssemblies": [{"id": "sa31-assembly"}],
            "projectRoot": "Z:/SA31",
            "workbookSync": {"status": "app_changed", "workbook": "Z:/SA31/source.xlsx"},
        }
        migrated = migrate_project_to_standalone(
            project, now=NOW, archived=False, normalize_managed_pages=False
        )
        self.assertEqual(pages, migrated["pages"])
        self.assertEqual(archived_pages, migrated["archivedPages"])
        self.assertEqual(project["assets"], migrated["assets"])
        self.assertEqual(project["savedAssemblies"], migrated["savedAssemblies"])
        self.assertEqual("disabled", migrated["workbookSync"]["status"])
        self.assertEqual("preserve_existing", migrated["managedPagePolicy"])
        self.assertEqual(
            migrated,
            migrate_project_to_standalone(
                migrated, now=LATER, archived=False, normalize_managed_pages=False
            ),
        )

    def test_page_archive_restore_preserves_id_payload_and_relative_position(self) -> None:
        project = create_standalone_project("archive-pages", profile="minimal", now=NOW)
        project["pages"].extend(
            [drawing("page-a", 3), drawing("page-b", 4), drawing("page-c", 5)]
        )
        project = normalize_standalone_project(project, now=NOW)
        archived = archive_page(project, "page-b", reason="Superseded draft", now=NOW)
        self.assertNotIn("page-b", [page["id"] for page in archived["pages"]])
        archived_page = next(page for page in archived["archivedPages"] if page["id"] == "page-b")
        self.assertEqual(NOW, archived_page["archivedAt"])
        self.assertEqual("Superseded draft", archived_page["archivedReason"])
        self.assertEqual("page-a", archived_page["archivedPreviousPageId"])
        self.assertEqual("page-c", archived_page["archivedNextPageId"])

        # A later page insertion does not disturb the archived page's neighbor anchor.
        archived["pages"].append(drawing("page-later", 99))
        restored = restore_page(archived, "page-b", now=LATER)
        user_ids = [page["id"] for page in restored["pages"] if not page.get("appManaged")]
        self.assertEqual(["page-a", "page-b", "page-c", "page-later"], user_ids)
        restored_page = next(page for page in restored["pages"] if page["id"] == "page-b")
        self.assertEqual([{"id": "object-page-b", "type": "rect"}], restored_page["canvasObjects"])
        self.assertEqual(NOW, restored_page["lastArchivedAt"])
        self.assertEqual("Superseded draft", restored_page["lastArchivedReason"])
        self.assertEqual(LATER, restored_page["restoredAt"])
        self.assertFalse(any(page["id"] == "page-b" for page in restored["archivedPages"]))
        with self.assertRaises(ValueError):
            archive_page(project, project["pages"][0]["id"], now=NOW)

    def test_source_archive_restore_moves_continuations_as_one_recoverable_group(self) -> None:
        project = create_standalone_project("archive-continuations", profile="minimal", now=NOW)
        source = drawing("source-page", 4)
        continuation_a = drawing("source-page-cont-a", 5, include=False)
        continuation_a.update({"continuationOf": "source-page", "continuationIndex": 1})
        continuation_b = drawing("source-page-cont-b", 7)
        continuation_b.update({"continuationOf": "source-page", "continuationIndex": 2})
        project["pages"].extend(
            [
                drawing("page-before", 3),
                source,
                continuation_a,
                drawing("page-between", 6),
                continuation_b,
                drawing("page-after", 8),
            ]
        )
        project = normalize_standalone_project(project, now=NOW)
        original_user_ids = [
            page["id"] for page in project["pages"] if not page.get("appManaged")
        ]

        archived = archive_page(project, "source-page", reason="Replace source", now=NOW)
        active_ids = [page["id"] for page in archived["pages"]]
        for page_id in ("source-page", "source-page-cont-a", "source-page-cont-b"):
            self.assertNotIn(page_id, active_ids)
        self.assertIn("page-between", active_ids)

        grouped = [
            page
            for page in archived["archivedPages"]
            if page.get("archivedGroupRootId") == "source-page"
        ]
        self.assertEqual(
            ["source-page", "source-page-cont-a", "source-page-cont-b"],
            [page["id"] for page in grouped],
        )
        self.assertEqual([True, False, True], [page["archivedInclude"] for page in grouped])
        self.assertTrue(all(page["archivedReason"] == "Replace source" for page in grouped))
        self.assertTrue(all(page["include"] is False for page in grouped))

        # A later unrelated page remains last while every grouped page returns
        # to its own original neighbor position, including a non-contiguous
        # continuation on the far side of page-between.
        archived["pages"].append(drawing("page-later", 99))
        restored = restore_page(archived, "source-page", now=LATER)
        restored_user_ids = [
            page["id"] for page in restored["pages"] if not page.get("appManaged")
        ]
        self.assertEqual([*original_user_ids, "page-later"], restored_user_ids)
        restored_by_id = {page["id"]: page for page in restored["pages"]}
        self.assertTrue(restored_by_id["source-page"]["include"])
        self.assertFalse(restored_by_id["source-page-cont-a"]["include"])
        self.assertTrue(restored_by_id["source-page-cont-b"]["include"])
        for page_id in ("source-page", "source-page-cont-a", "source-page-cont-b"):
            page = restored_by_id[page_id]
            self.assertEqual(f"object-{page_id}", page["canvasObjects"][0]["id"])
            self.assertEqual("source-page", page["lastArchivedGroupRootId"])
            self.assertEqual(NOW, page["lastArchivedAt"])
            self.assertEqual(LATER, page["restoredAt"])
        self.assertFalse(
            any(
                page.get("archivedGroupRootId") == "source-page"
                for page in restored["archivedPages"]
            )
        )

    def test_individual_continuation_archive_stays_independent_of_source_group(self) -> None:
        project = create_standalone_project("archive-one-continuation", profile="minimal", now=NOW)
        continuation_a = drawing("source-cont-a", 4)
        continuation_a.update({"continuationOf": "source", "continuationIndex": 1})
        continuation_b = drawing("source-cont-b", 5)
        continuation_b.update({"continuationOf": "source", "continuationIndex": 2})
        project["pages"].extend(
            [drawing("source", 3), continuation_a, continuation_b, drawing("after", 6)]
        )
        project = normalize_standalone_project(project, now=NOW)

        one_archived = archive_page(project, "source-cont-a", reason="Review continuation", now=NOW)
        self.assertIn("source", [page["id"] for page in one_archived["pages"]])
        self.assertIn("source-cont-b", [page["id"] for page in one_archived["pages"]])
        retired_a = next(
            page for page in one_archived["archivedPages"] if page["id"] == "source-cont-a"
        )
        self.assertEqual("source-cont-a", retired_a["archivedGroupRootId"])

        source_archived = archive_page(one_archived, "source", reason="Review source", now=LATER)
        retired_roots = {
            page["id"]: page.get("archivedGroupRootId")
            for page in source_archived["archivedPages"]
        }
        self.assertEqual("source-cont-a", retired_roots["source-cont-a"])
        self.assertEqual("source", retired_roots["source"])
        self.assertEqual("source", retired_roots["source-cont-b"])

        source_restored = restore_page(source_archived, "source", now="2026-08-03T12:00:00Z")
        self.assertEqual(
            ["source", "source-cont-b", "after"],
            [page["id"] for page in source_restored["pages"] if not page.get("appManaged")],
        )
        self.assertEqual(
            ["source-cont-a"],
            [page["id"] for page in source_restored["archivedPages"]],
        )

        continuation_restored = restore_page(
            source_restored, "source-cont-a", now="2026-08-04T12:00:00Z"
        )
        self.assertEqual(
            ["source", "source-cont-a", "source-cont-b", "after"],
            [page["id"] for page in continuation_restored["pages"] if not page.get("appManaged")],
        )
        self.assertEqual([], continuation_restored["archivedPages"])

    def test_project_archive_restore_is_metadata_only_and_idempotent(self) -> None:
        project = create_standalone_project("archive-project", profile="minimal", now=NOW)
        archived = archive_project(project, reason="Legacy project", now=NOW)
        self.assertTrue(archived["archived"])
        self.assertEqual(project["pages"], archived["pages"])
        self.assertEqual(archived, archive_project(archived, reason="Different", now=LATER))
        restored = restore_project(archived, now=LATER)
        self.assertFalse(restored["archived"])
        self.assertEqual(NOW, restored["lastArchivedAt"])
        self.assertEqual("Legacy project", restored["lastArchivedReason"])
        self.assertEqual(project["pages"], restored["pages"])
        self.assertEqual(restored, restore_project(restored, now="2026-08-03T00:00:00Z"))


if __name__ == "__main__":
    unittest.main()
