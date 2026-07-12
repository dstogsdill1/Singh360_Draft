SINGH360 CURRENT-APP REPOSITORY RESET

1. Extract this ZIP into the Singh360_SmartDraw repository root.
2. Double-click RESET_TO_CURRENT_APP.bat.
3. Type RESET.
4. The script backs up removed/replaced files under:
   .docs\archive\current_app_repo_reset_<timestamp>
5. It validates Python, the frontend build, routes, and component library.
6. Type PUSH only after validation passes.

STAYS:
- .docs/
- docs/component-library/
- current Flask/React app
- engines/ems_sheet.py
- personal Singh360 Component Library Real PowerPoint files

REMOVED:
- docs/LEGACY_GENERATOR.md and all old public buglists/reports/plans
- old VSON/Visio/RDM generator modules
- legacy /editor and web fallback
- old root installers, rollback scripts, PDFs, ZIPs, and temporary readmes

CORRECT MEANING:
- docs/  = public GitHub Pages
- .docs/ = local runtime projects, library, exports, and backups
