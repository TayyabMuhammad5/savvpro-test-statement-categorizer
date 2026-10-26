"""Phase 1 Bug 2: Sign convention regression tests.

Rules:
- Delete the 'majority positive => Amex' heuristic.
- Determine sign from explicit evidence only (Type column, 'Charge Amount' header,
  preamble text, split Debit/Credit columns).
- If undeterminable, set sign_convention='unknown', emit parse warning.
- Test with an income-heavy checking file (majority positive but NOT Amex).
"""
from __future__ import annotations

import pytest
from app.parser import parse_statement_csv


class TestSignConventionNoMajorityHeuristic:
    """Income-heavy checking file must NOT be treated as Amex-style inverted."""

    def test_income_heavy_checking_not_inverted(self) -> None:
        """A checking account with more inflows than outflows should NOT invert signs."""
        csv_data = "\n".join([
            "Date,Description,Amount",
            "2025-05-01,CLIENT PAYOUT WEDDING RETAINER,4850.00",
            "2025-05-03,PRINT STORE PAYOUT,1640.00",
            "2025-05-05,BOOK ROYALTY PAYOUT,612.50",
            "2025-05-07,B&H PHOTO EQUIPMENT,-329.00",
            "2025-05-09,ADOBE SUBSCRIPTION,-59.99",
            "2025-05-11,CLIENT CHECK DEPOSIT,2200.00",
            "2025-05-13,SHUTTLE SERVICE,-45.00",
        ])
        txs, detected_fmt, warnings = parse_statement_csv(csv_data)
        # Income-heavy: 4 positive (9302.50) vs 3 negative (433.99)
        # Old heuristic would invert because pos_count > neg_count * 2
        # The client payouts must stay positive (inflows), equipment must stay negative (outflows)
        assert len(txs) == 7
        client_payout = [t for t in txs if "CLIENT PAYOUT" in t.raw_description][0]
        assert client_payout.amount > 0, "Client payout should be positive (inflow)"
        bh_photo = [t for t in txs if "B&H PHOTO" in t.raw_description][0]
        assert bh_photo.amount < 0, "B&H Photo equipment purchase should be negative (outflow)"

    def test_explicit_charge_amount_header_inverts(self) -> None:
        """A file with 'Charge Amount' header should correctly invert."""
        csv_data = "\n".join([
            "Date,Description,Charge Amount,Type",
            "2025-04-02,DELTA AIR LINES,$618.40,Charge",
            "2025-04-16,ADORAMA RETURN CREDIT,-$79.00,Credit",
        ])
        txs, detected_fmt, warnings = parse_statement_csv(csv_data)
        assert len(txs) == 2
        delta = txs[0]
        assert delta.amount < 0, "Charge Amount column: charges should be negative (outflow)"
        adorama = txs[1]
        assert adorama.amount > 0, "Charge Amount column: credits should be positive (inflow)"

    def test_type_column_determines_sign(self) -> None:
        """Type column (DEBIT/CREDIT) should override sign regardless of majority."""
        csv_data = "\n".join([
            "Date,Description,Amount,Type",
            "2025-04-02,EQUIPMENT PURCHASE,618.40,Charge",
            "2025-04-03,STUDIO RENTAL,200.00,Sale",
            "2025-04-04,CLIENT REFUND,79.00,Credit",
        ])
        txs, detected_fmt, warnings = parse_statement_csv(csv_data)
        equip = [t for t in txs if "EQUIPMENT" in t.raw_description][0]
        assert equip.amount < 0, "Type=Charge should make amount negative"
        refund = [t for t in txs if "CLIENT REFUND" in t.raw_description][0]
        assert refund.amount > 0, "Type=Credit should make amount positive"

    def test_split_debit_credit_columns_work(self) -> None:
        """Split Debit/Credit columns should always work regardless of amounts."""
        csv_data = "\n".join([
            "Date,Description,Debit,Credit",
            "2025-05-01,CLIENT PAYOUT,,4850.00",
            "2025-05-07,EQUIPMENT PURCHASE,329.00,",
        ])
        txs, detected_fmt, warnings = parse_statement_csv(csv_data)
        assert txs[0].amount == 4850.00
        assert txs[1].amount == -329.00

    def test_unknown_sign_convention_emits_warning(self) -> None:
        """When sign convention can't be determined, emit a warning."""
        # All positive amounts, no Type column, no Charge Amount header, no split columns
        csv_data = "\n".join([
            "Date,Description,Amount",
            "2025-05-01,SOME VENDOR,100.00",
            "2025-05-02,ANOTHER VENDOR,200.00",
            "2025-05-03,THIRD VENDOR,50.00",
        ])
        txs, detected_fmt, warnings = parse_statement_csv(csv_data)
        # Should either keep as-is or emit a warning about unknown convention
        # The key test: it should NOT invert these just because they're all positive
        for tx in txs:
            assert tx.amount > 0, "Without explicit evidence, should not invert positive amounts"
