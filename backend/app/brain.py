from __future__ import annotations

import re
from collections import defaultdict
from typing import Dict, List, Optional, Tuple
from .models import (
    CategorizedTransaction,
    CategorySummary,
    DecisionSignal,
    RawTransaction,
    StatementAnalysisResponse,
    TaxCategory,
    TaxFlag,
    TransactionType,
)
from .parser import normalize_merchant_name, parse_statement_csv
from .rules import (
    AMBIGUITY_TRAPS,
    EXPENSE_ONLY_CATEGORIES,
    KEYWORD_HEURISTICS,
    MERCHANT_RULES,
    PENDING_INDICATOR_RE,
    REFUND_INDICATOR_RE,
    SCHEDULE_C_MAPPING,
    TRANSFER_RULES,
)

CONFIDENCE_THRESHOLD = 0.70
SECTION_179_THRESHOLD = 2500.00


class StatementCategorizerBrain:
    """
    Deterministic, zero-LLM rule & heuristic categorization engine ("The Brain")
    tailored for an Independent Photography & Photobook Publishing Studio.

    Pipeline per row:
      1. Duplicate & Pending Hold Detector (prevents double-counting unsettled holds)
      2. Non-Expense / Internal Transfer & Autopay Filter
      3. User-Learned Merchant Overrides (in-memory or session-supplied rules)
      4. Curated Domain Regex Rules (Photography & Photobook COGS/OpEx/Income)
      5. Token Keyword & Context Heuristics
      6. Contra-Expense Refund Reconciler (ensures gear/print refunds reduce expenses, never inflate income)
      7. Tax Policy Guardrails (Section 179 >= $2,500 Capital Asset check, 50% Meals cap)
      8. Ambiguity Guardrail & Confidence Gate (< 0.70 -> Needs Review)
    """

    def __init__(self, custom_rules: Optional[Dict[str, TaxCategory]] = None) -> None:
        self.custom_rules: Dict[str, TaxCategory] = {}
        if custom_rules:
            for k, v in custom_rules.items():
                self.custom_rules[normalize_merchant_name(k)] = (
                    v if isinstance(v, TaxCategory) else TaxCategory(v)
                )

    def learn_merchant_rule(self, raw_or_normalized_merchant: str, category: TaxCategory) -> str:
        norm = normalize_merchant_name(raw_or_normalized_merchant)
        self.custom_rules[norm] = category
        return norm

    def categorize_row(
        self,
        tx: RawTransaction,
        seen_signatures: Dict[Tuple[str, str, float], int],
    ) -> CategorizedTransaction:
        norm_merchant = normalize_merchant_name(tx.raw_description)
        combined_text = f"{tx.raw_description} {tx.memo or ''}".strip()
        abs_amt = round(abs(tx.amount), 2)
        signals: List[DecisionSignal] = []

        # -------------------------------------------------------------------
        # Stage 1: Pending Hold & Exact Same-Day Duplicate Detection
        # -------------------------------------------------------------------
        is_pending = bool(
            (tx.raw_status and PENDING_INDICATOR_RE.search(tx.raw_status))
            or PENDING_INDICATOR_RE.search(tx.raw_description)
        )
        sig = (tx.date, norm_merchant, tx.amount)
        prior_row = seen_signatures.get(sig)
        if not is_pending:
            seen_signatures[sig] = tx.row_index

        if is_pending or prior_row is not None:
            reason_msg = (
                "Unsettled PENDING authorization hold — excluded from Schedule C totals until posted."
                if is_pending
                else f"Potential duplicate of Row #{prior_row} (identical date, merchant '{norm_merchant}', and amount ${abs_amt:,.2f}). Verify whether this was a double charge."
            )
            signals.append(
                DecisionSignal(
                    layer="Stage 1: Integrity Guard",
                    rule_id="PENDING_HOLD" if is_pending else "DUPLICATE_ROW",
                    detail=reason_msg,
                    weight=0.0,
                )
            )
            return CategorizedTransaction(
                id=f"tx-{tx.row_index}",
                row_index=tx.row_index,
                date=tx.date,
                raw_description=tx.raw_description,
                normalized_merchant=norm_merchant,
                amount=tx.amount,
                abs_amount=abs_amt,
                category=TaxCategory.NEEDS_REVIEW,
                suggested_categories=[
                    TaxCategory.NON_DEDUCTIBLE_TRANSFER,
                    TaxCategory.GEAR_RENTALS,
                    TaxCategory.CAMERA_EQUIPMENT,
                ],
                transaction_type=TransactionType.DUPLICATE,
                confidence=0.30,
                needs_review=True,
                review_reason=reason_msg,
                explanation=reason_msg,
                matched_rule="PENDING_HOLD" if is_pending else "DUPLICATE_ROW",
                signals=signals,
                tax_flag=TaxFlag.PENDING_OR_DUPLICATE,
                tax_note="Excluded from tax totals to prevent double-counting.",
                deductible_rate=0.0,
                deductible_impact=0.0,
            )

        # -------------------------------------------------------------------
        # Stage 2: Internal Transfers, Credit Card Autopay & Tax Payments
        # -------------------------------------------------------------------
        for tr_rule in TRANSFER_RULES:
            if tr_rule.pattern.search(combined_text):
                signals.append(
                    DecisionSignal(
                        layer="Stage 2: Transfer Filter",
                        rule_id=tr_rule.rule_id,
                        detail=tr_rule.explanation,
                        weight=tr_rule.base_confidence,
                    )
                )
                return CategorizedTransaction(
                    id=f"tx-{tx.row_index}",
                    row_index=tx.row_index,
                    date=tx.date,
                    raw_description=tx.raw_description,
                    normalized_merchant=norm_merchant,
                    amount=tx.amount,
                    abs_amount=abs_amt,
                    category=TaxCategory.NON_DEDUCTIBLE_TRANSFER,
                    suggested_categories=[TaxCategory.NON_DEDUCTIBLE_TRANSFER],
                    transaction_type=TransactionType.TRANSFER,
                    confidence=tr_rule.base_confidence,
                    needs_review=False,
                    explanation=tr_rule.explanation,
                    matched_rule=tr_rule.rule_id,
                    signals=signals,
                    tax_flag=TaxFlag.INTERNAL_TRANSFER,
                    tax_note="Excluded from Schedule C income and expenses.",
                    deductible_rate=0.0,
                    deductible_impact=0.0,
                )

        # -------------------------------------------------------------------
        # Stage 3: User-Learned Custom Merchant Rules
        # -------------------------------------------------------------------
        if norm_merchant in self.custom_rules:
            learned_cat = self.custom_rules[norm_merchant]
            signals.append(
                DecisionSignal(
                    layer="Stage 3: User Learned Rule",
                    rule_id="USER_MERCHANT_MEMORY",
                    detail=f"Matched user-confirmed rule for merchant '{norm_merchant}'.",
                    weight=0.99,
                )
            )
            return self._finalize_categorization(
                tx=tx,
                norm_merchant=norm_merchant,
                combined_text=combined_text,
                category=learned_cat,
                confidence=0.99,
                explanation=f"Categorized via user-saved rule for '{norm_merchant}'.",
                matched_rule="USER_MERCHANT_MEMORY",
                signals=signals,
                tax_flag=TaxFlag.NONE,
                bypass_traps=True,
            )

        # -------------------------------------------------------------------
        # Stage 4: Curated Photography & Photobook Merchant Rules
        # -------------------------------------------------------------------
        matched_category: Optional[TaxCategory] = None
        confidence = 0.0
        explanation = ""
        matched_rule_id = "UNMATCHED"
        tax_flag = TaxFlag.NONE

        for rule in MERCHANT_RULES:
            if rule.pattern.search(combined_text):
                matched_category = rule.category
                confidence = rule.base_confidence
                explanation = rule.explanation
                matched_rule_id = rule.rule_id
                tax_flag = rule.tax_flag
                signals.append(
                    DecisionSignal(
                        layer="Stage 4: Domain Merchant Rule",
                        rule_id=rule.rule_id,
                        detail=rule.explanation,
                        weight=rule.base_confidence,
                    )
                )
                break

        # -------------------------------------------------------------------
        # Stage 5: Keyword & Contextual Heuristics (if no exact vendor match)
        # -------------------------------------------------------------------
        if matched_category is None:
            for kw_rule in KEYWORD_HEURISTICS:
                if kw_rule.pattern.search(combined_text):
                    matched_category = kw_rule.category
                    confidence = kw_rule.base_confidence
                    explanation = kw_rule.explanation
                    matched_rule_id = kw_rule.rule_id
                    tax_flag = kw_rule.tax_flag
                    signals.append(
                        DecisionSignal(
                            layer="Stage 5: Keyword Heuristic",
                            rule_id=kw_rule.rule_id,
                            detail=kw_rule.explanation,
                            weight=kw_rule.base_confidence,
                        )
                    )
                    break

        return self._finalize_categorization(
            tx=tx,
            norm_merchant=norm_merchant,
            combined_text=combined_text,
            category=matched_category,
            confidence=confidence,
            explanation=explanation,
            matched_rule=matched_rule_id,
            signals=signals,
            tax_flag=tax_flag,
            bypass_traps=False,
        )

    def _finalize_categorization(
        self,
        tx: RawTransaction,
        norm_merchant: str,
        combined_text: str,
        category: Optional[TaxCategory],
        confidence: float,
        explanation: str,
        matched_rule: str,
        signals: List[DecisionSignal],
        tax_flag: TaxFlag,
        bypass_traps: bool = False,
    ) -> CategorizedTransaction:
        abs_amt = round(abs(tx.amount), 2)
        suggested: List[TaxCategory] = []
        review_reason: Optional[str] = None

        # -------------------------------------------------------------------
        # Stage 6: Ambiguity Traps (Opaque Retailers, Local Cafes, P2P, ATM)
        # -------------------------------------------------------------------
        if not bypass_traps:
            for trap in AMBIGUITY_TRAPS:
                if trap.pattern.search(combined_text):
                    # Allow explicit shoot catering to bypass the generic cafe trap
                    if trap.trap_id == "TRAP_LOCAL_CAFE_DINING" and matched_rule == "MEALS_SHOOT_CATERING":
                        continue
                    confidence = min(confidence if confidence > 0 else trap.max_confidence, trap.max_confidence)
                    review_reason = trap.reason
                    explanation = trap.reason
                    matched_rule = trap.trap_id
                    tax_flag = trap.tax_flag
                    suggested = list(trap.suggested_categories)
                    signals.append(
                        DecisionSignal(
                            layer="Stage 6: Ambiguity Trap",
                            rule_id=trap.trap_id,
                            detail=trap.reason,
                            weight=-0.50,
                        )
                    )
                    break

        # -------------------------------------------------------------------
        # Stage 7: Refund vs. Income Reconciliation (Contra-Expense Logic)
        # -------------------------------------------------------------------
        # Match refund keywords against description ONLY; memo adds weak signal but
        # must never change transaction type on its own.
        has_refund_keyword_desc = bool(REFUND_INDICATOR_RE.search(tx.raw_description))
        has_refund_keyword_memo = bool(
            tx.memo and REFUND_INDICATOR_RE.search(tx.memo)
        )
        is_inflow = tx.amount > 0

        # Detect "REFUND TO CLIENT" outflow — contra-income, Needs Review
        is_refund_to_client = bool(
            not is_inflow
            and re.search(r"\bREFUND\s+TO\s+CLIENT\b", tx.raw_description, re.I)
        )

        if category == TaxCategory.NON_DEDUCTIBLE_TRANSFER:
            tx_type = TransactionType.TRANSFER
        elif is_refund_to_client:
            # Outflow refund to client — contra-income, must be reviewed
            tx_type = TransactionType.EXPENSE
            confidence = min(confidence if confidence > 0 else 0.30, 0.30)
            review_reason = (
                f"Outflow refund to client (−${abs_amt:,.2f}): this appears to be a contra-income "
                "refund (money returned to a client). Verify and assign the correct treatment."
            )
            explanation = review_reason
            suggested = [
                TaxCategory.CLIENT_BOOK_INCOME,
                TaxCategory.NON_DEDUCTIBLE_TRANSFER,
                TaxCategory.PERSONAL_NON_DEDUCTIBLE,
            ]
            signals.append(
                DecisionSignal(
                    layer="Stage 7: Refund Reconciler",
                    rule_id="REFUND_TO_CLIENT",
                    detail=review_reason,
                    weight=-0.50,
                )
            )
        elif category == TaxCategory.CLIENT_BOOK_INCOME and not has_refund_keyword_desc:
            tx_type = TransactionType.INCOME
        elif is_inflow:
            # Positive money coming back — only inflows can be refunds
            if category in EXPENSE_ONLY_CATEGORIES or has_refund_keyword_desc:
                tx_type = TransactionType.REFUND
                tax_flag = TaxFlag.CONTRA_EXPENSE_REFUND
                signals.append(
                    DecisionSignal(
                        layer="Stage 7: Refund Reconciler",
                        rule_id="CONTRA_EXPENSE_REFUND",
                        detail="Inflow from expense vendor or explicit refund keyword — treated as a contra-expense (reduces category spend) rather than taxable income.",
                        weight=0.05,
                    )
                )
                if category is None:
                    # Unknown vendor refund -> Needs Review so user picks which expense bucket to offset
                    confidence = min(confidence, 0.50)
                    review_reason = (
                        "Vendor refund/credit detected, but the original expense category is unclear. "
                        "Assign this to the matching expense category so it offsets your spend rather than counting as taxable income."
                    )
                    explanation = review_reason
                    suggested = [
                        TaxCategory.GEAR_RENTALS,
                        TaxCategory.CAMERA_EQUIPMENT,
                        TaxCategory.PHOTOBOOK_PRINTING,
                    ]
                else:
                    explanation = (
                        f"Vendor refund / deposit return for {category.value} (+${abs_amt:,.2f}). "
                        f"Applied as a contra-expense offsetting {category.value} spend — NOT taxable income."
                    )
            else:
                # Unrecognized positive inflow without refund keywords -> could be client check/wire or refund
                tx_type = TransactionType.INCOME
                if category is None:
                    confidence = 0.40
                    review_reason = (
                        f"Unidentified incoming deposit (+${abs_amt:,.2f}): confirm whether this is taxable Client Shoot / Book Income, "
                        "a non-taxable personal transfer, or an expense reimbursement."
                    )
                    explanation = review_reason
                    suggested = [
                        TaxCategory.CLIENT_BOOK_INCOME,
                        TaxCategory.NON_DEDUCTIBLE_TRANSFER,
                        TaxCategory.GEAR_RENTALS,
                    ]
        else:
            # Outflow — always an expense. Refund keywords in outflow description
            # do NOT make it a refund (e.g. "FEDEX RETURN LABEL -25" is shipping expense).
            tx_type = TransactionType.EXPENSE

        # -------------------------------------------------------------------
        # Stage 8: Tax Policy Guardrails (Section 179 Capital Assets & 50% Meals)
        # -------------------------------------------------------------------
        tax_note: Optional[str] = None
        if (
            category == TaxCategory.CAMERA_EQUIPMENT
            and tx_type == TransactionType.EXPENSE
            and abs_amt >= SECTION_179_THRESHOLD
        ):
            tax_flag = TaxFlag.SECTION_179_CANDIDATE
            tax_note = (
                f"High-value hardware purchase (${abs_amt:,.2f} >= $2,500 IRS De Minimis Safe Harbor limit). "
                "Eligible for Section 179 expensing or MACRS bonus depreciation."
            )
            signals.append(
                DecisionSignal(
                    layer="Stage 8: IRS Policy Check",
                    rule_id="SECTION_179_THRESHOLD",
                    detail=tax_note,
                    weight=0.0,
                )
            )

        if category == TaxCategory.CLIENT_CREW_MEALS:
            tax_flag = TaxFlag.MEALS_50_PERCENT
            tax_note = "IRS Schedule C Line 24b limits business & shoot crew meal deductions to 50% of net spend."

        if tx_type == TransactionType.REFUND and not tax_note:
            tax_note = "Contra-expense credit: subtracts from category spend instead of inflating gross income."

        # -------------------------------------------------------------------
        # Stage 9: Unknown Vendor / Low-Confidence Gate (< 0.70 -> Needs Review)
        # -------------------------------------------------------------------
        if category is None or confidence < CONFIDENCE_THRESHOLD:
            needs_review = True
            final_category = TaxCategory.NEEDS_REVIEW
            if not review_reason:
                review_reason = (
                    f"Unrecognized merchant '{norm_merchant}' (${abs_amt:,.2f}). "
                    "The brain does not guess when confidence is below 70% — please assign the correct tax category."
                )
            if not explanation:
                explanation = review_reason
            if not suggested:
                suggested = [
                    TaxCategory.PROPS_REFERENCE_BOOKS,
                    TaxCategory.STUDIO_LOCATIONS,
                    TaxCategory.CLIENT_CREW_MEALS,
                    TaxCategory.PERSONAL_NON_DEDUCTIBLE,
                ]
            deductible_rate = 0.0
            deductible_impact = 0.0
        else:
            needs_review = False
            final_category = category
            _, deductible_rate = SCHEDULE_C_MAPPING.get(final_category, ("Schedule C", 1.0))
            if tx_type == TransactionType.EXPENSE:
                deductible_impact = round(abs_amt * deductible_rate, 2)
            elif tx_type == TransactionType.REFUND:
                deductible_impact = round(-abs_amt * deductible_rate, 2)
            else:
                deductible_impact = 0.0

        return CategorizedTransaction(
            id=f"tx-{tx.row_index}",
            row_index=tx.row_index,
            date=tx.date,
            raw_description=tx.raw_description,
            normalized_merchant=norm_merchant,
            amount=tx.amount,
            abs_amount=abs_amt,
            category=final_category,
            suggested_categories=suggested,
            transaction_type=tx_type,
            confidence=round(confidence, 2),
            needs_review=needs_review,
            review_reason=review_reason,
            explanation=explanation,
            matched_rule=matched_rule,
            signals=signals,
            tax_flag=tax_flag,
            tax_note=tax_note,
            deductible_rate=deductible_rate,
            deductible_impact=deductible_impact,
            user_overridden=bypass_traps,
        )

    def analyze_statement(
        self,
        csv_content: str,
        statement_name: str = "uploaded_statement.csv",
    ) -> StatementAnalysisResponse:
        raw_txs, detected_format, warnings = parse_statement_csv(csv_content)
        seen_signatures: Dict[Tuple[str, str, float], int] = {}
        categorized: List[CategorizedTransaction] = [
            self.categorize_row(tx, seen_signatures) for tx in raw_txs
        ]
        return self.build_summary_response(
            statement_name=statement_name,
            detected_format=detected_format,
            transactions=categorized,
            warnings=warnings,
        )

    @staticmethod
    def build_summary_response(
        statement_name: str,
        detected_format: str,
        transactions: List[CategorizedTransaction],
        warnings: Optional[List[str]] = None,
    ) -> StatementAnalysisResponse:
        buckets: Dict[TaxCategory, Dict[str, float]] = defaultdict(
            lambda: {"count": 0, "gross": 0.0, "refunds": 0.0}
        )

        gross_income = 0.0
        gross_expenses = 0.0
        total_refund_offsets = 0.0
        estimated_deductible = 0.0

        needs_review_count = 0
        duplicate_count = 0
        transfer_count = 0
        refund_count = 0

        for tx in transactions:
            if tx.transaction_type == TransactionType.DUPLICATE:
                duplicate_count += 1
            if tx.transaction_type == TransactionType.TRANSFER:
                transfer_count += 1
            if tx.transaction_type == TransactionType.REFUND:
                refund_count += 1

            if tx.needs_review or tx.category == TaxCategory.NEEDS_REVIEW:
                needs_review_count += 1
                buckets[TaxCategory.NEEDS_REVIEW]["count"] += 1
                if tx.amount < 0:
                    buckets[TaxCategory.NEEDS_REVIEW]["gross"] += tx.abs_amount
                else:
                    buckets[TaxCategory.NEEDS_REVIEW]["refunds"] += tx.abs_amount
                continue

            b = buckets[tx.category]
            b["count"] += 1

            if tx.transaction_type == TransactionType.INCOME:
                gross_income += tx.abs_amount
                b["gross"] += tx.abs_amount
            elif tx.transaction_type == TransactionType.EXPENSE:
                if tx.category not in (
                    TaxCategory.NON_DEDUCTIBLE_TRANSFER,
                    TaxCategory.PERSONAL_NON_DEDUCTIBLE,
                ):
                    gross_expenses += tx.abs_amount
                b["gross"] += tx.abs_amount
                estimated_deductible += tx.deductible_impact
            elif tx.transaction_type == TransactionType.REFUND:
                total_refund_offsets += tx.abs_amount
                b["refunds"] += tx.abs_amount
                estimated_deductible += tx.deductible_impact  # negative offset
            elif tx.transaction_type == TransactionType.TRANSFER:
                b["gross"] += tx.abs_amount

        category_summaries: List[CategorySummary] = []
        for cat, stats in buckets.items():
            line_desc, rate = SCHEDULE_C_MAPPING.get(cat, ("Schedule C", 1.0))
            gross = round(stats["gross"], 2)
            refunds = round(stats["refunds"], 2)
            if cat in (
                TaxCategory.CLIENT_BOOK_INCOME,
                TaxCategory.NON_DEDUCTIBLE_TRANSFER,
                TaxCategory.PERSONAL_NON_DEDUCTIBLE,
                TaxCategory.NEEDS_REVIEW,
            ):
                net = round(gross - refunds, 2) if cat != TaxCategory.CLIENT_BOOK_INCOME else gross
                deductible = 0.0
            else:
                net = round(max(0.0, gross - refunds), 2)
                deductible = round(net * rate, 2)

            category_summaries.append(
                CategorySummary(
                    category=cat,
                    schedule_c_line=line_desc,
                    transaction_count=int(stats["count"]),
                    gross_spend=gross,
                    refunds_and_credits=refunds,
                    net_spend=net,
                    deductible_rate=rate,
                    deductible_amount=deductible,
                )
            )

        # Sort expense categories by net_spend descending, keeping Needs Review at top if present
        category_summaries.sort(
            key=lambda s: (
                0 if s.category == TaxCategory.NEEDS_REVIEW else 1,
                -s.net_spend,
            )
        )

        auto_categorized = len(transactions) - needs_review_count
        net_expenses = round(max(0.0, gross_expenses - total_refund_offsets), 2)

        return StatementAnalysisResponse(
            statement_name=statement_name,
            detected_bank_format=detected_format,
            total_rows=len(transactions),
            auto_categorized_count=auto_categorized,
            needs_review_count=needs_review_count,
            duplicate_or_pending_count=duplicate_count,
            transfer_count=transfer_count,
            refund_count=refund_count,
            gross_income=round(gross_income, 2),
            gross_expenses=round(gross_expenses, 2),
            total_refund_offsets=round(total_refund_offsets, 2),
            net_expenses=net_expenses,
            estimated_deductible_total=round(max(0.0, estimated_deductible), 2),
            category_summaries=category_summaries,
            transactions=transactions,
            parse_warnings=warnings or [],
        )
