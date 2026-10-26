from __future__ import annotations

import unittest
from app.brain import StatementCategorizerBrain
from app.models import RawTransaction, TaxCategory, TaxFlag, TransactionType
from app.sample_data import (
    AMEX_EDITORIAL_SHOOT_CSV,
    CHASE_STUDIO_CREDIT_CARD_CSV,
    MERCURY_STUDIO_CHECKING_CSV,
)


def make_tx(
    desc: str,
    amount: float,
    row_index: int = 1,
    date: str = "2025-03-10",
    status: str | None = None,
) -> RawTransaction:
    return RawTransaction(
        row_index=row_index,
        date=date,
        raw_description=desc,
        amount=amount,
        raw_status=status,
    )


class TestStatementCategorizerBrain(unittest.TestCase):
    def test_core_photography_and_photobook_categories(self) -> None:
        brain = StatementCategorizerBrain()
        seen = {}

        # Photobook printing -> Photobook Printing & Lab COGS
        blurb = brain.categorize_row(make_tx("BLURB *BOOK PRINT RUN SAN FRANCISCO CA", -1420.50, 1), seen)
        self.assertEqual(blurb.category, TaxCategory.PHOTOBOOK_PRINTING)
        self.assertEqual(blurb.transaction_type, TransactionType.EXPENSE)
        self.assertFalse(blurb.needs_review)
        self.assertGreaterEqual(blurb.confidence, 0.90)

        # Lens rental -> Gear & Lens Rentals
        lens = brain.categorize_row(make_tx("LENSRENTALS.COM 901-754-9100 TN", -485.00, 2), seen)
        self.assertEqual(lens.category, TaxCategory.GEAR_RENTALS)
        self.assertFalse(lens.needs_review)

        # Editing software -> Software & Digital Workflow
        adobe = brain.categorize_row(make_tx("ADOBE *PHOTOGRAPHY PLAN", -59.99, 3), seen)
        self.assertEqual(adobe.category, TaxCategory.SOFTWARE_WORKFLOW)
        self.assertFalse(adobe.needs_review)

        # Reference photobooks -> Props, Styling & Reference Books
        strand = brain.categorize_row(make_tx("STRAND BOOK STORE 828 BROADWAY NY", -195.00, 4), seen)
        self.assertEqual(strand.category, TaxCategory.PROPS_REFERENCE_BOOKS)
        self.assertFalse(strand.needs_review)

    def test_refund_is_contra_expense_not_income(self) -> None:
        """
        Critical assessment rule: 'a refund is money back, not income.'
        Verify that positive credits from LensRentals, Blurb, and B&H Photo reduce category
        spend (contra-expense) rather than inflating Gross Income.
        """
        brain = StatementCategorizerBrain()
        csv_data = "\n".join([
            "Date,Description,Amount",
            "2025-03-04,LENSRENTALS.COM RENTAL,-485.00",
            "2025-03-08,LENSRENTALS.COM DEPOSIT RETURN,150.00",
            "2025-03-10,BLURB *BOOK PRINT RUN,-1000.00",
            "2025-03-12,BLURB *DEFECT CREDIT,180.00",
            "2025-03-15,HONEYBOOK*CLIENT PAYOUT,3000.00",
        ])
        summary = brain.analyze_statement(csv_data)

        # Gross income must ONLY be the $3,000 HoneyBook client payout, NOT the $330 in refunds
        self.assertEqual(summary.gross_income, 3000.00)
        self.assertEqual(summary.total_refund_offsets, 330.00)
        self.assertEqual(summary.gross_expenses, 1485.00)
        self.assertEqual(summary.net_expenses, 1155.00)

        refund_tx = [t for t in summary.transactions if "DEPOSIT RETURN" in t.raw_description][0]
        self.assertEqual(refund_tx.transaction_type, TransactionType.REFUND)
        self.assertEqual(refund_tx.category, TaxCategory.GEAR_RENTALS)
        self.assertEqual(refund_tx.tax_flag, TaxFlag.CONTRA_EXPENSE_REFUND)
        self.assertEqual(refund_tx.deductible_impact, -150.00)

    def test_transfers_and_autopay_excluded_from_spending_and_income(self) -> None:
        """
        Prompt rule: 'TRANSFER TO SAVINGS is not spending' and credit card autopay is not income.
        """
        brain = StatementCategorizerBrain()
        csv_data = "\n".join([
            "Date,Description,Amount",
            "2025-03-10,ONLINE TRANSFER TO SAVINGS,-2000.00",
            "2025-03-15,OWNER DRAW ACH TRANSFER TO SELF,-3500.00",
            "2025-03-31,AUTOMATIC PAYMENT - THANK YOU,4500.00",
        ])
        summary = brain.analyze_statement(csv_data)

        self.assertEqual(summary.gross_income, 0.0)
        self.assertEqual(summary.gross_expenses, 0.0)
        self.assertEqual(summary.estimated_deductible_total, 0.0)
        self.assertEqual(summary.transfer_count, 3)
        for tx in summary.transactions:
            self.assertEqual(tx.category, TaxCategory.NON_DEDUCTIBLE_TRANSFER)
            self.assertEqual(tx.transaction_type, TransactionType.TRANSFER)
            self.assertFalse(tx.needs_review)

    def test_ambiguous_and_unknown_merchants_go_to_needs_review(self) -> None:
        """
        Prompt rule: 'JOES CAFE 9921 is unknown, so it goes to Needs Review. If the app is not sure, it must say so.'
        """
        brain = StatementCategorizerBrain()
        seen = {}

        joes = brain.categorize_row(make_tx("JOES CAFE 9921 BROOKLYN NY", -18.75, 1), seen)
        self.assertTrue(joes.needs_review)
        self.assertEqual(joes.category, TaxCategory.NEEDS_REVIEW)
        self.assertLess(joes.confidence, 0.70)

        amazon = brain.categorize_row(make_tx("AMAZON.COM*MKTPL 8821WA", -142.65, 2), seen)
        self.assertTrue(amazon.needs_review)
        self.assertEqual(amazon.category, TaxCategory.NEEDS_REVIEW)
        self.assertIn(TaxCategory.CAMERA_EQUIPMENT, amazon.suggested_categories)

        venmo = brain.categorize_row(make_tx("VENMO *MARCUS VANCE", -250.00, 3), seen)
        self.assertTrue(venmo.needs_review)
        self.assertEqual(venmo.category, TaxCategory.NEEDS_REVIEW)

        unknown = brain.categorize_row(make_tx("ZXY9918 MYSTERY VENDOR LLC", -88.00, 4), seen)
        self.assertTrue(unknown.needs_review)
        self.assertEqual(unknown.category, TaxCategory.NEEDS_REVIEW)

    def test_section_179_high_value_camera_equipment_flag(self) -> None:
        brain = StatementCategorizerBrain()
        seen = {}

        high_val = brain.categorize_row(make_tx("B&H PHOTO 800-606-6969 NY", -3299.00, 1), seen)
        self.assertEqual(high_val.category, TaxCategory.CAMERA_EQUIPMENT)
        self.assertEqual(high_val.tax_flag, TaxFlag.SECTION_179_CANDIDATE)
        self.assertIn("Section 179", high_val.tax_note or "")

        small_val = brain.categorize_row(make_tx("B&H PHOTO 800-606-6969 NY", -149.00, 2), seen)
        self.assertEqual(small_val.category, TaxCategory.CAMERA_EQUIPMENT)
        self.assertEqual(small_val.tax_flag, TaxFlag.NONE)

    def test_meals_50_percent_deduction_calculation(self) -> None:
        brain = StatementCategorizerBrain()
        seen = {}

        catering = brain.categorize_row(make_tx("EZCATER*SHOOT CREW LUNCH", -200.00, 1), seen)
        self.assertEqual(catering.category, TaxCategory.CLIENT_CREW_MEALS)
        self.assertEqual(catering.deductible_rate, 0.5)
        self.assertEqual(catering.deductible_impact, 100.00)
        self.assertEqual(catering.tax_flag, TaxFlag.MEALS_50_PERCENT)

    def test_pending_and_duplicate_row_detection(self) -> None:
        brain = StatementCategorizerBrain()
        csv_data = "\n".join([
            "Date,Description,Amount,Status",
            "2025-04-05,INDIE FILM LAB MONTGOMERY AL,-284.00,Posted",
            "2025-04-05,INDIE FILM LAB MONTGOMERY AL,-284.00,Posted",
            "2025-04-06,LENSRENTALS.COM PENDING AUTH HOLD,-485.00,Pending",
        ])
        summary = brain.analyze_statement(csv_data)

        self.assertEqual(summary.gross_expenses, 284.00)
        self.assertEqual(summary.duplicate_or_pending_count, 2)
        self.assertEqual(summary.transactions[1].transaction_type, TransactionType.DUPLICATE)
        self.assertTrue(summary.transactions[1].needs_review)
        self.assertEqual(summary.transactions[2].transaction_type, TransactionType.DUPLICATE)
        self.assertTrue(summary.transactions[2].needs_review)

    def test_word_boundary_prevents_substring_false_positives(self) -> None:
        """
        Regression test for AI substring trap: 'SCHUBERT ARCHIVAL BINDERY' contains 'UBER',
        but must NOT be categorized as 'Shoot Travel & Transport'.
        """
        brain = StatementCategorizerBrain()
        seen = {}
        tx = brain.categorize_row(make_tx("SCHUBERT ARCHIVAL BINDERY LLC", -320.00, 1), seen)
        self.assertEqual(tx.category, TaxCategory.PHOTOBOOK_PRINTING)
        self.assertNotEqual(tx.category, TaxCategory.TRAVEL_TRANSPORT)

    def test_user_learned_merchant_rule_override(self) -> None:
        brain = StatementCategorizerBrain()
        brain.learn_merchant_rule("JOES CAFE 9921 BROOKLYN NY", TaxCategory.CLIENT_CREW_MEALS)
        seen = {}
        tx = brain.categorize_row(make_tx("JOES CAFE 9921 BROOKLYN NY", -18.75, 1), seen)
        self.assertFalse(tx.needs_review)
        self.assertEqual(tx.category, TaxCategory.CLIENT_CREW_MEALS)
        self.assertTrue(tx.user_overridden)

    def test_all_three_sample_statements_analyze_cleanly(self) -> None:
        brain = StatementCategorizerBrain()
        for csv_blob in (
            CHASE_STUDIO_CREDIT_CARD_CSV,
            AMEX_EDITORIAL_SHOOT_CSV,
            MERCURY_STUDIO_CHECKING_CSV,
        ):
            res = brain.analyze_statement(csv_blob)
            self.assertGreaterEqual(res.total_rows, 13)
            self.assertGreaterEqual(res.needs_review_count, 2)
            self.assertGreaterEqual(res.auto_categorized_count, 8)


if __name__ == "__main__":
    unittest.main()
