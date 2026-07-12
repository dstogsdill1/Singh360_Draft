SINGH360 CURRENT-APP REPOSITORY RESET V2

This replaces the failed V1 reset.

The V1 failure was caused by Windows/OneDrive locking:
ems\library\exports

V2 does not try to force-delete that locked folder. It:
- removes legacy ems/ from the Git index
- adds ems/ to .gitignore
- tries to move the local folder into .docs/archive
- leaves it locally ignored if Windows still has it locked
- continues with validation instead of aborting

RUN:
1. Extract into Singh360_SmartDraw.
2. Double-click RESET_TO_CURRENT_APP_V2.bat.
3. Type RESET.
4. Type PUSH only after validation passes.

All changed/removed files are backed up under:
.docs\archive\current_app_repo_reset_v2_<timestamp>
