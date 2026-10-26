"""Phase 1 Bug 1: Refund logic regression tests.

Rules:
- REFUND requires an INFLOW (amount > 0). 
- An outflow containing RETURN/CREDIT (e.g. "FEDEX RETURN LABEL -25") stays an EXPENSE.
- Match refund/pending keywords against the description only; memo text may add a
  weak signal but must never change transaction type.
- Outflow with refund wording and no clear meaning → Needs Review.
- "REFUND TO CLIENT" outflow → contra-income, Needs Review with explanation.
"""
from __future__ import annotations

import pytest
from app.brain import StatementCategorizerBrain
from app.models import RawTransaction, TaxCategory, TransactionType


def make_tx(
    desc: str,
    amount: float,
    row_index: int = 1,
    date: str = "2025-03-10",
    memo: str | None = None,
) -> RawTransaction:
    return RawTransaction(
        row_index=row_index,
        date=date,
        raw_description=desc,
        amount=amount,
        memo=memo,
    )


class TestRefundLogicOutflowStaysExpense:
    """Outflows with RETURN/CREDIT keywords must stay as EXPENSE, not become REFUND."""

    def test_fedex_return_label_outflow_is_expense(self) -> None:
        brain = StatementCategorizerBrain()
        tx = brain.categorize_row(make_tx("FEDEX RETURN LABEL", -25.00), {})
        assert tx.transaction_type == TransactionType.EXPENSE
        assert tx.amount < 0

    def test_adobe_credit_card_fee_outflow_is_expense(self) -> None:
        brain = StatementCategorizerBrain()
        tx = brain.categorize_row(make_tx("ADOBE CREDIT CARD FEE", -10.00), {})
        assert tx.transaction_type == TransactionType.EXPENSE
        assert tx.amount < 0

    def test_return_shipping_label_outflow_is_expense(self) -> None:
        brain = StatementCategorizerBrain()
        tx = brain.categorize_row(make_tx("UPS STORE RETURN SHIPPING", -15.50), {})
        assert tx.transaction_type == TransactionType.EXPENSE
        assert tx.amount < 0


class TestRefundRequiresInflow:
    """A true REFUND must have positive amount (inflow)."""

    def test_inflow_with_refund_keyword_is_refund(self) -> None:
        brain = StatementCategorizerBrain()
        tx = brain.categorize_row(make_tx("B&H PHOTO REFUND", 150.00), {})
        assert tx.transaction_type == TransactionType.REFUND

    def test_inflow_from_expense_vendor_deposit_return_is_refund(self) -> None:
        brain = StatementCategorizerBrain()
        tx = brain.categorize_row(make_tx("LENSRENTALS.COM DEPOSIT RETURN", 150.00), {})
        assert tx.transaction_type == TransactionType.REFUND
        assert tx.category == TaxCategory.GEAR_RENTALS


class TestRefundKeywordDescriptionOnly:
    """Refund keywords in memo must NOT override transaction type when description is clean."""

    def test_memo_refund_keyword_does_not_make_outflow_a_refund(self) -> None:
        brain = StatementCategorizerBrain()
        tx = brain.categorize_row(
            make_tx("ADORAMA INC 212-741-0401 NY", -429.00, memo="refund pending on other order"),
            {},
        )
        assert tx.transaction_type == TransactionType.EXPENSE
        assert tx.amount < 0


class TestRefundToClientOutflow:
    """'REFUND TO CLIENT' outflow is contra-income, should go to Needs Review."""

    def test_refund_to_client_outflow_needs_review(self) -> None:
        brain = StatementCategorizerBrain()
        tx = brain.categorize_row(make_tx("REFUND TO CLIENT JOHNSON", -500.00), {})
        assert tx.needs_review is True
        assert tx.category == TaxCategory.NEEDS_REVIEW


class TestOutflowWithAmbiguousRefundWording:
    """Outflow with refund wording and no clear meaning → Needs Review."""

    def test_ambiguous_refund_outflow_needs_review(self) -> None:
        brain = StatementCategorizerBrain()
        tx = brain.categorize_row(make_tx("CREDIT ADJUSTMENT UNKNOWN VENDOR", -75.00), {})
        assert tx.needs_review is True
        assert tx.category == TaxCategory.NEEDS_REVIEW
