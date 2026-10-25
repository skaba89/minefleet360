---
name: hr-workforce
description: Use for drivers, mechanics, shifts, leave, skills, licenses and authorizations.
---
# Hr Workforce

## Workflow
1. Review project constraints and existing implementation.
2. Specify domain states, permission rules, failure cases and data lineage.
3. Implement the smallest coherent vertical slice with tests and documented decisions.
4. Verify tenant isolation, auditability and invalid/late/duplicated events.
5. Summarize tests actually run and remaining risks.

## Domain-specific checklist
Model staff roles separately from login roles; licence categories, expiry and required qualifications; shift availability, leave and fatigue policy; limit PII exposure; test inactive/unqualified assignment prevention.
