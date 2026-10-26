from __future__ import annotations

import unittest
from app.parser import normalize_merchant_name, parse_currency_value, parse_statement_csv
from app.sample_data import (
    AMEX_EDITORIAL_SHOOT_CSV,
    CHASE_STUDIO_CREDIT_CARD_CSV,
    MERCURY_STUDIO_CHECKING_CSV,
)


class TestStatementParser(unittest.TestCase):
    def test_currency_parsing_variations(self) -> None:
        self.assertEqual(parse_currency_value("$1,240.50"), 1240.50)
        self.assertEqual(parse_currency_value("($45.00)"), -45.00)
        self.assertEqual(parse_currency_value("-3299.00"), -3299.00)
        self.assertEqual(parse_currency_value("120.00 CR"), -120.00)
        self.assertIsNone(parse_currency_value(""))
        self.assertIsNone(parse_currency_value("--"))

    def test_merchant_normalization_strips_bank_noise(self) -> None:
        self.assertEqual(normalize_merchant_name("POS DEBIT - B&H PHOTO 800-606-6969 NY"), "B&H PHOTO NY")
        self.assertEqual(normalize_merchant_name("TST* BLUE BOTTLE COFFEE #4412"), "BLUE BOTTLE COFFEE")
        self.assertEqual(normalize_merchant_name("LENSRENTALS.COM DEPOSIT RETURN"), "LENSRENTALS.COM")

    def test_amex_preamble_and_sign_inversion(self) -> None:
        txs, detected_fmt, warnings = parse_statement_csv(AMEX_EDITORIAL_SHOOT_CSV)
        self.assertTrue("Amex" in detected_fmt or "Positive-Charge" in detected_fmt)
        self.assertEqual(len(warnings), 1)
        self.assertEqual(len(txs), 14)
        self.assertEqual(txs[0].amount, -618.40)
        adorama_credit = [t for t in txs if "RETURN CREDIT" in t.raw_description][0]
        self.assertEqual(adorama_credit.amount, 79.00)

    def test_mercury_split_debit_credit_columns(self) -> None:
        txs, detected_fmt, _ = parse_statement_csv(MERCURY_STUDIO_CHECKING_CSV)
        self.assertIn("Split Debit/Credit", detected_fmt)
        self.assertEqual(len(txs), 13)
        self.assertEqual(txs[0].amount, 4850.00)
        self.assertEqual(txs[3].amount, -2890.00)

    def test_chase_signed_single_column(self) -> None:
        txs, detected_fmt, _ = parse_statement_csv(CHASE_STUDIO_CREDIT_CARD_CSV)
        self.assertIn("Single-Column", detected_fmt)
        self.assertEqual(len(txs), 22)
        self.assertEqual(txs[0].amount, -3299.00)


if __name__ == "__main__":
    unittest.main()
