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

**Verified:** 84 passing backend tests, React build and isolated browser checks for
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
