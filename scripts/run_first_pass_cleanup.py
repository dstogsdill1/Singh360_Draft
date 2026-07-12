
from component_canonical_tools import repo_root, apply_canonical_first_pass
import json
root = repo_root()
print("Repo root:", root)
print("Running dry-run first-pass cleanup...")
dry = apply_canonical_first_pass(root, dry_run=True)
print(json.dumps(dry, indent=2))
print("")
answer = input("Apply this cleanup to component metadata now? Type YES to apply: ").strip()
if answer == "YES":
    result = apply_canonical_first_pass(root, dry_run=False)
    print(json.dumps(result, indent=2))
    print("Done. Open Singh360 Draft and click Refresh Library.")
else:
    print("Cancelled. No changes applied.")
