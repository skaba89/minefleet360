---
name: security-review
description: Use when reviewing auth, RBAC, privacy, secrets and tenant isolation.
---
# Security Review

## Workflow
1. Review project constraints and existing implementation.
2. Specify domain states, permission rules, failure cases and data lineage.
3. Implement the smallest coherent vertical slice with tests and documented decisions.
4. Verify tenant isolation, auditability and invalid/late/duplicated events.
5. Summarize tests actually run and remaining risks.

## Domain-specific checklist
Produce threat model and verification matrix; systematically test cross-tenant object identifiers for create/read/update/delete/export; API access vs UI hide; GPS staff retention and lawful access; secure defaults, audit and rate limiting.
