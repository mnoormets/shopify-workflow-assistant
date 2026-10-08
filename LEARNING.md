# Your first learning session

The code was created with AI assistance. Portfolio evidence is what you can explain,
change and validate yourself, not simply the presence of the repository.

## Session 1: follow one order (30-45 minutes)
1. Load demo data and find DEMO-005. It has multiple findings: explain why.
2. Read `Order` in backend/domain.py. Why is a timezone required? Why Decimal?
3. Follow POST /api/import: validation -> digest -> transaction -> upsert.
4. Replay the same import. Explain why the row count does not double.
5. Explain the distinction between a review candidate and a proven merchant error.

## Session 2: make a change yourself
Configurable limits are now implemented with AI assistance in ReviewPolicy and
GET/PUT /api/policy. Inspect the boundary tests: one minute before, exactly at and
one minute after a custom three-hour limit.
1. Change the pending-payment limit in the app and identify which findings disappear.
2. Explain why PAYMENT_MISMATCH remains even when an age warning disappears.
3. Explain how the settings survive restart without changing the order payload.
4. Your independent next change: add a test for a paid partial order at the limit.
Do not change expected results solely to make a failing test green.

## Session 3: break and repair
Try a duplicate ID, missing UTC offset, invalid amount and the same idempotency key
with changed data. Record expected/actual behavior. Explain the atomic transaction.

## Session 4: measure local AI
Choose a local model only after checking available hardware. Compare its explanations
with the rule baseline on a separate held-out case set. Score unsupported facts,
helpfulness and latency separately. Keep bad examples and record the actual model,
version, prompt and hardware. No training or fine-tuning is needed for the first demo.

## Before putting this on a CV
Demonstrate the app, explain a debugging decision, implement a small change without
AI assistance, and reproduce the tests. Describe it as an AI-assisted personal project.
Do not claim customer deployment, measured savings or senior engineering tenure.

## Session 1 response, 8 October 2026
Your approach: trace the payment through each stage and look for where it stops.
Next: compare transaction/order IDs, amounts and timestamps, then inspect payment
and carrier webhook delivery and processing errors. A provider's paid state is
not proof of settlement, and the fault need not be in the store. Do not change
states or charge again before confirming the records.
