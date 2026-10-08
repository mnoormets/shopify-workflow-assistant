# Shopify Workflow Review



A portfolio and learning project: identify inconsistencies between store payment,

provider payment, stock allocation and shipment states. The first release uses

invented orders; it is not connected to Shopify or a merchant account.



## Run locally



This computer already has an isolated Python environment and compiled React UI.

Double-click `run.cmd`, or run `./run.ps1`, then open http://127.0.0.1:8770/.

Click **Laadi näidistellimused**. You can search order IDs, filter priority, inspect

recorded evidence and request an explanation. API docs: `/docs`.



For a fresh checkout:

```sh

python -m venv .venv

# Activate your virtual environment, then:

pip install -r requirements-lock.txt

cd frontend

pnpm install --frozen-lockfile

pnpm run build

cd ..

python -m uvicorn backend.api:app --host 127.0.0.1 --port 8770

```



## Architecture



React -> FastAPI validation -> SQLAlchemy -> SQLite (local) / PostgreSQL (optional)

                         -> deterministic versioned rules -> evidence + review queue

                         -> optional local Ollama explanation -> human review



- Rules determine findings. A language model cannot alter statuses, priority or money.

- `/api/import` accepts an allow-listed schema and requires `Idempotency-Key`.

  Replaying the same batch returns a replay receipt; reusing its key for a different

  batch returns 409. A batch is committed atomically. Later imports upsert order IDs.

- Stored data contains no names, email addresses, addresses or payment credentials.

- Money uses Decimal validation, then decimal strings in JSON (no float rounding).

- Timestamps require offsets; future orders are rejected on import.

- 48-hour paid and 24-hour pending thresholds are assumptions, not merchant SLAs.

- Pickup and digital orders do not require shipping tracking numbers.

- Refunded/fulfilled orders are review candidates, not proven mistakes: returns exist.



## Optional local AI



Install Ollama separately and choose/download a model that fits your hardware.

Set only the process variable `SHOPIFY_OPS_MODEL` to that installed model's name,

then restart the server. The adapter calls localhost:11434/api/chat with structured

JSON output, stream disabled and a 45-second timeout. Only the finding's code,

reason, evidence and review action are sent, not the complete order or customer data.

No model is installed automatically. Without a model the UI explicitly shows rules.

Timeouts and invalid responses fall back to verified rule explanations.

Model responses remain drafts: JSON shape validation does not guarantee correctness.



## Tests and evaluation

```sh

python -m pytest -q

python -m backend.evaluate_demo

```

The evaluation set is eight invented orders with eight expected findings, including

clean tracked, pickup and digital orders. Passing it proves fixture agreement only,

not real merchant precision/recall. Add separate anonymized merchant cases only with

permission. No throughput, cost-saving or uptime claims have been measured.



## PostgreSQL and Docker



`docker compose up --build` runs the app with PostgreSQL on a loopback-bound port.

The included password is an explicit local-demo value, not a real credential.

The Docker/PostgreSQL route is provided but must be tested where Docker is available.

The exercised local route uses SQLite. Set `SHOPIFY_OPS_DATABASE_URL` to a SQLAlchemy

PostgreSQL URL to change databases. No `.env` files are loaded.



## Scope and next work



This is a local single-user demo, not production-ready: authentication, database

migrations, tenant isolation, queueing, merchant-approved thresholds, production

monitoring and real integration adapters are still needed before a merchant pilot.

No orders are refunded, charged, canceled, messaged or updated. Public hosting and

GitHub publication require a later explicit action. Keep generated `data/` out of Git.



See `LEARNING.md` for the first learning session and `VALIDATION.md` for actual checks.



## Configurable review limits

Use Kontrollipiirid in the local app to save integer hours between 1 and 720.

Defaults are 48 hours for paid unfulfilled orders and 24 for pending payments.

GET/PUT /api/policy reads or saves the local policy in the same database. Findings

include the active policy and age findings include threshold_hours as evidence.

Changing limits recalculates findings; it does not change imported order states.

These are elapsed-hour thresholds, not business-day or carrier SLA calculations.


## Webhook integration foundation
Version 0.2 includes a signed Shopify order-snapshot inbox, durable duplicate detection,
source timestamp ordering, transactional projection and before/after audit history.
The UI has a synthetic event simulator. See INTEGRATION.md for supported payloads,
worker commands, tested boundaries and prerequisites before a real merchant pilot.
No Shopify credentials, real store connection or merchant writes are present.

## Operations workspace
The React dashboard now includes a persistent incident queue. Click **120
 tellimusega tööpäev**, then **Uuenda juhtumeid leidudest**. Inspect a case, assign
an owner, record the evidence checked, and move it to investigating. Only an
investigating case can be marked resolved; reopening is explicit. A resolution
is an operator record, not proof that Shopify or a payment provider was changed.

Incident IDs are deterministic per order/rule. Observation updates preserve the
operator's state. A rule no longer firing clears detection.active, without
inventing a human resolution. Revision-checked compare-and-swap writes reject
stale operator edits with HTTP 409. Each successful write and source-observation
change appends before/after records in the same transaction. History is ordered by
revision. List endpoints use bounded limits and literal order-ID filtering.

New endpoints: POST /api/scenario, POST /api/incidents/sync, GET /api/incidents,
GET /api/incidents/{id}, PATCH /api/incidents/{id}. OpenAPI includes strict inputs.
A local schema upgrade adds audit revisions without discarding existing notes.
The 120-order scenario includes five exception groups and three clean groups.
No customer details or external merchant calls are used in the scenario.

Operator labels in this local demo are self-declared, not authenticated identity.
Free-text notes must contain only synthetic content. This is not a tamper-proof
ledger. Authentication, permission enforcement, robust migration orchestration,
backup/restore, retention and a merchant-approved pilot are deployment gates.
PostgreSQL incident concurrency is implemented through conditional updates but
has not been validated against a live PostgreSQL server.

## Browser workflow verification
Install Playwright separately in the project root (`npm install --no-save
playwright`) and its Chromium (`npx playwright install chromium`). With this local
app running, run `node tests/ui_workflow.cjs`. Optionally set
PLAYWRIGHT_CHROMIUM_EXECUTABLE to a browser binary or SHOPIFY_UI_URL to another
localhost port. The test creates synthetic records and operator notes; run it
only against a demo. Screenshot/results go to ignored data/ui-check. The checked
local run used a fresh headless context without the user's browser profile.
