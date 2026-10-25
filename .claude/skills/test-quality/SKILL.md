---
name: test-quality
description: Use to design and execute reliable tests for each change.
---
# Test Quality

## Workflow
1. Review project constraints and existing implementation.
2. Specify domain states, permission rules, failure cases and data lineage.
3. Implement the smallest coherent vertical slice with tests and documented decisions.
4. Verify tenant isolation, auditability and invalid/late/duplicated events.
5. Summarize tests actually run and remaining risks.

## Domain-specific checklist
Create unit, integration, contract, E2E and security tests including permissions, malformed input, clock skew, offline duplicate GPS events, migrations; report precise commands, actual output, residual risk; no unverifiable claims.
