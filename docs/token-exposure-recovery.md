# Historical token exposure recovery

The old `monzo_scheduler.db` exists in Git history. The observed access token's
recorded expiry was 2026-09-29; no refresh token was stored. Confirm that the
connection is no longer usable and review Monzo activity during the exposure
period. A different production database does not invalidate a copied token.

Run `python scripts/check_sensitive_files.py` before committing; CI runs the same
check. Configure the Security checks job as a required branch protection check,
and enable GitHub secret scanning/push protection where available.

History cleanup is a separate maintenance operation because it changes existing
commit IDs and requires coordinated replacement of remote branches and tags.
A reviewed, sanitized mirror should remove all database paths and sidecars using
`git-filter-repo --invert-paths --path-glob '*.db' --path-glob '*.db-*'
--path-glob '*.sqlite' --path-glob '*.sqlite-*' --path-glob '*.sqlite3'
--path-glob '*.sqlite3-*'`. Verify every ref before publishing rewritten history.

After publishing the reviewed history, ask collaborators to clone again, remove
old clones and backups securely, and follow GitHub's sensitive-data removal
procedure for cached commits and pull request refs. Do not merge old branches
back into the cleaned repository. History cleanup cannot invalidate credentials
or remove copies already downloaded by others.

Use `scripts/prepare_clean_history.sh /path/to/new/private/review-directory` to
prepare a scrubbed mirror, Git bundle, and old/new commit map for review. The
script pins git-filter-repo 2.47.0, does not alter the working checkout, and never
pushes. The bundle contains the sanitized refs and the security review branch.
Do not treat preparation as removal from GitHub: remote ref replacement and
cached-ref cleanup still require the coordinated maintenance procedure above.

Migration 0014 checkpoints/truncates SQLite WAL, switches to delete-mode journals,
and vacuums the live database after encryption. Runtime and migrations use
secure_delete=ON and restrict existing database/sidecar files to 0600. Encryption
migration downgrade is blocked so rollback cannot silently recreate plaintext.
Stop the service and other database users before migration, allow temporary disk
space for rebuilding, and take a protected encrypted backup first. The deployment
workflow now stops the service during schema changes and leaves it stopped if
migration fails, rather than running against a partially changed schema.

No migration can erase old backups, snapshots, filesystem snapshots, exported
files, or Git objects. Retire these separately and rotate any credentials whose
old copies cannot be accounted for. Keep production backup encryption separate
from the application token-encryption key.
