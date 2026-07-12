SINGH360 CURRENT-APP REPOSITORY RESET V3

V3 fixes both failures from the prior attempts:

1. Locked ems/library/exports:
   ems/ is removed from Git and ignored even if Windows keeps a locked local copy.

2. Obsolete component-library smoke:
   scripts/smoke_component_library.py is replaced with a current LibraryV2 smoke
   that checks /api/lib, the local component catalog, and the published Pages catalog.
   It does not test retired EMS seed/RDM-folder workflows.

RUN:
1. Extract into Singh360_SmartDraw.
2. Double-click RESET_TO_CURRENT_APP_V3.bat.
3. Type RESET.
4. Type PUSH only after validation passes.

V3 also repairs the residual tracked deletions left by the failed V2 attempt.
All changed/removed files are backed up under:
.docs\archive\current_app_repo_reset_v3_<timestamp>
