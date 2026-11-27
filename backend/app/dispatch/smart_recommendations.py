"""Internal advisory composition; not an HTTP contract or a route provider."""

from collections import Counter
from datetime import datetime
from uuid import UUID

from app.assignment.contracts import AssignmentFacts
from app.dispatch.smart_eta import RouteEstimate, usable_eta
from app.dispatch.smart_ranking import DispatchCandidate, rank_candidates


def recommend_from_pool(
    pool: list[AssignmentFacts],
    estimates: list[RouteEstimate],
    *,
    tenant_id: UUID,
    site_id: UUID,
    destination_id: UUID,
    now: datetime,
) -> list[DispatchCandidate]:
    """Consume only server-authorized pool facts and trusted provider estimates.

    Unknown or ambiguous route evidence is excluded. Idle time is not yet measured:
    all candidates receive the same neutral tie-break value, not a measured idle time.
    The result is advisory and does not reserve a vehicle or driver.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        return []
    scoped = [
        estimate
        for estimate in estimates
        if estimate.tenant_id == tenant_id
        and estimate.site_id == site_id
        and estimate.destination_id == destination_id
    ]
    counts = Counter(estimate.vehicle_id for estimate in scoped)
    by_vehicle = {estimate.vehicle_id: estimate for estimate in scoped}
    candidates: list[DispatchCandidate] = []
    for facts in pool:
        if facts.site_id != site_id or facts.status != "ACTIVE":
            continue
        if facts.valid_from.tzinfo is None or facts.valid_from.utcoffset() is None:
            continue
        end = facts.valid_to
        if end is not None and (end.tzinfo is None or end.utcoffset() is None):
            continue
        if facts.valid_from > now or (end is not None and end <= now):
            continue
        estimate = by_vehicle.get(facts.vehicle_id)
        if estimate is None or counts[facts.vehicle_id] != 1:
            continue
        eta = usable_eta(
            estimate,
            tenant_id=tenant_id,
            site_id=site_id,
            vehicle_id=facts.vehicle_id,
            destination_id=destination_id,
            now=now,
        )
        if eta is None:
            continue
        candidates.append(
            DispatchCandidate(facts.vehicle_assignment_id, tenant_id, site_id, True, True, True, eta, 0)
        )
    return rank_candidates(candidates, tenant_id=tenant_id, site_id=site_id)
