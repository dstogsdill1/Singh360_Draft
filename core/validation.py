from __future__ import annotations

from typing import Any


def find_invalid_scalars(value: Any, path: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(value, dict):
        for k, v in value.items():
            hits.extend(find_invalid_scalars(v, f"{path}.{k}"))
        return hits
    if isinstance(value, list):
        for i, v in enumerate(value):
            hits.extend(find_invalid_scalars(v, f"{path}[{i}]"))
        return hits

    if isinstance(value, float) and value != value:
        hits.append(path)
    if isinstance(value, str) and value.strip().lower() in {"nan", "nat", "<na>", "undefined"}:
        hits.append(path)
    return hits


def validate_project(project: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(project.get("pages"), list):
        errors.append("pages must be a list")
    if not isinstance(project.get("worksheets"), list):
        errors.append("worksheets must be a list")

    errors.extend([f"Invalid scalar at {p}" for p in find_invalid_scalars(project)])

    page_ids = set()
    for p in project.get("pages", []):
        pid = p.get("id")
        if not pid:
            errors.append("page missing id")
            continue
        if pid in page_ids:
            errors.append(f"duplicate page id: {pid}")
        page_ids.add(pid)

    return errors
