# Validation - 8 October 2026



- Python API/domain tests: 56 passed (pytest). One upstream Starlette/httpx deprecation warning.

- React production build: successful, 23 modules transformed.

- Synthetic evaluation: 8 expected findings, 8 found, 0 additional, 0 missing.

- Running local service: PID24888, bound127.0.0.1:8770; GET health200 and root200.

- Demo import: imported8, replay behavior exercised in tests.

- Live search DEMO-005: PAYMENT_MISMATCH, PAYMENT_PENDING, SHIPMENT_MISMATCH.

- SQLite persistence across application restart tested with a temporary database.

- Optional Ollama adapter tested with mocked valid, failed and invalid responses.

- No actual model downloaded or model inference evaluated. Current UI uses rules.

- Docker/PostgreSQL config supplied but not executed; CI workflow supplied but not run on GitHub.

- Codex browser UI inspection failed before page access (trusted Node helper exited). HTML/assets

  served and build verified; browser visual/interactive end-to-end check is still outstanding.

- No real store linked, confidential data used, public deployment or CV achievement claim made.



- Review policy: persisted integer limits (1-720 hours), GET/PUT API and React settings form.

- Custom limit tests: one minute before, at and after for paid and pending orders.

- Invalid settings rejected without overwriting saved values; unchanged payment conflicts

  remain visible after age-limit changes; settings persistence verified across restart.

- Updated live health reports rule_version 1.1.0 and policy API returns default 48/24.


- Webhook inbox/projection: HMAC tampering, duplicate delivery and ID-content conflict,
  out-of-order timestamps, equal-timestamp conflicts, privacy allow-list, invalid
  schema capture, rollback/retry, persistent inbox restart and concurrent duplicates.
- Live synthetic event run: 2 processed, 1 stale; repeated run creates no events.
- UI production build successful after event history/audit additions.
- PostgreSQL locking code provided but not exercised; merchant integration still pending.

## Incident operations â€” 8 October 2026
69 tests pass, including repeated sync, invalid state transitions, stale revision
rejection without extra audit records, detection clear/reactivation, clean scenario
groups, list limits/literal wildcard filters, and legacy audit migration preserving
notes. React production build passes. Existing audit-table upgrade failure was
found during live end-to-end testing and repaired; the previous database was not
removed. No external store or payment action was executed.

Live isolated headless Chromium test passed: scenario import, incident sync,
evidence view, ownership update, note/revision write and audit persistence after
page reload. No page errors. The source test is tests/ui_workflow.cjs; it refuses
non-local URLs and writes only ignored data/ui-check artifacts. A screenshot was
visually inspected for layout and readable workflow history. Operator identity
is a self-declared label in demo mode. Protected mode is described below.


## Protected operator checkpoint â€” 8 October 2026
84 backend tests pass. Added missing/wrong-key rejection for reads and mutations,
valid-key workflow, server-assigned audit identity despite a forged actor label,
public health without secret disclosure, no-store headers, fail-closed invalid
configuration and separate webhook signature enforcement. Frontend build passes.

Isolated headless Chromium with a fresh context and temporary SQLite database:
wrong key rejected; valid login and incident update completed; reload required a
new key; localStorage/sessionStorage remained empty. The run used an ephemeral
random process key, not a stored credential. See access-workflow-report.json and
tests/ui_access.cjs. Shared-key identity is installation-level, not per-human.


## Evidence-linked investigation — 9 October 2026
96 tests passed; 12 added behavioral cases cover evidence links, unchanged stored findings, invented/missing/duplicate model steps and extra model facts, valid ranking, policy snapshot changes and protected access. Synthetic 120-order coverage evaluation passed:75 flagged,45 clean,105 cited steps. React build and isolated headless Chrome UI check passed with no page errors. Screenshot visually inspected. No live LLM or merchant pilot performed in this checkpoint.
