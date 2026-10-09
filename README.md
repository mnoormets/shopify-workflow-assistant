# Shopify Workflow Review

[![Checks](https://github.com/mnoormets/shopify-workflow-assistant/actions/workflows/check.yml/badge.svg)](https://github.com/mnoormets/shopify-workflow-assistant/actions/workflows/check.yml)

An AI-assisted portfolio application for reconciling order, payment, inventory
and shipment evidence, then recording a human review decision. React dashboard,
FastAPI API, durable SQL storage and deterministic findings. The included data is
synthetic; a merchant pilot has not been performed.

## What works

- Review queue with searchable order IDs, severity filters and evidence views.
- Persistent incidents: ownership, open/investigating/resolved/dismissed states,
  required decision notes, before/after audit history and revision conflict checks.
- Signed Shopify order webhook receiver, durable inbox, duplicate detection,
  stale/equal timestamp conflict handling and transactional order projection.
- Atomic JSON batch import with idempotency keys and configurable review thresholds.
- Optional operator-key protection for API reads/writes; server-assigned audit actor.
- Optional local Ollama explanation; validated output falls back to rule explanations.
- Eight-order demo and a 120-order synthetic operational scenario.

**Verified:** 96 passing backend tests, React build and isolated browser checks for
incident persistence and protected login/edit/reload. GitHub Actions runs the tests
and frontend build. [Validation](VALIDATION.md) records the actual test scope.

## Architecture

```text
React dashboard -> FastAPI validation -> SQLAlchemy / SQLite
Shopify HMAC    -> durable event inbox -> transactional projection
Stored orders  -> versioned rules     -> findings -> incident review + audit
                                      -> optional local explanation
```

Rules determine findings. The language model cannot change priority, money or
merchant statuses. Human incident decisions do not perform Shopify actions.
Imported structured fields exclude customer names, addresses and payment credentials;
free-text operator notes still require appropriate handling.

## Run from a fresh checkout

Requires Python 3.12, Node.js and pnpm. The CI workflow records the checked versions.

```sh
python -m venv .venv
# Activate .venv using your platform's activation command.
pip install -r requirements-lock.txt
cd frontend
pnpm install --frozen-lockfile
pnpm run build
cd ..
python -m uvicorn backend.api:app --host 127.0.0.1 --port 8770
```

Open http://127.0.0.1:8770/ and load the demo or 120-order scenario. API schema is
at `/docs`. Windows launch scripts `run.cmd` / `run.ps1` use an existing virtual
environment and compiled frontend; perform the setup above first.

## Verification

```sh
python -m pytest -q
python -m backend.evaluate_demo
```

Browser sources: `tests/ui_workflow.cjs` and `tests/ui_access.cjs`. They require
Playwright and a local running server; the protected check additionally needs its
operator key in the test process environment. Tests use a fresh browser context,
never an existing user profile. Actual receipts: `ui-workflow-report.json` and
`access-workflow-report.json`.

## Configuration

Only process environment settings are used; no `.env` file is loaded.

| Setting | Purpose |
| --- | --- |
| `SHOPIFY_OPS_DATABASE_URL` | SQLAlchemy database URL; default local SQLite |
| `SHOPIFY_OPS_OPERATOR_KEY` | Optional random key, at least 32 characters |
| `SHOPIFY_OPS_MODEL` | Optional installed Ollama model name |

See [Operations](OPERATIONS.md) for access and incident behavior and
[Integration](INTEGRATION.md) for webhook receiver settings and worker operation.
The API requires `X-Operator-Key` when protection is enabled, except health and
the independently HMAC-protected webhook route. The UI retains the key only in
memory. An invalid explicit key prevents startup. This identifies one installation
operator; it does not provide individual accounts or enterprise RBAC.

Without a key, run only the synthetic localhost demo. External hosting needs TLS,
managed identity/secrets and deployment hardening. `docker compose up --build`
provides a PostgreSQL route with a clearly labelled local-demo password; that
route has not been exercised here. SQLite is the verified database route.

## Evaluation boundaries

The demo and 120-order scenario are authored test fixtures. They do not establish
merchant precision, throughput, savings or uptime. Default 48-hour paid and
24-hour pending thresholds are assumptions, not store-approved SLAs. Refunded
fulfilled orders are review candidates, not proof of an incorrect payment.

Ollama must be installed/configured separately; JSON validation alone does not
guarantee grounded prose. AI output remains a draft. Store connection, independent
provider/carrier feeds and owner-approved operational testing are future work.

## Evidence-linked investigation (9 October 2026)

Open a finding and choose **Koosta uurimisplaan**. `POST /api/investigate/{order_id}` joins all current findings for the order, cites their exact structured evidence, states unknowns and provides a review checklist. A SHA256 snapshot binds the shown findings, policy and approved steps; it is not a source authenticity guarantee. Regenerate after data changes.

Optional local Ollama can reorder approved step IDs only. Unknown IDs, duplicates, omitted steps, extra prose/facts and malformed responses are rejected. All displayed text comes from reviewed playbooks; model output cannot introduce a cause or charge/refund action. The older `/api/explain` endpoint remains an explicitly labelled free-text draft with weaker grounding guarantees; use the investigation plan for the constrained workflow.

Verified here: 96 backend tests; 120 synthetic orders (75 flagged, 45 clean), 105 cited steps with no coverage/citation mismatch; React build; isolated headless UI check with no page errors. These are synthetic evaluations and mocked adversarial model outputs, **not live-model ranking quality or measured merchant savings**. See `investigation-evaluation.json`, `investigation-ui-report.json`, [pilot protocol](PILOT.md) and [interview practice](INTERVIEW.md).

```sh
python -m backend.evaluate_investigation
```
