"""core/extractors — one extractor per source type.

Each extractor reads ONE kind of source file and writes findings into the
shared ProjectModel (core/model.py). They are deterministic-first and never
invent values: when a source can't be parsed they record a `blocked`/`review`
flag instead of guessing.

Registry maps a source_type (from core/intake) -> extractor callable.
"""
from __future__ import annotations

from . import emerson_dump, kwh360_assets, ems_worksheet, cad_worksheet
from . import rdm_tdb, panel_config, cd_drawings, survey_photos, lighting_plan

REGISTRY = {
    "emerson_dump": emerson_dump.extract,
    "cad_worksheet": cad_worksheet.extract,
    "kwh360_assets": kwh360_assets.extract,
    "ems_worksheet": ems_worksheet.extract,
    "rdm_tdb": rdm_tdb.extract,
    "panel_config": panel_config.extract,
    "lighting_plan": lighting_plan.extract,
    "cd_drawings": cd_drawings.extract,
    "survey_photos": survey_photos.extract,
}

__all__ = ["REGISTRY"]
