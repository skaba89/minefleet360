---
name: fuel-inventory
description: Use for fuel issuance, tanks, spare parts, pneus and procurement.
---
# Fuel Inventory

## Workflow
1. Review project constraints and existing implementation.
2. Specify domain states, permission rules, failure cases and data lineage.
3. Implement the smallest coherent vertical slice with tests and documented decisions.
4. Verify tenant isolation, auditability and invalid/late/duplicated events.
5. Summarize tests actually run and remaining risks.

## Domain-specific checklist
Use append-only stock movements with balancing controls; record issue approval and recipient; consumption per km/h and exceptions; track thresholds and stocktake adjustments; test concurrent issue conflicts.
