# Project Profile Schema

Committed profiles live in `defaults/project_templates/project_profiles.json`; the adjacent JSON Schema documents the contract.

Each profile declares `id`, `displayName`, `description`, `extends`, `styleProfile`, `sourceSlots`, `dataSheets`, `pageRecipes`, `defaultIncludedFamilies`, `optionalFamilies`, `validationRules`, and `version`.

`BASE_CORE` owns common administration worksheets and page families. `EMS_FULL`, `EMS_INSTALL`, `EMS_RETROFIT`, `CX`, and `RCX` inherit those arrays and validation rules. Inheritance is resolved at backend startup, rejects missing parents and cycles, and de-duplicates entries while preserving order.

Profiles create a starting structure only. Page families remain includable, excludable, and reorderable. Only explicit `YES` index rows publish. `00_PROJECT_META` is never a drawing page, Cover is first, and Sheet Index is second.
