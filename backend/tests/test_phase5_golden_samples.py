from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.brain import StatementCategorizerBrain
from app.main import app
from app.models import TaxCategory, TaxFlag, TransactionType
from app.sample_data import (
    AMEX_EDITORIAL_SHOOT_CSV,
    CHASE_STUDIO_CREDIT_CARD_CSV,
    EUROPEAN_SEMICOLON_DECIMAL_COMMA_CSV,
    INCOME_HEAVY_COMMERCIAL_CHECKING_CSV,
    MERCURY_STUDIO_CHECKING_CSV,
    QUOTED_MULTILINE_PREAMBLE_CSV,
    SAMPLE_STATEMENTS,
)


client = TestClient(app)


class TestPhase5GoldenSamples:
    @pytest.fixture(autouse=True)
    def setup_brain(self) -> None:
        self.brain = StatementCategorizerBrain()

    def test_presets_api_returns_all_six_sample_statements(self) -> None:
        """API /api/presets and /api/v1/presets must return all 6 curated sample statements."""
        response = client.get("/api/presets")
        assert response.status_code == 200
        presets = response.json()
        assert len(presets) == 6
        preset_ids = {p["id"] for p in presets}
        assert "chase_studio_card" in preset_ids
        assert "amex_editorial_shoot" in preset_ids
        assert "mercury_studio_checking" in preset_ids
        assert "european_semicolon_decimal_comma" in preset_ids
        assert "income_heavy_commercial_checking" in preset_ids
        assert "quoted_multiline_preamble" in preset_ids

    def test_golden_chase_studio_credit_card(self) -> None:
        """Chase Ink Studio Card golden snapshot test."""
        res = self.brain.analyze_statement(CHASE_STUDIO_CREDIT_CARD_CSV, "chase.csv")
        assert res.total_rows == 22
        assert "Single-Column" in res.detected_bank_format

        # B&H Photo lens ($3,299) must be Camera Equipment with Section 179 flag
        bh = next(t for t in res.transactions if "B&H PHOTO" in t.raw_description)
        assert bh.category == TaxCategory.CAMERA_EQUIPMENT
        assert bh.tax_flag == TaxFlag.SECTION_179_CANDIDATE
        assert bh.deductible_rate == 1.0

        # LensRentals deposit return ($150) must be contra-expense refund
        lr_refund = next(t for t in res.transactions if "DEPOSIT RETURN" in t.raw_description)
        assert lr_refund.transaction_type == TransactionType.REFUND
        assert lr_refund.category == TaxCategory.GEAR_RENTALS

        # Blurb defect credit ($180) must reduce printing COGS, not inflate income
        blurb_credit = next(t for t in res.transactions if "DEFECT CREDIT" in t.raw_description)
        assert blurb_credit.transaction_type == TransactionType.REFUND
        assert blurb_credit.category == TaxCategory.PHOTOBOOK_PRINTING

        # Autopay ($4,500) must be excluded transfer
        autopay = next(t for t in res.transactions if "AUTOMATIC PAYMENT" in t.raw_description)
        assert autopay.transaction_type == TransactionType.TRANSFER
        assert autopay.category == TaxCategory.NON_DEDUCTIBLE_TRANSFER

        # Ensure totals are computed properly
        assert res.total_refund_offsets > 0
        assert res.estimated_deductible_total > 0

    def test_golden_amex_editorial_shoot(self) -> None:
        """Amex Editorial Shoot golden snapshot test (positive charges + preamble)."""
        res = self.brain.analyze_statement(AMEX_EDITORIAL_SHOOT_CSV, "amex.csv")
        assert res.total_rows == 14
        assert "Amex" in res.detected_bank_format or "Positive-Charge" in res.detected_bank_format

        # Delta Air Lines must be negative outflow (expense)
        delta = next(t for t in res.transactions if "DELTA AIR LINES" in t.raw_description)
        assert delta.amount < 0
        assert delta.category == TaxCategory.TRAVEL_TRANSPORT

        # LA Art Book Fair booth must be marketing/portfolio
        booth = next(t for t in res.transactions if "LA ART BOOK FAIR" in t.raw_description)
        assert booth.amount < 0
        assert booth.category == TaxCategory.MARKETING_BOOK_FAIRS

        # Adorama return credit (-$79 on statement inverted to +$79) must be refund
        ado_ret = next(t for t in res.transactions if "RETURN CREDIT" in t.raw_description)
        assert ado_ret.amount > 0
        assert ado_ret.transaction_type == TransactionType.REFUND
        assert ado_ret.category == TaxCategory.CAMERA_EQUIPMENT

        # Amex ePayment must be transfer
        pmt = next(t for t in res.transactions if "EPAYMENT" in t.raw_description)
        assert pmt.category == TaxCategory.NON_DEDUCTIBLE_TRANSFER

    def test_golden_mercury_studio_checking(self) -> None:
        """Mercury Studio Checking golden snapshot test (split debit/credit)."""
        res = self.brain.analyze_statement(MERCURY_STUDIO_CHECKING_CSV, "mercury.csv")
        assert res.total_rows == 13
        assert "Split" in res.detected_bank_format

        # HoneyBook payout ($4,850) must be studio income
        hb = next(t for t in res.transactions if "HONEYBOOK" in t.raw_description)
        assert hb.amount > 0
        assert hb.category == TaxCategory.CLIENT_BOOK_INCOME
        assert hb.transaction_type == TransactionType.INCOME

        # Edition One Books ($2,890) must be printing COGS
        ed_one = next(t for t in res.transactions if "EDITION ONE" in t.raw_description)
        assert ed_one.amount < 0
        assert ed_one.category == TaxCategory.PHOTOBOOK_PRINTING

        # Owner draw ($3,500) must be transfer
        draw = next(t for t in res.transactions if "OWNER DRAW" in t.raw_description)
        assert draw.category == TaxCategory.NON_DEDUCTIBLE_TRANSFER

    def test_golden_european_semicolon_decimal_comma(self) -> None:
        """European semicolon delimiter and decimal comma statement snapshot test."""
        res = self.brain.analyze_statement(EUROPEAN_SEMICOLON_DECIMAL_COMMA_CSV, "euro.csv")
        assert res.total_rows == 10

        # Hahnemühle FineArt paper (-485,50 €)
        hahne = next(t for t in res.transactions if "HAHNEMUEHLE" in t.raw_description)
        assert hahne.abs_amount == 485.50
        assert hahne.amount < 0
        assert hahne.category == TaxCategory.PHOTOBOOK_PRINTING

        # Leica Store (-2.850,00 €)
        leica = next(t for t in res.transactions if "LEICA" in t.raw_description)
        assert leica.abs_amount == 2850.00
        assert leica.category == TaxCategory.CAMERA_EQUIPMENT
        assert leica.tax_flag == TaxFlag.SECTION_179_CANDIDATE

        # Blurb EU defect credit (+180,00 €)
        defect = next(t for t in res.transactions if "DEFECT CREDIT" in t.raw_description)
        assert defect.amount == 180.00
        assert defect.transaction_type == TransactionType.REFUND

        # SEPA client advance (+3.500,00 €)
        sepa = next(t for t in res.transactions if "SEPA" in t.raw_description)
        assert sepa.amount == 3500.00
        assert sepa.category == TaxCategory.CLIENT_BOOK_INCOME

    def test_golden_income_heavy_commercial_checking(self) -> None:
        """Income-heavy statement confirms no guessing heuristic (inflows stay positive income)."""
        res = self.brain.analyze_statement(INCOME_HEAVY_COMMERCIAL_CHECKING_CSV, "income_heavy.csv")
        assert res.total_rows == 12

        # 6,500 HoneyBook and 4,200 Vogue wire must remain positive income
        hb = next(t for t in res.transactions if "HONEYBOOK*CLIENT PAYOUT - CAMPAIGN" in t.raw_description)
        assert hb.amount == 6500.00
        assert hb.category == TaxCategory.CLIENT_BOOK_INCOME

        vogue = next(t for t in res.transactions if "VOGUE" in t.raw_description)
        assert vogue.amount == 4200.00
        assert vogue.category == TaxCategory.CLIENT_BOOK_INCOME

        # Wire fee must be bank fee (-15.00)
        wire_fee = next(t for t in res.transactions if "WIRE FEE" in t.raw_description)
        assert wire_fee.amount == -15.00
        assert wire_fee.category == TaxCategory.BANK_MERCHANT_FEES

    def test_golden_quoted_multiline_preamble(self) -> None:
        """Preamble headers skipped and multiline quoted cells parsed with zero row-splitting errors."""
        res = self.brain.analyze_statement(QUOTED_MULTILINE_PREAMBLE_CSV, "preamble.csv")
        assert res.total_rows == 9

        # Multiline B&H Photo row
        bh = next(t for t in res.transactions if "B&H PHOTO" in t.raw_description)
        assert bh.abs_amount == 2850.00
        assert bh.category == TaxCategory.CAMERA_EQUIPMENT
        assert bh.tax_flag == TaxFlag.SECTION_179_CANDIDATE

        # Multiline LensRentals row
        lr = next(t for t in res.transactions if "LENSRENTALS" in t.raw_description)
        assert lr.category == TaxCategory.GEAR_RENTALS
