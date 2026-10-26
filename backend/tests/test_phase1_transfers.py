"""Phase 1 Bug 3: Transfer detection and cross-row pairing regression tests.

Rules:
- Require context for transfers: match explicit self-transfers ("TRANSFER TO/FROM SAVINGS|CHECKING|OWN ACCOUNT", "OWNER DRAW", etc.)
- Autopay sign sanity check: autopay on card is inflow (> 0); on bank account is outflow (< 0).
- "ONLINE TRANSFER FROM <person/company>" must NOT auto-exclude as transfer -> Needs Review with [Client Income, Transfer, Personal].
- "EPAYMENT" inside other merchants (e.g. "EPAYMENT PARKING METERS") must NOT auto-exclude as transfer.
- Cross-row transfer pairing: same amount, opposite sign, <= 3 days flagged with high confidence.
"""
from __future__ import annotations

import pytest
from app.brain import StatementCategorizerBrain
from app.models import TaxCategory, TransactionType


class TestTransferLogicRegression:
    def setup_method(self) -> None:
        self.brain = StatementCategorizerBrain()

    def test_online_transfer_from_person_not_auto_excluded(self) -> None:
        """'ONLINE TRANSFER FROM JANE DOE' must go to Needs Review, not auto-excluded."""
        csv_data = "\n".join([
            "Date,Description,Amount",
            "2025-05-02,ONLINE TRANSFER FROM JANE DOE,1200.00",
        ])
        resp = self.brain.analyze_statement(csv_data, "checking.csv")
        tx = resp.transactions[0]
        assert tx.needs_review is True, "P2P/Client transfer must not be auto-excluded"
        assert TaxCategory.CLIENT_BOOK_INCOME in tx.suggested_categories
        assert TaxCategory.NON_DEDUCTIBLE_TRANSFER in tx.suggested_categories
        assert TaxCategory.PERSONAL_NON_DEDUCTIBLE in tx.suggested_categories

    def test_epayment_inside_other_merchant_not_auto_excluded(self) -> None:
        """'PARKING EPAYMENT METERS' must NOT be classified as internal credit card autopay."""
        csv_data = "\n".join([
            "Date,Description,Amount",
            "2025-05-04,PARKING EPAYMENT METERS,-15.00",
        ])
        resp = self.brain.analyze_statement(csv_data, "checking.csv")
        tx = resp.transactions[0]
        assert tx.transaction_type != TransactionType.TRANSFER or tx.needs_review is True
        assert tx.category != TaxCategory.NON_DEDUCTIBLE_TRANSFER or tx.needs_review is True

    def test_explicit_transfer_to_savings_is_transfer(self) -> None:
        """'TRANSFER TO SAVINGS' outflow should be classified as internal transfer."""
        csv_data = "\n".join([
            "Date,Description,Amount",
            "2025-05-05,TRANSFER TO SAVINGS,-2000.00",
        ])
        resp = self.brain.analyze_statement(csv_data, "checking.csv")
        tx = resp.transactions[0]
        assert tx.transaction_type == TransactionType.TRANSFER
        assert tx.category == TaxCategory.NON_DEDUCTIBLE_TRANSFER
        assert tx.needs_review is False

    def test_owner_draw_is_transfer(self) -> None:
        """'OWNER DRAW' should be classified as internal transfer."""
        csv_data = "\n".join([
            "Date,Description,Amount",
            "2025-05-06,OWNER DRAW,-1500.00",
        ])
        resp = self.brain.analyze_statement(csv_data, "checking.csv")
        tx = resp.transactions[0]
        assert tx.transaction_type == TransactionType.TRANSFER
        assert tx.category == TaxCategory.NON_DEDUCTIBLE_TRANSFER

    def test_cross_row_transfer_pairing(self) -> None:
        """Cross-row transfer pairing: same amount, opposite sign, <=3 days."""
        csv_data = "\n".join([
            "Date,Description,Amount",
            "2025-05-10,CHECKING TO SAVINGS TRANSFER,-1000.00",
            "2025-05-11,SAVINGS TRANSFER RECEIVED,1000.00",
        ])
        resp = self.brain.analyze_statement(csv_data, "combined.csv")
        tx1, tx2 = resp.transactions[0], resp.transactions[1]
        assert tx1.transaction_type == TransactionType.TRANSFER
        assert tx2.transaction_type == TransactionType.TRANSFER
        assert any("cross-row" in s.detail.lower() or "cross-row" in s.layer.lower() or "paired" in s.detail.lower() for s in tx1.signals)
