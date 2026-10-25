---
name: mining-dispatch
description: Use for haulage missions, dispatch, rotation metrics, tonnage and weighbridge.
---
# Mining Dispatch

## Workflow
1. Review project constraints and existing implementation.
2. Specify domain states, permission rules, failure cases and data lineage.
3. Implement the smallest coherent vertical slice with tests and documented decisions.
4. Verify tenant isolation, auditability and invalid/late/duplicated events.
5. Summarize tests actually run and remaining risks.

## Domain-specific checklist
Define trip plan/assigned/en route/loading/unloading/completed/cancelled; immutable measurement events; distinguish estimated GPS events from official weighed tonnes; reconcile duplicates/late offline updates and subcontractor billing.
