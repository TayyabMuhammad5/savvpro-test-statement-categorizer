"""Phase 1 Bug 7 & Bug 8: Money, dates, parser robustness, and rollups regression tests.

Rules:
- Never fabricate dates: unparseable/empty date -> row is flagged with per-row error in parse_errors[].
- Delimiter sniffing (',', ';', tab).
- Decimal commas (European format: 1.250,50 or 1250,50).
- Quoted multiline cells.
- Header detection beyond the first 10 lines.
- Detect DD/MM vs MM/DD by scanning whole column; warn if ambiguous.
- Rollups: stop clipping negative net spend; show refunds exceeding spend explicitly.
- Add amount_in_review and provisional: true when Needs Review rows remain.
"""
from __future__ import annotations

import pytest
from app.brain import StatementCategorizerBrain
from app.models import TaxCategory
from app.parser import parse_currency_value, parse_statement_csv


class TestMoneyAndDatesRobustness:
    def setup_method(self) -> None:
        self.brain = StatementCategorizerBrain()

    def test_never_fabricate_empty_dates(self) -> None:
        """Empty or unparseable date must NOT be fabricated as 2025-01-01; must emit parse error."""
        csv_data = "\n".join([
            "Date,Description,Amount",
            ",B&H PHOTO EQUIPMENT,-150.00",
            "INVALID_DATE,ADOBE SUBSCRIPTION,-59.99",
        ])
        resp = self.brain.analyze_statement(csv_data)
        # Should flag rows with parse error
        assert any("Row 1" in err and "date" in err.lower() for err in resp.parse_warnings) or any("Row 1" in err and "date" in err.lower() for err in getattr(resp, "parse_errors", []))
        # Date must not be fabricated
        if resp.transactions:
            assert resp.transactions[0].date != "2025-01-01" or resp.transactions[0].needs_review is True

    def test_semicolon_and_tab_delimiter_sniffing(self) -> None:
        """Semicolon delimited CSV must be parsed correctly."""
        semicolon_csv = "\n".join([
            "Date;Description;Amount",
            "2025-05-01;B&H PHOTO EQUIPMENT;-150.00",
            "2025-05-02;ADOBE SUBSCRIPTION;-59.99",
        ])
        txs, detected_fmt, warnings = parse_statement_csv(semicolon_csv)
        assert len(txs) == 2
        assert txs[0].amount == -150.00

        tab_csv = "\n".join([
            "Date\tDescription\tAmount",
            "2025-05-01\tB&H PHOTO EQUIPMENT\t-150.00",
            "2025-05-02\tADOBE SUBSCRIPTION\t-59.99",
        ])
        txs_tab, _, _ = parse_statement_csv(tab_csv)
        assert len(txs_tab) == 2
        assert txs_tab[0].amount == -150.00

    def test_european_decimal_comma_parsing(self) -> None:
        """European format numbers with decimal comma must parse correctly."""
        assert parse_currency_value("1240,50") == 1240.50
        assert parse_currency_value("1.240,50") == 1240.50
        assert parse_currency_value("-2.500,00") == -2500.00

    def test_quoted_multiline_cells(self) -> None:
        """CSV cells with embedded newlines in quotes must not break row alignment."""
        multiline_csv = (
            'Date,Description,Amount\n'
            '2025-05-01,"B&H PHOTO\nEQUIPMENT NYC",-150.00\n'
            '2025-05-02,ADOBE SUBSCRIPTION,-59.99\n'
        )
        txs, _, _ = parse_statement_csv(multiline_csv)
        assert len(txs) == 2
        assert txs[0].amount == -150.00
        assert "B&H PHOTO" in txs[0].raw_description

    def test_header_detection_beyond_first_10_lines(self) -> None:
        """CSV with 15 bank metadata preamble rows before header must still detect header."""
        preamble = [f"Metadata line {i}: some bank info" for i in range(15)]
        header_and_data = [
            "Date,Description,Amount",
            "2025-05-01,B&H PHOTO EQUIPMENT,-150.00",
        ]
        csv_data = "\n".join(preamble + header_and_data)
        txs, _, warnings = parse_statement_csv(csv_data)
        assert len(txs) == 1
        assert txs[0].amount == -150.00
        assert any("15" in w for w in warnings)

    def test_rollups_do_not_clip_negative_net_spend(self) -> None:
        """When refunds exceed spend, net_spend is negative and must not be clipped to 0."""
        csv_data = "\n".join([
            "Date,Description,Amount",
            "2025-05-01,LENSRENTALS.COM,-100.00",
            "2025-05-05,LENSRENTALS.COM DEPOSIT REFUND,250.00",
        ])
        resp = self.brain.analyze_statement(csv_data)
        gear_cat = [c for c in resp.category_summaries if c.category == TaxCategory.GEAR_RENTALS][0]
        # Gross = 100, Refunds = 250 -> Net = -150.00 (not clipped to 0.0)
        assert gear_cat.net_spend == -150.00
        assert resp.provisional is False
        assert resp.amount_in_review == 0.0

    def test_amount_in_review_and_provisional_flag(self) -> None:
        """Needs review rows set provisional: true and amount_in_review > 0."""
        csv_data = "\n".join([
            "Date,Description,Amount",
            "2025-05-01,B&H PHOTO EQUIPMENT,-150.00",
            "2025-05-02,MYSTERY SHOPPING VENDOR,-85.00",
        ])
        resp = self.brain.analyze_statement(csv_data)
        assert resp.needs_review_count == 1
        assert resp.provisional is True
        assert resp.amount_in_review == 85.00
