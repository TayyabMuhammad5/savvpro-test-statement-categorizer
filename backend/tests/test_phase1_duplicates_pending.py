"""Phase 1 Bug 5: Duplicate and pending holds regression tests.

Rules:
- Possible duplicate is a Needs Review item with default suggestion "Keep" and "Exclude", never silently dropped.
- Pending holds are auto-excluded with a visible "Excluded: pending" badge (not Needs Review).
- Pending holds are reconciled with a later posted row of same merchant/amount (±) when present.
- Distinct 'excluded' state and consistent summary counts (no row double counted).
"""
from __future__ import annotations

import pytest
from app.brain import StatementCategorizerBrain
from app.models import TaxCategory, TransactionType


class TestDuplicatesAndPendingRegression:
    def test_possible_duplicate_is_needs_review(self) -> None:
        """Exact same-day duplicate should route to Needs Review with suggestions Keep and Exclude."""
        csv_data = "\n".join([
            "Date,Description,Amount",
            "2025-05-01,B&H PHOTO EQUIPMENT,-150.00",
            "2025-05-01,B&H PHOTO EQUIPMENT,-150.00",
        ])
        brain = StatementCategorizerBrain()
        resp = brain.analyze_statement(csv_data)
        assert len(resp.transactions) == 2
        tx1, tx2 = resp.transactions[0], resp.transactions[1]
        assert tx1.needs_review is False
        assert tx2.needs_review is True
        assert tx2.transaction_type == TransactionType.DUPLICATE
        assert "duplicate" in (tx2.review_reason or "").lower()

    def test_pending_hold_is_auto_excluded_not_needs_review(self) -> None:
        """Pending hold is auto-excluded (excluded state, not Needs Review) with pending badge/note."""
        csv_data = "\n".join([
            "Date,Description,Amount,Status",
            "2025-05-01,B&H PHOTO EQUIPMENT,-150.00,PENDING",
        ])
        brain = StatementCategorizerBrain()
        resp = brain.analyze_statement(csv_data)
        tx = resp.transactions[0]
        assert tx.needs_review is False
        assert tx.transaction_type == TransactionType.EXCLUDED
        assert "pending" in (tx.tax_note or "").lower()

    def test_pending_hold_reconciles_with_posted_row(self) -> None:
        """Pending hold is reconciled with a later posted row of same merchant and amount."""
        csv_data = "\n".join([
            "Date,Description,Amount,Status",
            "2025-05-01,B&H PHOTO EQUIPMENT,-150.00,PENDING",
            "2025-05-03,B&H PHOTO EQUIPMENT,-150.00,POSTED",
        ])
        brain = StatementCategorizerBrain()
        resp = brain.analyze_statement(csv_data)
        tx_pending, tx_posted = resp.transactions[0], resp.transactions[1]
        assert tx_pending.transaction_type == TransactionType.EXCLUDED
        assert tx_pending.needs_review is False
        assert "reconciled" in (tx_pending.tax_note or "").lower() or "posted" in (tx_pending.tax_note or "").lower()
        assert tx_posted.transaction_type == TransactionType.EXPENSE
        assert tx_posted.needs_review is False

    def test_summary_counts_no_double_counting(self) -> None:
        """Total rows must equal auto_categorized + needs_review + duplicate/excluded/pending."""
        csv_data = "\n".join([
            "Date,Description,Amount,Status",
            "2025-05-01,B&H PHOTO EQUIPMENT,-150.00,POSTED",
            "2025-05-01,B&H PHOTO EQUIPMENT,-150.00,POSTED",   # Duplicate -> Needs Review
            "2025-05-02,TRANSFER TO SAVINGS,-500.00,POSTED",  # Transfer
            "2025-05-03,MYSTERY UNKNOWN SHOP,-25.00,POSTED",  # Needs Review
            "2025-05-04,CAFE HOLD,-12.00,PENDING",            # Pending -> Excluded
        ])
        brain = StatementCategorizerBrain()
        resp = brain.analyze_statement(csv_data)
        assert resp.total_rows == 5
        # auto_categorized_count + needs_review_count + duplicate_or_pending_count (excluded) == total_rows
        # Verify no double counting:
        assert resp.needs_review_count == 2  # duplicate row + mystery unknown shop
        assert resp.auto_categorized_count == 2  # B&H posted + transfer
        assert resp.duplicate_or_pending_count == 1  # pending hold
