from __future__ import annotations

import unittest
from app.main import analyze_statement_payload, health_check, list_categories, list_presets
from app.models import BatchAnalyzeRequest, TaxCategory
from app.sample_data import CHASE_STUDIO_CREDIT_CARD_CSV


class TestStatementAPI(unittest.TestCase):
    def test_health_and_metadata_endpoints(self) -> None:
        health = health_check()
        self.assertEqual(health["status"], "ok")
        self.assertIn("Zero-LLM", health["engine"])

        cats = list_categories()
        self.assertGreaterEqual(len(cats), 14)

        presets = list_presets()
        self.assertGreaterEqual(len(presets), 3)

    def test_analyze_endpoint_with_custom_rules(self) -> None:
        req = BatchAnalyzeRequest(
            statement_name="chase_test.csv",
            csv_content=CHASE_STUDIO_CREDIT_CARD_CSV,
            custom_rules={"JOES CAFE 9921 BROOKLYN NY": TaxCategory.CLIENT_CREW_MEALS.value},
        )
        res = analyze_statement_payload(req)
        self.assertEqual(res.total_rows, 22)
        joes = [t for t in res.transactions if "JOES CAFE" in t.raw_description][0]
        self.assertEqual(joes.category, TaxCategory.CLIENT_CREW_MEALS)
        self.assertFalse(joes.needs_review)


if __name__ == "__main__":
    unittest.main()
