# Operational walkthrough

## Problem and implemented workflow
Payment, stock and carrier systems can disagree. A raw list of findings is not
sufficient: someone must own the review, see source observations and record the
outcome without losing another operator's work. This application now joins a
webhook inbox, deterministic detection and persistent incident management.

1. The signed receiver acknowledges a normalized durable event.
2. A worker projects the newest snapshot; duplicate/stale events cannot overwrite it.
3. Versioned rules emit source-backed findings.
4. Explicit incident sync preserves operator state and marks detection changes.
5. The reviewer assigns an owner, inspects evidence and records a reason.
6. Revision checks prevent an outdated browser from overwriting a newer decision.
7. State changes and before/after audit snapshots commit together.

The AI explanation interface is optional and cannot execute merchant actions.
No local generative model is connected to this app yet; deterministic evidence and
checks remain functional. This is not a claim of tested autonomous AI diagnosis.

## State machine
open -> investigating or dismissed
investigating -> open, resolved or dismissed
resolved/dismissed -> investigating

Same-state notes/owner updates are allowed but still increment revision and append
an audit record. Detection.active is separate from status: it may remain true when
an operator records resolution, or false while review remains open. The UI displays
both rather than silently equating a disappeared rule with a solved issue.

## Concurrency and recovery
Each update includes its expected revision. A conditional SQL update must affect
one row; otherwise the request fails with 409 and no audit change is committed.
Sync is eventually consistent with imports: a simultaneous new order observation
may require another sync. Audit persistence is transactional. SQLite is the tested
local backend; hosted PostgreSQL and multi-process migration coordination still
need deployment validation. Actor labels are not authentication.

## Demonstration data
The 120-order scenario is authored and repeatable within the anchor hour. It adds
105 expected findings; three clean groups produce none. It does not estimate the
incident rate of a real merchant or measured monetary savings. Source fixtures,
API tests and UI checks are separate evidence, with their scope retained.
