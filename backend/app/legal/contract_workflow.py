"""Pure rules for a future contract approval workflow.

These functions do not mutate persistence or confer authorization.
The API must enforce RBAC, tenant isolation, site scope and audit on every transition.
"""

from enum import StrEnum


class ContractState(StrEnum):
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ContractAction(StrEnum):
    SUBMIT = "SUBMIT"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REVISE = "REVISE"


_ALLOWED: dict[tuple[ContractState, ContractAction], ContractState] = {
    (ContractState.DRAFT, ContractAction.SUBMIT): ContractState.PENDING_REVIEW,
    (ContractState.PENDING_REVIEW, ContractAction.APPROVE): ContractState.APPROVED,
    (ContractState.PENDING_REVIEW, ContractAction.REJECT): ContractState.REJECTED,
    (ContractState.REJECTED, ContractAction.REVISE): ContractState.DRAFT,
}


def next_contract_state(
    current: ContractState,
    action: ContractAction,
    *,
    actor_is_creator: bool,
    document_attached: bool,
) -> ContractState:
    """Return a valid next state or raise ValueError; never create a signed state."""
    target = _ALLOWED.get((current, action))
    if target is None:
        raise ValueError("invalid contract transition")
    if action == ContractAction.SUBMIT and not document_attached:
        raise ValueError("contract requires a document before review")
    if action == ContractAction.APPROVE and actor_is_creator:
        raise ValueError("creator cannot approve own contract")
    return target
