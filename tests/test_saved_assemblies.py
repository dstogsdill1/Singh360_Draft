from __future__ import annotations

import unittest

from core.project_model import default_project, ensure_project_shape


class SavedAssemblyProjectModelTests(unittest.TestCase):
    def test_default_project_starts_with_no_saved_assemblies(self) -> None:
        self.assertEqual(default_project("project-1")["savedAssemblies"], [])

    def test_project_normalization_preserves_saved_editable_group(self) -> None:
        project = default_project("project-1")
        project["savedAssemblies"] = [{
            "id": "assembly-1",
            "name": "Signage Trio",
            "createdAt": "2026-07-29T00:00:00Z",
            "object": {
                "type": "Group",
                "objectId": "group-1",
                "objects": [{"type": "Rect", "objectId": "child-1"}],
            },
        }]

        normalized = ensure_project_shape(project)

        self.assertEqual(normalized["savedAssemblies"], project["savedAssemblies"])


if __name__ == "__main__":
    unittest.main()
