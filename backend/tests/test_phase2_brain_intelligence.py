from __future__ import annotations

import os
from pathlib import Path
import pytest

from app.brain import StatementCategorizerBrain
from app.models import RawTransaction, TaxCategory, TaxFlag, TransactionType
from app.rules import (
    MERCHANT_RULES,
    SCHEDULE_C_MAPPING,
    load_rules_from_yaml,
)


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


class TestPhase2BrainIntelligence:
    def test_rules_yaml_validation_and_taxonomy_count(self) -> None:
        """
        Verify that all rules in YAML validate against Pydantic schema,
        the taxonomy covers >= 150 photography & publishing studio vendors,
        and each rule includes >= 2 positive and >= 2 negative test examples that pass.
        """
        rules_data = load_rules_from_yaml()
        assert len(rules_data["merchants"]) >= 150, f"Expected >= 150 merchant rules, got {len(rules_data['merchants'])}"

        # Validate examples for all merchant rules
        for rule in rules_data["merchants"]:
            assert len(rule.positive_examples) >= 2, f"Rule {rule.rule_id} missing positive examples"
            assert len(rule.negative_examples) >= 2, f"Rule {rule.rule_id} missing negative examples"
            
            for pos in rule.positive_examples:
                assert rule.pattern.search(pos), f"Rule {rule.rule_id} failed to match positive example '{pos}'"
            for neg in rule.negative_examples:
                assert not rule.pattern.search(neg), f"Rule {rule.rule_id} unexpectedly matched negative example '{neg}'"

    def test_fuzzy_matching_caps_confidence_and_routes_to_review(self) -> None:
        """
        Typo in merchant should be caught by Levenshtein fuzzy matching,
        suggesting the vendor category but capping confidence at <= 0.65
        so it safely routes to Needs Review.
        """
        brain = StatementCategorizerBrain()
        seen = {}
        # Typo: 'LENSRENTLS' instead of 'LENSRENTALS'
        tx = brain.categorize_row(make_tx("LENSRENTLS MEMPHIS TN", -340.00, 1), seen)
        assert tx.needs_review is True
        assert tx.category == TaxCategory.NEEDS_REVIEW
        assert tx.confidence <= 0.65
        assert TaxCategory.GEAR_RENTALS in tx.suggested_categories
        assert any("fuzzy" in s.layer.lower() or "fuzzy" in s.rule_id.lower() for s in tx.signals)

    def test_top_alternatives_with_why_not_explanations(self) -> None:
        """
        Categorization must generate top alternative categories with explicit 'why not' reasons.
        """
        brain = StatementCategorizerBrain()
        seen = {}
        tx = brain.categorize_row(make_tx("B&H PHOTO 800-606-6969 NY", -450.00, 1), seen)
        assert tx.category == TaxCategory.CAMERA_EQUIPMENT
        assert len(tx.suggested_categories) >= 1
        assert tx.alternative_reasons is not None
        assert len(tx.alternative_reasons) >= 1

    def test_tax_guardrails_permits_contract_labor_and_mileage(self) -> None:
        """
        Test Schedule C line mappings:
        - Permits -> Line 23
        - Second shooter / contract labor -> Line 11
        - Mileage note on gas / auto expenses
        - Not tax advice disclaimer on statement analysis response
        """
        # Line 23 for location permits
        assert "Line 23" in SCHEDULE_C_MAPPING[TaxCategory.STUDIO_LOCATIONS][0] or \
               "Line 23" in SCHEDULE_C_MAPPING[TaxCategory.STUDIO_LOCATIONS][0]

        brain = StatementCategorizerBrain()
        seen = {}
        
        # Contract labor / second shooter
        assistant_tx = brain.categorize_row(make_tx("PHOTO ASSISTANT SECOND SHOOTER DAY RATE", -500.00, 1), seen)
        assert assistant_tx.category == TaxCategory.CONTRACT_LABOR
        assert "Line 11" in SCHEDULE_C_MAPPING[TaxCategory.CONTRACT_LABOR][0]
        
        # Gas / mileage note
        gas_tx = brain.categorize_row(make_tx("CHEVRON 0092144 LOS ANGELES CA", -65.00, 2), seen)
        assert gas_tx.needs_review is True  # Ambiguous trap
        assert gas_tx.tax_note is not None
        assert "mileage" in gas_tx.tax_note.lower()

        # Disclaimer on response
        csv_data = "Date,Description,Amount\n2025-03-01,ADOBE *CREATIVE CLOUD,-59.99\n"
        res = brain.analyze_statement(csv_data)
        assert hasattr(res, "tax_disclaimer")
        assert "not tax advice" in res.tax_disclaimer.lower()

    def test_bank_category_and_recurrence_signals(self) -> None:
        """
        Bank-provided category and recurring monthly charges should generate signals.
        """
        brain = StatementCategorizerBrain()
        csv_data = "\n".join([
            "Date,Description,Amount,Category",
            "2025-01-15,ADOBE *CREATIVE CLOUD,-59.99,Professional Services",
            "2025-02-15,ADOBE *CREATIVE CLOUD,-59.99,Professional Services",
            "2025-03-15,ADOBE *CREATIVE CLOUD,-59.99,Professional Services",
        ])
        res = brain.analyze_statement(csv_data)
        adobe_tx = res.transactions[2]
        signal_layers = [s.layer for s in adobe_tx.signals]
        assert any("Recurrence" in layer or "Subscription" in layer for layer in signal_layers)
        assert any("Bank Category" in layer for layer in signal_layers)
