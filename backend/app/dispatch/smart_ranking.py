"""Advisory ranking only; callers must load authorized, fresh facts server-side.

No assignment is created. Existing assignment and mission guards remain authoritative.
"""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class DispatchCandidate:
    assignment_id: UUID
    tenant_id: UUID
    site_id: UUID
    eligible: bool
    available: bool
    facts_fresh: bool
    eta_seconds: int | None
    idle_seconds: int


def rank_candidates(
    candidates: list[DispatchCandidate], *, tenant_id: UUID, site_id: UUID
) -> list[DispatchCandidate]:
    """Prefer shortest verified ETA, then longest idle time, then stable ID.

    Unknown ETA, stale facts, duplicate IDs and invalid durations are excluded.
    Tenant/site matching is defense in depth, not a substitute for RBAC or RLS.
    """
    scoped = [c for c in candidates if c.tenant_id == tenant_id and c.site_id == site_id]
    counts: dict[UUID, int] = {}
    for candidate in scoped:
        counts[candidate.assignment_id] = counts.get(candidate.assignment_id, 0) + 1

    ranked: list[tuple[int, int, UUID, DispatchCandidate]] = []
    for candidate in scoped:
        eta = candidate.eta_seconds
        if (
            not candidate.eligible
            or not candidate.available
            or not candidate.facts_fresh
            or counts[candidate.assignment_id] != 1
            or eta is None
            or eta < 0
            or candidate.idle_seconds < 0
        ):
            continue
        ranked.append((eta, -candidate.idle_seconds, candidate.assignment_id, candidate))
    ranked.sort(key=lambda item: item[:3])
    return [item[3] for item in ranked]
