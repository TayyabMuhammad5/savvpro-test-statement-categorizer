"""Phase 1 Bug 4: Override precedence regression tests.

Precedence order:
row-level user decision > merchant-level user rule > integrity guards (duplicate/pending) > transfers > dictionary > heuristics > traps.

Rules:
- User decisions must resolve duplicate/pending rows.
- Row-level actions: "Keep (not a duplicate)", "Exclude as duplicate", and row-only category assignment.
- Reject invalid combos: assigning "Needs Review" as a decision.
- Income category on an outflow requires confirmation flag or raises error/warning.
"""
from __future__ import annotations

import pytest
from app.brain import StatementCategorizerBrain
from app.models import TaxCategory, TransactionType


class TestOverridePrecedenceRegression:
    def test_row_decision_overrides_duplicate_guard(self) -> None:
        """Row-level action 'keep' allows a duplicate row to be kept and categorized."""
        csv_data = "\n".join([
            "Date,Description,Amount",
            "2025-05-01,B&H PHOTO EQUIPMENT,-150.00",
            "2025-05-01,B&H PHOTO EQUIPMENT,-150.00",
        ])
        # Without override, row 2 is flagged as duplicate
        brain_normal = StatementCategorizerBrain()
        resp_normal = brain_normal.analyze_statement(csv_data)
        assert resp_normal.transactions[1].transaction_type == TransactionType.DUPLICATE

        # With row decision {"tx-2": {"action": "keep", "category": TaxCategory.CAMERA_EQUIPMENT.value}}
        brain_override = StatementCategorizerBrain(
            row_decisions={"tx-2": {"action": "keep", "category": TaxCategory.CAMERA_EQUIPMENT.value}}
        )
        resp_override = brain_override.analyze_statement(csv_data)
        tx2 = resp_override.transactions[1]
        assert tx2.user_overridden is True
        assert tx2.category == TaxCategory.CAMERA_EQUIPMENT
        assert tx2.transaction_type == TransactionType.EXPENSE
        assert tx2.needs_review is False

    def test_row_decision_exclude_as_duplicate(self) -> None:
        """Row-level action 'exclude' explicitly excludes a row as duplicate."""
        csv_data = "\n".join([
            "Date,Description,Amount",
            "2025-05-01,SOME UNIQUE VENDOR,-50.00",
        ])
        brain = StatementCategorizerBrain(
            row_decisions={"tx-1": {"action": "exclude"}}
        )
        resp = brain.analyze_statement(csv_data)
        tx1 = resp.transactions[0]
        assert tx1.user_overridden is True
        assert tx1.transaction_type in (TransactionType.DUPLICATE, TransactionType.EXCLUDED)
        assert tx1.needs_review is False

    def test_merchant_rule_overrides_transfer(self) -> None:
        """Merchant-level rule takes precedence over transfer filter."""
        csv_data = "\n".join([
            "Date,Description,Amount",
            "2025-05-01,OWNER DRAW,-1000.00",
        ])
        # If user explicitly mapped "OWNER DRAW" to Personal/Non-deductible or another category
        brain = StatementCategorizerBrain(
            custom_rules={"OWNER DRAW": TaxCategory.PERSONAL_NON_DEDUCTIBLE}
        )
        resp = brain.analyze_statement(csv_data)
        tx = resp.transactions[0]
        assert tx.category == TaxCategory.PERSONAL_NON_DEDUCTIBLE
        assert tx.user_overridden is True

    def test_row_decision_overrides_merchant_rule(self) -> None:
        """Row-level decision takes precedence over merchant-level rule."""
        csv_data = "\n".join([
            "Date,Description,Amount",
            "2025-05-01,B&H PHOTO EQUIPMENT,-150.00",
            "2025-05-02,B&H PHOTO EQUIPMENT,-150.00",
        ])
        # Merchant rule maps B&H PHOTO to CAMERA_EQUIPMENT, but row 1 is overridden to PROPS
        brain = StatementCategorizerBrain(
            custom_rules={"B&H PHOTO EQUIPMENT": TaxCategory.CAMERA_EQUIPMENT},
            row_decisions={"tx-1": {"category": TaxCategory.PROPS_REFERENCE_BOOKS.value}}
        )
        resp = brain.analyze_statement(csv_data)
        assert resp.transactions[0].category == TaxCategory.PROPS_REFERENCE_BOOKS
        assert resp.transactions[1].category == TaxCategory.CAMERA_EQUIPMENT

    def test_reject_needs_review_as_user_decision(self) -> None:
        """Assigning 'Needs Review' as a user decision must be rejected."""
        brain = StatementCategorizerBrain()
        with pytest.raises(ValueError, match="Needs Review"):
            brain.set_row_decision("tx-1", action="categorize", category=TaxCategory.NEEDS_REVIEW)

    def test_income_category_on_outflow_requires_confirmation(self) -> None:
        """Assigning an income category to an outflow without confirmation flag must be rejected."""
        brain = StatementCategorizerBrain()
        with pytest.raises(ValueError, match="confirmation"):
            brain.set_row_decision(
                "tx-1",
                action="categorize",
                category=TaxCategory.CLIENT_BOOK_INCOME,
                amount=-100.0,
                confirm_income_on_outflow=False,
            )
