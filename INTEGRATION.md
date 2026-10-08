# Shopify integration foundation - 8 October 2026

## Implemented and exercised locally
Raw-body HMAC-SHA256 validation with constant-time digest comparison; exact configured
shop allow-list; supported orders/create, orders/updated and orders/paid snapshots.
256 KiB request limit, UUID delivery IDs and persistent duplicate receipts.

Ingress commits a privacy-filtered inbox before acknowledgement. No request body,
customer, email, address, line-item descriptions or notes are retained. Authentication
happens before parsing. Failed normalization has a safe error code and empty payload;
it is acknowledged as a captured failure, not retried indefinitely. Correct it via a
new supported snapshot/delivery; this adapter cannot reconstruct the discarded raw body.

A separate worker projects pending snapshots and stores before/after audit rows in
one transaction. Failed transactions remain pending. Older source updated_at values
cannot overwrite newer ones; conflicting equal timestamps are flagged for review.
Order IDs are namespaced by shop. Store updates preserve independent provider, stock
and carrier observations. No carrier handover is inferred from fulfillment status.

## Run local simulation
Open the UI and select the event simulation button. It records pending -> paid, then
rejects an older pending snapshot and identifies a duplicate. Run it again to verify
that no additional changes are applied. This is synthetic; it does not call Shopify.
The simulation is disabled when a real receiver is configured.

## Worker
`python -m backend.worker --once` processes up to 100 pending events and exits.
`python -m backend.worker` polls every two seconds. No external API calls or merchant
writes occur. The UI provides a manual process button for the local learning demo.

## Real connection prerequisites (not performed)
Process settings SHOPIFY_OPS_WEBHOOK_SECRET (app client secret) and SHOPIFY_OPS_SHOP
(exact myshopify.com domain) enable POST /api/webhooks/shopify. No .env file is read.
Do not put the secret in a command committed to Git or send it in chat.

Before a real pilot: owner approval, installed Shopify app and scopes, HTTPS endpoint,
operator authentication, disabled demo/import routes, validated API version/payloads,
privacy/compliance webhooks and retention/deletion, migrations, reconciliation and
live-store acceptance tests. The current UI is bound to loopback and not public.

The order adapter currently rejects unsupported payment states (including partial
refunds). It does not reconcile multiple fulfillments, pickup metadata or independent
payment/carrier APIs. Missing shipping flags default conservatively to physical goods.
These limitations must be addressed for the specific store before calling it production.

## Concurrency scope
SQLite writer serialization and concurrent delivery duplicates were exercised locally.
PostgreSQL worker row/advisory locks are implemented but not yet executed against a
PostgreSQL server; do not claim cross-database production verification.

## Sources
- https://shopify.dev/docs/apps/build/webhooks/verify-deliveries
- https://shopify.dev/docs/api/webhooks/latest

## Your engineering evidence
Explain how an invalid signature differs from an authenticated bad order schema.
Show the rollback/retry test. Add one unsupported-payment-state normalization test
and explain whether you should reject, map or extend the domain before changing it.
