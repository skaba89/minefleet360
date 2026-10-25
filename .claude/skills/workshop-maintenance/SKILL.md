---
name: workshop-maintenance
description: Use for mechanics, workshops, work orders and preventive or corrective maintenance.
---
# Workshop Maintenance

## Workflow
1. Review project constraints and existing implementation.
2. Specify domain states, permission rules, failure cases and data lineage.
3. Implement the smallest coherent vertical slice with tests and documented decisions.
4. Verify tenant isolation, auditability and invalid/late/duplicated events.
5. Summarize tests actually run and remaining risks.

## Domain-specific checklist
Define WO lifecycle requested→approved→assigned→in progress→QC→closed; tie parts and labor to WO; protect against double-consumption; capture out-of-service duration; enforce release approval; verify parts and audit trail.
