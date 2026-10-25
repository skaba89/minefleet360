---
name: delivery-review
description: Use before merging or releasing features and when reviewing a change.
---
# Delivery Review

## Workflow
1. Review project constraints and existing implementation.
2. Specify domain states, permission rules, failure cases and data lineage.
3. Implement the smallest coherent vertical slice with tests and documented decisions.
4. Verify tenant isolation, auditability and invalid/late/duplicated events.
5. Summarize tests actually run and remaining risks.

## Domain-specific checklist
Check PR scope, docs, API schema, migration risks, fallback strategy, performance, accessibility, dependencies, environment variables, reproducible build and rollback. Block on high-severity issues.
