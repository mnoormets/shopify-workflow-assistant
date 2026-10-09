# Read-only merchant pilot

## Purpose
Measure whether evidence-linked investigation plans help an operator diagnose payment, stock and shipment discrepancies. This is a proposed pilot, not completed merchant validation.

## Before importing a real case
The store owner must approve scope and the specific export. Use a separate local installation/database. Assign random case IDs; remove customer names, emails, addresses, tokens and payment credentials. Use the structured Order schema; provider/carrier states must be actual source observations, never guesses. The current app receives structured snapshots and Shopify order webhooks; it does not independently fetch provider or carrier data. Do not connect a live store until its credentials, data scope and hosting are separately reviewed.

## Trial protocol
Use 10-20 owner-approved, anonymized historical cases including clean cases. Freeze the input and review policy. Have the owner label the actual outcome using provider/carrier records before seeing the generated plan. First compare the basic findings view and the investigation view on randomized, balanced case groups. Repeat with swapped groups if practical; account for learning effects. Record active working seconds, correct classification, evidence checks completed and any unsupported instruction. Do not count time waiting for a model as active working time; record it separately. A tiny pilot cannot prove general accuracy.

All investigation steps are read-only. The operator confirms matching transaction/order IDs, event timestamps and source records before deciding. Save only an anonymized summary in incident notes. Keep source documents and private exports outside the public repository.

## Measurement sheet (private)
Columns: case_id, known_outcome, view_used, active_seconds, model_wait_seconds, diagnosis_correct, evidence_checks_completed, unsupported_recommendation, operator_feedback. Publish aggregate metrics only after owner approval. Report sample size, protocol, failure cases and uncertainty alongside any time difference. A rejected ranking is a safe fallback event, not proof of successful model reasoning.

## Stop conditions
Stop when IDs do not match, source observations are missing, a source timestamp is ambiguous, data includes personal information, or a suggestion is not supported. Never infer settlement from a single store status. Never issue refunds, charges, store changes or messages from this app.

## Completion evidence
Owner-approved scope; data provenance; independent labels; anonymized timing sheet; aggregate report; actual failure analysis. Until these exist, CV wording must say synthetic evaluation and prepared pilot, not production deployment or merchant savings.
