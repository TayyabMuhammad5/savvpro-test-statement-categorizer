"""
Evaluation Suite for Statement Categorizer Brain (Deterministic Engine).
Evaluates accuracy, precision, review rate, and safety against labeled ground truth.
"""
from __future__ import annotations

import csv
from pathlib import Path
import sys

# Add backend directory to sys.path so app modules import cleanly
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "backend"))

from app.brain import StatementCategorizerBrain
from app.models import TaxCategory, TransactionType


def run_evaluation(csv_path: Path | None = None) -> dict:
    if csv_path is None:
        csv_path = Path(__file__).parent / "labeled_transactions.csv"

    if not csv_path.exists():
        raise FileNotFoundError(f"Evaluation dataset not found at {csv_path}")

    # Read ground truth
    ground_truth = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ground_truth.append({
                "date": row["Date"],
                "description": row["Description"],
                "amount": float(row["Amount"]),
                "expected_category": row["Expected_Category"].strip(),
                "expected_type": row["Expected_Type"].strip().lower(),
            })

    total_rows = len(ground_truth)
    if total_rows == 0:
        raise ValueError("Evaluation dataset is empty.")

    # Format input CSV for the Brain
    csv_lines = ["Date,Description,Amount"]
    for row in ground_truth:
        csv_lines.append(f"{row['date']},{row['description']},{row['amount']}")
    csv_content = "\n".join(csv_lines)

    brain = StatementCategorizerBrain()
    response = brain.analyze_statement(csv_content, statement_name="eval_benchmark.csv")

    auto_count = 0
    review_count = 0
    correct_auto = 0
    misclassified_auto = []
    correct_review_abstentions = 0

    category_stats = {}

    for i, tx in enumerate(response.transactions):
        gt = ground_truth[i]
        exp_cat = gt["expected_category"]
        exp_type = gt["expected_type"]

        is_auto = not tx.needs_review and tx.category != TaxCategory.NEEDS_REVIEW

        cat_key = exp_cat
        if cat_key not in category_stats:
            category_stats[cat_key] = {"total": 0, "auto": 0, "review": 0, "correct": 0}
        category_stats[cat_key]["total"] += 1

        if is_auto:
            auto_count += 1
            category_stats[cat_key]["auto"] += 1
            cat_match = (tx.category.value == exp_cat)
            type_match = (tx.transaction_type.value == exp_type)
            if cat_match and type_match:
                correct_auto += 1
                category_stats[cat_key]["correct"] += 1
            else:
                misclassified_auto.append({
                    "row": i + 1,
                    "description": tx.raw_description,
                    "amount": tx.amount,
                    "expected_category": exp_cat,
                    "predicted_category": tx.category.value,
                    "expected_type": exp_type,
                    "predicted_type": tx.transaction_type.value,
                    "matched_rule": tx.matched_rule,
                })
        else:
            review_count += 1
            category_stats[cat_key]["review"] += 1
            if exp_cat == TaxCategory.NEEDS_REVIEW.value:
                correct_review_abstentions += 1

    auto_pct = (auto_count / total_rows) * 100
    review_pct = (review_count / total_rows) * 100
    precision = (correct_auto / auto_count * 100) if auto_count > 0 else 0.0

    print("=" * 80)
    print("      DETERMINISTIC BRAIN BENCHMARK & EVALUATION REPORT")
    print("=" * 80)
    print(f"Total Labeled Benchmark Rows   : {total_rows}")
    print(f"Auto-Categorized Decisions     : {auto_count} ({auto_pct:.1f}%)")
    print(f"Routed to 'Needs Review'       : {review_count} ({review_pct:.1f}%)")
    print(f"Auto-Categorization Precision  : {precision:.2f}%  (Target: >= 98.0%)")
    print(f"Misclassified Auto Rows Count  : {len(misclassified_auto)}")
    print("-" * 80)
    print(f"{'Category':<38} | {'Total':<6} | {'Auto':<6} | {'Review':<7} | {'Precision':<8}")
    print("-" * 80)
    for cat_name, stats in sorted(category_stats.items()):
        cat_prec = (stats["correct"] / stats["auto"] * 100) if stats["auto"] > 0 else 100.0
        print(f"{cat_name:<38} | {stats['total']:<6} | {stats['auto']:<6} | {stats['review']:<7} | {cat_prec:.1f}%")
    print("-" * 80)

    if misclassified_auto:
        print("\nMISCLASSIFIED ROWS DETAILS:")
        for m in misclassified_auto:
            print(f"  Row {m['row']}: '{m['description']}' (${m['amount']:.2f})")
            print(f"    Expected: [{m['expected_category']}] ({m['expected_type']})")
            print(f"    Got     : [{m['predicted_category']}] ({m['predicted_type']}) via {m['matched_rule']}")
        print("-" * 80)

    results = {
        "total_rows": total_rows,
        "auto_count": auto_count,
        "auto_pct": auto_pct,
        "review_count": review_count,
        "review_pct": review_pct,
        "correct_auto": correct_auto,
        "precision": precision,
        "misclassified": misclassified_auto,
    }
    return results


if __name__ == "__main__":
    res = run_evaluation()
    if res["precision"] < 98.0:
        print(f"FAILED: Precision {res['precision']:.2f}% is below 98.0% threshold!")
        sys.exit(1)
    else:
        print(f"SUCCESS: Brain achieved {res['precision']:.2f}% precision on benchmark dataset!")
