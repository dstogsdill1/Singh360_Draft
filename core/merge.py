"""core/merge.py — Stage 2+3 orchestrator: raw folder -> ProjectModel.

Runs intake to classify a project folder, then dispatches each file to its
registered extractor, fusing all findings into one ProjectModel. This is the
"identify a data dump and pull it together" step.
"""
from __future__ import annotations

from pathlib import Path

from core.intake import inventory, Inventory
from core.model import ProjectModel
from core.extractors import REGISTRY


def build_model(
    project_folder: str | Path,
    project_id: str = "",
    store: str = "",
    *,
    inv: Inventory | None = None,
    limit_per_type: int | None = None,
) -> ProjectModel:
    """Inventory `project_folder`, run every extractor, return the fused model."""
    folder = Path(project_folder)
    model = ProjectModel(project_id=project_id, store=store, title=store or folder.name)

    inv = inv or inventory(folder)

    # Group files by source type so we can cap noisy types (e.g. hundreds of CDs).
    by_type: dict[str, list] = {}
    for f in inv.files:
        if f.source_type in REGISTRY:
            by_type.setdefault(f.source_type, []).append(f)

    for source_type, files in by_type.items():
        extractor = REGISTRY[source_type]
        use = files[:limit_per_type] if limit_per_type else files
        for fe in use:
            try:
                extractor(fe.path, model)
            except Exception as exc:  # noqa: BLE001 - never let one file kill the run
                model.flag("blocked", f"{Path(fe.path).name}: extractor crashed: {exc}", fe.path)
        if limit_per_type and len(files) > limit_per_type:
            model.flag("info", f"{source_type}: processed {limit_per_type} of {len(files)} files (capped)", source_type)

    return model


def main() -> None:
    import sys
    if len(sys.argv) < 2:
        print("usage: python -m core.merge <project-folder> [out-model.json]")
        raise SystemExit(2)
    model = build_model(sys.argv[1])
    s = model.summary()
    print(f"Model: {s['nodes']} nodes, {s['points']} I/O points, {s['flags']} flags")
    for k, v in s["by_kind"].items():
        print(f"  {v:>4}  {k}")
    if len(sys.argv) > 2:
        print("wrote", model.save(sys.argv[2]))


if __name__ == "__main__":
    main()
