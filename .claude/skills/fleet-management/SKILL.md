---
name: fleet-management
description: Use when designing or implementing vehicles, equipment, assignments, eligibility and GPS lifecycle.
---
# Fleet Management

## Workflow
1. Review project constraints and existing implementation.
2. Specify domain states, permission rules, failure cases and data lineage.
3. Implement the smallest coherent vertical slice with tests and documented decisions.
4. Verify tenant isolation, auditability and invalid/late/duplicated events.
5. Summarize tests actually run and remaining risks.

## Domain-specific checklist
Vehicle state model; fleet assets by tenant/site; driver-vehicle assignments with valid intervals; eligibility rules for licence/inspection; odometer-hour-meter event handling; record data provenance; add cross-tenant and overlap tests.
