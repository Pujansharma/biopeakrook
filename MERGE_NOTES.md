# Biopeak Nexus — merge notes

## Inputs
- Base project: `Biopeak-Nexus-BE (1).zip` (old code)
- Overlay: `Biopeak-Nexus-BE-Phase-1-ROOK.zip` (new code)
- Output: merged working copy; neither uploaded ZIP was modified.

## Merge strategy
- Started from the old project tree.
- Overlaid all files from the new project snapshot onto the copied tree so that the new feature implementations and their integration/configuration changes are present.
- Retained old-only files and the old `.git` metadata where the new ZIP did not include replacements.
- This is a separate output folder; it does not edit the original old ZIP.

## File-level counts
- Files in old snapshot (excluding directories): 1126
- Files in new snapshot (excluding directories): 1177
- New snapshot files copied into merged tree: 1177
- Existing paths replaced in merged copy with new snapshot versions: 1097
- Paths retained only from old snapshot: 29

## Integrated areas
- ROOK wearable connections, SDK configuration, health dashboard/timeline/domain APIs, webhook handlers, ingestion and background processing.
- Customer appointment routes and appointment auto-assignment/redemption updates.
- Product document categories and assignments.
- App-download redirect and appointment reminder command.
- Related settings, `.env.example`, URL wiring, migrations, tests, docs, and Bruno API requests from the new snapshot.

## Compatibility fixes applied in merged copy
- Fixed six invalid Python exception-handler clauses that used `except ErrorA, ErrorB` syntax, replacing them with tuple syntax. The same syntax issue existed in both input snapshots; only the merged copy was corrected.

## Important operational steps before production
1. Review `.env.example` and configure ROOK credentials for the target environment. Do not enable unsigned webhooks in production.
2. Review database migrations in staging before applying them to production data.
3. Install dependencies using the project's documented workflow.
4. Run `python manage.py check` and the full test suite in the configured environment.
5. Test existing appointment/customer/product APIs as well as all new ROOK endpoints.
6. The merge has not been runtime-tested here because Django and the project's dependencies are not installed in this environment. Python syntax compilation was checked separately.

## Retained old-only paths
- `bruno/leads/v2/PATCH Lead v2 (converted ΓÇö onboarding sent only).bru`
