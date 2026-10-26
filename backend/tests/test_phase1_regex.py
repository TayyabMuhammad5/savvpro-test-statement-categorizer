"""Phase 1 Bug 6: Regex quality regression tests.

Rules:
- Fix trailing \\b that breaks prefix matches ('GOOGLE *ADS123', 'SOUTHWEST AIRLINES').
- Match rules against normalized merchant first, description second.
- Every rule must have >= 2 positive and >= 2 negative examples.
"""
from __future__ import annotations

import pytest
from app.brain import StatementCategorizerBrain
from app.models import TaxCategory
from app.rules import MERCHANT_RULES, TRANSFER_RULES, KEYWORD_HEURISTICS


class TestRegexQualityRegression:
    def setup_method(self) -> None:
        self.brain = StatementCategorizerBrain()

    def test_google_ads_with_trailing_digits(self) -> None:
        """'GOOGLE *ADS123456' must match MARKETING_BOOK_FAIRS despite trailing digits."""
        csv_data = "\n".join([
            "Date,Description,Amount",
            "2025-05-01,GOOGLE *ADS123456,-120.00",
        ])
        resp = self.brain.analyze_statement(csv_data)
        tx = resp.transactions[0]
        assert tx.category == TaxCategory.MARKETING_BOOK_FAIRS
        assert tx.needs_review is False

    def test_southwest_airlines_prefix_match(self) -> None:
        """'SOUTHWEST AIRLINES' must match TRAVEL_TRANSPORT."""
        csv_data = "\n".join([
            "Date,Description,Amount",
            "2025-05-02,SOUTHWEST AIRLINES,-340.50",
        ])
        resp = self.brain.analyze_statement(csv_data)
        tx = resp.transactions[0]
        assert tx.category == TaxCategory.TRAVEL_TRANSPORT
        assert tx.needs_review is False

    def test_matched_against_normalized_merchant_first(self) -> None:
        """Noise prefix 'POS DEBIT - ' stripped so normalized merchant matches rules."""
        csv_data = "\n".join([
            "Date,Description,Amount",
            "2025-05-03,POS DEBIT - B&H PHOTO 800-606 NY,-250.00",
        ])
        resp = self.brain.analyze_statement(csv_data)
        tx = resp.transactions[0]
        assert tx.category == TaxCategory.CAMERA_EQUIPMENT
        assert tx.matched_rule == "GEAR_BH_ADORAMA"
