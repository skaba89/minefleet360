"""A contract approval must be explicit and may never mean legal signature."""

import pytest

from app.legal.contract_workflow import ContractAction, ContractState, next_contract_state


def transition(state: ContractState, action: ContractAction, *, creator: bool = False, document: bool = True) -> ContractState:
    return next_contract_state(state, action, actor_is_creator=creator, document_attached=document)


def test_review_and_approval_require_distinct_people() -> None:
    assert transition(ContractState.DRAFT, ContractAction.SUBMIT) == ContractState.PENDING_REVIEW
    assert transition(ContractState.PENDING_REVIEW, ContractAction.APPROVE) == ContractState.APPROVED
    with pytest.raises(ValueError, match="creator"):
        transition(ContractState.PENDING_REVIEW, ContractAction.APPROVE, creator=True)


def test_review_requires_a_document() -> None:
    with pytest.raises(ValueError, match="document"):
        transition(ContractState.DRAFT, ContractAction.SUBMIT, document=False)


def test_rejected_contract_must_be_revised_before_resubmission() -> None:
    assert transition(ContractState.PENDING_REVIEW, ContractAction.REJECT) == ContractState.REJECTED
    assert transition(ContractState.REJECTED, ContractAction.REVISE) == ContractState.DRAFT
    with pytest.raises(ValueError, match="invalid"):
        transition(ContractState.REJECTED, ContractAction.APPROVE)


@pytest.mark.parametrize("state", list(ContractState))
def test_no_direct_or_repeat_approval(state: ContractState) -> None:
    if state == ContractState.PENDING_REVIEW:
        return
    with pytest.raises(ValueError, match="invalid"):
        transition(state, ContractAction.APPROVE)
