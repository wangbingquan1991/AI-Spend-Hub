# Project status — SQLite deterministic connection close (review pending)

- **Baseline**: `main` at `09504dcdac7f3cc19f9138de60fecd87ac9c4b65` (PR #4 merged); no open PR at start of this increment. Original Git history preserved.
- **Scope**: `fix/sqlite-deterministic-connection-close`: use `contextlib.contextmanager` around `connect_db()`, retaining SQLite's `with db:` transaction commit/rollback behavior and explicitly closing in `finally`. In `tests/test_snapshot.py`, explicitly close the two direct `sqlite3.connect()` connections and commit DDL inside `with db:`.
- **Business behavior**: unchanged. Candidate review/approval/rejection, idempotency, cash-flow reporting, and SQLite backup behavior are untouched.
- **Verification (local copy matched against exact GitHub blobs)**: `PYTHONWARNINGS=error::ResourceWarning PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v` — 26 tests passed, 0 failed, 0 errors, 0 skipped. `web/index.html` and `web/review.html` inline JS syntax checked with Node v22.16.0, both passed. Recorded evidence is external to repository; tests use synthetic SQLite only.
- **Source provenance**: GitHub direct clone was unavailable in the test environment due to DNS. All nine executable/test asset blobs of baseline were checked against GitHub main; changed blobs matched locally tested byte content. Verification of PR head should use the same blob SHA checks, not imply a successful `git clone` or Windows host test.
- **Outstanding**: The director's Windows-host validation report and its raw log files are not accessible in this runtime. The supplied findings are context, not re-executed evidence. Windows locked-file teardown remains unverified here. Browser-to-HTTP E2E, NAS/Synology, and Docker live testing remain unverified.
- **Security / cost**: only synthetic local data; no real accounts, invoices, credentials, deployment, or new paid services.
- **Next**: review draft PR; do not merge until authorized.
