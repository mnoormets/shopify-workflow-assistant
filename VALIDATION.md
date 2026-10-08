# Validation - 8 October 2026

- Python API/domain tests: 35 passed (pytest). One upstream Starlette/httpx deprecation warning.
- React production build: successful, 23 modules transformed.
- Synthetic evaluation: 8 expected findings, 8 found, 0 additional, 0 missing.
- Running local service: PID21964, bound127.0.0.1:8770; GET health200 and root200.
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
