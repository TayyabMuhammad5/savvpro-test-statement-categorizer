from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
import re
from typing import Any, Dict, List, Optional, Tuple
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

ONLINE_TRANSFER_RE = re.compile(r"\bONLINE TRANSFER (?:FROM|TO)\s+(.+)$", re.I)
REFUND_TO_CLIENT_RE = re.compile(r"\bREFUND\s+TO\s+CLIENT\b", re.I)
GAS_STATION_RE = re.compile(
    r"\b(CHEVRON|SHELL\s*OIL|EXXON|BP\s*CONNECT|MOBIL|SPEEDWAY|7-ELEVEN|SUNOCO|CIRCLE\s*K|VALERO|TEXACO|WAWA)\b",
    re.I,
)
PERMIT_RE = re.compile(r"\b(PERMIT|PARKS\s*FILMING|MOME|FILMLA)\b", re.I)

DUPLICATE_SUGGESTED = [
    TaxCategory.NON_DEDUCTIBLE_TRANSFER,
    TaxCategory.GEAR_RENTALS,
    TaxCategory.CAMERA_EQUIPMENT,
]


def levenshtein_distance(s1: str, s2: str) -> int:
    """Pure-Python deterministic Levenshtein edit distance."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def string_similarity(s1: str, s2: str) -> float:
    """Computes normalized string similarity ratio between 0.0 and 1.0."""
    s1, s2 = s1.upper().strip(), s2.upper().strip()
    if s1 == s2:
        return 1.0
    dist = levenshtein_distance(s1, s2)
    max_len = max(len(s1), len(s2))
    return 1.0 - (dist / max_len) if max_len > 0 else 1.0


FUZZY_TARGETS: List[Tuple[str, TaxCategory]] = [
    ("LENSRENTALS", TaxCategory.GEAR_RENTALS),
    ("BORROWLENSES", TaxCategory.GEAR_RENTALS),
    ("SHAREGRID", TaxCategory.GEAR_RENTALS),
    ("BH PHOTO", TaxCategory.CAMERA_EQUIPMENT),
    ("ADORAMA", TaxCategory.CAMERA_EQUIPMENT),
    ("SAMYS CAMERA", TaxCategory.CAMERA_EQUIPMENT),
    ("KEH CAMERA", TaxCategory.CAMERA_EQUIPMENT),
    ("BLURB", TaxCategory.PHOTOBOOK_PRINTING),
    ("ARTIFACT UPRISING", TaxCategory.PHOTOBOOK_PRINTING),
    ("PRINTIQUE", TaxCategory.PHOTOBOOK_PRINTING),
    ("INDIE FILM LAB", TaxCategory.PHOTOBOOK_PRINTING),
    ("THE DARKROOM", TaxCategory.PHOTOBOOK_PRINTING),
    ("RICHARD PHOTO LAB", TaxCategory.PHOTOBOOK_PRINTING),
    ("BAY PHOTO", TaxCategory.PHOTOBOOK_PRINTING),
    ("WHITEWALL", TaxCategory.PHOTOBOOK_PRINTING),
    ("ADOBE", TaxCategory.SOFTWARE_WORKFLOW),
    ("CAPTURE ONE", TaxCategory.SOFTWARE_WORKFLOW),
    ("PHOTO MECHANIC", TaxCategory.SOFTWARE_WORKFLOW),
    ("DROPBOX", TaxCategory.SOFTWARE_WORKFLOW),
    ("GOOGLE WORKSPACE", TaxCategory.SOFTWARE_WORKFLOW),
    ("NOTION", TaxCategory.SOFTWARE_WORKFLOW),
    ("PEERSPACE", TaxCategory.STUDIO_LOCATIONS),
    ("SPLACER", TaxCategory.STUDIO_LOCATIONS),
    ("SWEETGREEN", TaxCategory.CLIENT_CREW_MEALS),
    ("EZCATER", TaxCategory.CLIENT_CREW_MEALS),
    ("STRAND BOOK STORE", TaxCategory.PROPS_REFERENCE_BOOKS),
    ("PRINTED MATTER", TaxCategory.PROPS_REFERENCE_BOOKS),
    ("DASHWOOD BOOKS", TaxCategory.PROPS_REFERENCE_BOOKS),
    ("USPS", TaxCategory.SHIPPING_PACKAGING),
    ("PIRATE SHIP", TaxCategory.SHIPPING_PACKAGING),
    ("FEDEX", TaxCategory.SHIPPING_PACKAGING),
    ("UPS STORE", TaxCategory.SHIPPING_PACKAGING),
    ("DELTA AIRLINES", TaxCategory.TRAVEL_TRANSPORT),
    ("UNITED AIRLINES", TaxCategory.TRAVEL_TRANSPORT),
    ("AMERICAN AIRLINES", TaxCategory.TRAVEL_TRANSPORT),
    ("SOUTHWEST AIRLINES", TaxCategory.TRAVEL_TRANSPORT),
    ("UBER", TaxCategory.TRAVEL_TRANSPORT),
    ("LYFT", TaxCategory.TRAVEL_TRANSPORT),
    ("HISCOX", TaxCategory.INSURANCE_LEGAL),
    ("HONEYBOOK", TaxCategory.CLIENT_BOOK_INCOME),
    ("PHOTO ASSISTANT", TaxCategory.CONTRACT_LABOR),
    ("SECOND SHOOTER", TaxCategory.CONTRACT_LABOR),
    ("DIGITAL TECH", TaxCategory.CONTRACT_LABOR),
]


CATEGORY_ALTERNATIVES: Dict[TaxCategory, List[Tuple[TaxCategory, str]]] = {
    TaxCategory.CAMERA_EQUIPMENT: [
        (TaxCategory.GEAR_RENTALS, "Could be a temporary short-term shoot rental rather than a purchased capital asset."),
        (TaxCategory.PROPS_REFERENCE_BOOKS, "Could be studio props, styling materials, or backgrounds purchased at a photo retailer."),
    ],
    TaxCategory.GEAR_RENTALS: [
        (TaxCategory.CAMERA_EQUIPMENT, "Could be a rental buyout or permanent hardware purchase rather than a short-term rental."),
        (TaxCategory.STUDIO_LOCATIONS, "Could be rented studio stage or location grip package rather than camera bodies/lenses."),
    ],
    TaxCategory.PHOTOBOOK_PRINTING: [
        (TaxCategory.SHIPPING_PACKAGING, "Could be shipping, packaging mailers, or pallet freight separated from print production."),
        (TaxCategory.PROPS_REFERENCE_BOOKS, "Could be sample monograph retained for studio reference/portfolio rather than lab COGS."),
    ],
    TaxCategory.SOFTWARE_WORKFLOW: [
        (TaxCategory.MARKETING_BOOK_FAIRS, "Could be website portfolio hosting or marketing funnel software rather than operational workflow."),
        (TaxCategory.PHOTOBOOK_PRINTING, "Could be digital proofing service directly tied to a specific book print run."),
    ],
    TaxCategory.STUDIO_LOCATIONS: [
        (TaxCategory.TRAVEL_TRANSPORT, "Could be lodging or transport associated with a shoot location rather than venue space rental."),
        (TaxCategory.CONTRACT_LABOR, "Could be studio assistant or stage manager fees billed alongside space hire."),
    ],
    TaxCategory.TRAVEL_TRANSPORT: [
        (TaxCategory.CLIENT_CREW_MEALS, "Could be transit meals or incidentals that are subject to the 50% meals limitation."),
        (TaxCategory.PERSONAL_NON_DEDUCTIBLE, "Could be personal commuting or non-business transit segment."),
    ],
    TaxCategory.SHIPPING_PACKAGING: [
        (TaxCategory.PHOTOBOOK_PRINTING, "Could be print lab production fees bundled with packaging."),
        (TaxCategory.CAMERA_EQUIPMENT, "Could be protective hard cases or gear transport equipment rather than postal mailers."),
    ],
    TaxCategory.PROPS_REFERENCE_BOOKS: [
        (TaxCategory.CAMERA_EQUIPMENT, "Could be technical hardware or accessories purchased for studio shoots."),
        (TaxCategory.PERSONAL_NON_DEDUCTIBLE, "Could be personal reading materials or home decor rather than client set props."),
    ],
    TaxCategory.CLIENT_CREW_MEALS: [
        (TaxCategory.PERSONAL_NON_DEDUCTIBLE, "Solo meals without business clients or shoot crew present are 0% deductible personal dining."),
        (TaxCategory.TRAVEL_TRANSPORT, "Could be travel per diem or transit meal during out-of-town shoot."),
    ],
    TaxCategory.MARKETING_BOOK_FAIRS: [
        (TaxCategory.SOFTWARE_WORKFLOW, "Could be general portfolio website subscription rather than advertising/fair campaign."),
        (TaxCategory.TRAVEL_TRANSPORT, "Could be travel/transit to a book fair rather than the exhibitor booth fee."),
    ],
    TaxCategory.INSURANCE_LEGAL: [
        (TaxCategory.BANK_MERCHANT_FEES, "Could be bank administrative or wire fees rather than insurance/copyright."),
        (TaxCategory.SOFTWARE_WORKFLOW, "Could be digital membership portal subscription rather than professional guild dues."),
    ],
    TaxCategory.BANK_MERCHANT_FEES: [
        (TaxCategory.NON_DEDUCTIBLE_TRANSFER, "Could be internal account transfer or settlement rather than a deductible processing fee."),
        (TaxCategory.SOFTWARE_WORKFLOW, "Could be banking or financial SaaS software platform subscription."),
    ],
    TaxCategory.CONTRACT_LABOR: [
        (TaxCategory.STUDIO_LOCATIONS, "Could be studio booking or location coordinator rather than independent assistant contractor."),
        (TaxCategory.PERSONAL_NON_DEDUCTIBLE, "Could be personal payment to an individual lacking a business invoice or W-9."),
    ],
    TaxCategory.CLIENT_BOOK_INCOME: [
        (TaxCategory.NON_DEDUCTIBLE_TRANSFER, "Could be personal transfer between own accounts rather than taxable client revenue."),
        (TaxCategory.GEAR_RENTALS, "Could be vendor security deposit refund rather than client project retainer."),
    ],
    TaxCategory.NON_DEDUCTIBLE_TRANSFER: [
        (TaxCategory.CLIENT_BOOK_INCOME, "Could be client invoice payment or direct deposit rather than an internal transfer."),
        (TaxCategory.PERSONAL_NON_DEDUCTIBLE, "Could be owner personal draw rather than operational balance settlement."),
    ],
    TaxCategory.PERSONAL_NON_DEDUCTIBLE: [
        (TaxCategory.CLIENT_CREW_MEALS, "Could be on-set crew lunch if business purpose and receipt are substantiated."),
        (TaxCategory.PROPS_REFERENCE_BOOKS, "Could be photo shoot styling items or props if used exclusively for commercial sets."),
    ],
    TaxCategory.NEEDS_REVIEW: [
        (TaxCategory.CAMERA_EQUIPMENT, "Merchant or amount may correspond to camera hardware, lighting, or photo supplies."),
        (TaxCategory.PROPS_REFERENCE_BOOKS, "Could be reference photobooks, set props, or background styling materials."),
        (TaxCategory.PERSONAL_NON_DEDUCTIBLE, "May represent non-deductible personal spending if not substantiated by business receipt."),
    ],
}


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

    def __init__(
        self,
        custom_rules: Optional[Dict[str, TaxCategory]] = None,
        row_decisions: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.custom_rules: Dict[str, TaxCategory] = {}
        if custom_rules:
            for k, v in custom_rules.items():
                self.learn_merchant_rule(k, v)

        self.row_decisions: Dict[str, Dict[str, Any]] = {}
        if row_decisions:
            for k, v in row_decisions.items():
                self._normalize_and_set_row_decision(k, v)

        self._match_cache: Dict[str, Tuple[Optional[TaxCategory], float, str, str, TaxFlag, str, str, str, float]] = {}
        self._template_cache: Dict[Tuple, CategorizedTransaction] = {}

    def _normalize_and_set_row_decision(self, key: str, val: Any) -> None:
        if isinstance(val, str):
            if val.lower() in ("keep", "exclude"):
                self.set_row_decision(key, action=val.lower())
            else:
                self.set_row_decision(key, action="categorize", category=val)
        elif isinstance(val, dict):
            self.set_row_decision(
                key,
                action=val.get("action", "categorize"),
                category=val.get("category"),
                transaction_type=val.get("transaction_type"),
                confirm_income_on_outflow=val.get("confirm_income_on_outflow", False),
            )

    def set_row_decision(
        self,
        row_id_or_index: str,
        action: str = "categorize",
        category: Optional[TaxCategory | str] = None,
        transaction_type: Optional[TransactionType | str] = None,
        amount: Optional[float] = None,
        confirm_income_on_outflow: bool = False,
    ) -> None:
        cat_enum: Optional[TaxCategory] = None
        if category is not None:
            cat_enum = category if isinstance(category, TaxCategory) else TaxCategory(category)
            if cat_enum == TaxCategory.NEEDS_REVIEW:
                raise ValueError("Cannot assign 'Needs Review' as a user decision.")
            if (
                cat_enum == TaxCategory.CLIENT_BOOK_INCOME
                and amount is not None
                and amount < 0
                and not confirm_income_on_outflow
            ):
                raise ValueError(
                    "Assigning income category to an outflow requires confirm_income_on_outflow=True confirmation flag."
                )

        tt_enum: Optional[TransactionType] = None
        if transaction_type is not None:
            tt_enum = (
                transaction_type
                if isinstance(transaction_type, TransactionType)
                else TransactionType(transaction_type)
            )

        key = str(row_id_or_index).strip()
        self.row_decisions[key] = {
            "action": action.lower(),
            "category": cat_enum,
            "transaction_type": tt_enum,
            "confirm_income_on_outflow": confirm_income_on_outflow,
        }

    def learn_merchant_rule(self, raw_or_normalized_merchant: str, category: TaxCategory | str) -> str:
        cat_enum = category if isinstance(category, TaxCategory) else TaxCategory(category)
        if cat_enum == TaxCategory.NEEDS_REVIEW:
            raise ValueError("Cannot assign 'Needs Review' as a merchant rule decision.")
        norm = normalize_merchant_name(raw_or_normalized_merchant)
        self.custom_rules[norm] = cat_enum
        return norm

    def categorize_row(
        self,
        tx: RawTransaction,
        seen_signatures: Dict[Tuple[str, str, float], int],
        transfer_pairs: Optional[Dict[int, int]] = None,
        posted_signatures: Optional[set] = None,
        recurring_rows: Optional[set[int]] = None,
    ) -> CategorizedTransaction:
        norm_merchant = normalize_merchant_name(tx.raw_description)
        combined_text = f"{tx.raw_description} {tx.memo or ''}".strip()
        abs_amt = round(abs(tx.amount), 2)
        signals: List[DecisionSignal] = []

        if tx.bank_category:
            signals.append(
                DecisionSignal(
                    layer="Stage 4b: Bank Category Signal",
                    rule_id="BANK_CATEGORY_DATA",
                    detail=f"Bank-provided category '{tx.bank_category}' recorded as corroborating signal.",
                    weight=0.03,
                )
            )

        if recurring_rows and tx.row_index in recurring_rows:
            signals.append(
                DecisionSignal(
                    layer="Stage 4c: Recurrence Signal",
                    rule_id="RECURRING_CADENCE",
                    detail=f"Detected recurring subscription/retainer cadence (${abs_amt:,.2f}) across statement periods.",
                    weight=0.04,
                )
            )

        row_key = f"tx-{tx.row_index}"
        row_decision = self.row_decisions.get(row_key) or self.row_decisions.get(str(tx.row_index))
        bypass_duplicate = False

        # -------------------------------------------------------------------
        # Precedence 1: Row-Level User Decision
        # -------------------------------------------------------------------
        if row_decision:
            action = row_decision.get("action", "categorize")
            dec_cat = row_decision.get("category")
            confirm_outflow = row_decision.get("confirm_income_on_outflow", False)

            if action == "exclude":
                signals.append(
                    DecisionSignal(
                        layer="Stage 0: User Decision",
                        rule_id="USER_ROW_EXCLUDE",
                        detail="Excluded as duplicate or non-business by user decision.",
                        weight=1.0,
                    )
                )
                return CategorizedTransaction(
                    id=row_key,
                    row_index=tx.row_index,
                    date=tx.date,
                    raw_description=tx.raw_description,
                    normalized_merchant=norm_merchant,
                    amount=tx.amount,
                    abs_amount=abs_amt,
                    category=TaxCategory.NON_DEDUCTIBLE_TRANSFER,
                    suggested_categories=[TaxCategory.NON_DEDUCTIBLE_TRANSFER],
                    transaction_type=TransactionType.EXCLUDED,
                    confidence=1.0,
                    needs_review=False,
                    explanation="Excluded as duplicate or non-business by row-level user decision.",
                    matched_rule="USER_ROW_EXCLUDE",
                    signals=signals,
                    tax_flag=TaxFlag.INTERNAL_TRANSFER,
                    tax_note="Excluded from Schedule C by user decision.",
                    deductible_rate=0.0,
                    deductible_impact=0.0,
                    user_overridden=True,
                )

            if action == "keep":
                bypass_duplicate = True

            if dec_cat:
                if dec_cat == TaxCategory.CLIENT_BOOK_INCOME and tx.amount < 0 and not confirm_outflow:
                    raise ValueError(
                        "Assigning income category to an outflow requires confirm_income_on_outflow=True confirmation flag."
                    )
                signals.append(
                    DecisionSignal(
                        layer="Stage 0: User Decision",
                        rule_id="USER_ROW_DECISION",
                        detail=f"Categorized as '{dec_cat.value}' by row-level user decision.",
                        weight=1.0,
                    )
                )
                return self._finalize_categorization(
                    tx=tx,
                    norm_merchant=norm_merchant,
                    combined_text=combined_text,
                    category=dec_cat,
                    confidence=1.0,
                    explanation=f"Categorized via user row decision for '{row_key}'.",
                    matched_rule="USER_ROW_DECISION",
                    signals=signals,
                    tax_flag=TaxFlag.NONE,
                    bypass_traps=True,
                )

        # -------------------------------------------------------------------
        # Precedence 2: Merchant-Level User Rules
        # -------------------------------------------------------------------
        if norm_merchant in self.custom_rules:
            learned_cat = self.custom_rules[norm_merchant]
            signals.append(
                DecisionSignal(
                    layer="Stage 1: User Learned Rule",
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
        # Precedence 3: Integrity Guards — Pending Holds & Exact Duplicates
        # -------------------------------------------------------------------
        is_pending = bool(
            (tx.raw_status and PENDING_INDICATOR_RE.search(tx.raw_status))
            or PENDING_INDICATOR_RE.search(tx.raw_description)
        )
        sig = (tx.date, norm_merchant, tx.amount)
        prior_row = seen_signatures.get(sig)
        if not is_pending:
            seen_signatures[sig] = tx.row_index

        if is_pending:
            is_reconciled = posted_signatures is not None and (norm_merchant, abs_amt) in posted_signatures
            note = (
                "Excluded: pending authorization hold (reconciled with posted transaction)."
                if is_reconciled
                else "Excluded: pending authorization hold."
            )
            signals.append(
                DecisionSignal(
                    layer="Stage 2: Integrity Guard",
                    rule_id="PENDING_HOLD",
                    detail=note,
                    weight=0.99,
                )
            )
            return CategorizedTransaction(
                id=row_key,
                row_index=tx.row_index,
                date=tx.date,
                raw_description=tx.raw_description,
                normalized_merchant=norm_merchant,
                amount=tx.amount,
                abs_amount=abs_amt,
                category=TaxCategory.NON_DEDUCTIBLE_TRANSFER,
                suggested_categories=DUPLICATE_SUGGESTED,
                transaction_type=TransactionType.EXCLUDED,
                confidence=0.99,
                needs_review=False,
                explanation=note,
                matched_rule="PENDING_HOLD",
                signals=signals,
                tax_flag=TaxFlag.PENDING_OR_DUPLICATE,
                tax_note=note,
                deductible_rate=0.0,
                deductible_impact=0.0,
            )

        if not bypass_duplicate and prior_row is not None:
            reason_msg = (
                f"Potential duplicate of Row #{prior_row} (identical date, merchant '{norm_merchant}', and amount ${abs_amt:,.2f}). Suggestion: Keep or Exclude."
            )
            signals.append(
                DecisionSignal(
                    layer="Stage 2: Integrity Guard",
                    rule_id="DUPLICATE_ROW",
                    detail=reason_msg,
                    weight=0.30,
                )
            )
            return CategorizedTransaction(
                id=row_key,
                row_index=tx.row_index,
                date=tx.date,
                raw_description=tx.raw_description,
                normalized_merchant=norm_merchant,
                amount=tx.amount,
                abs_amount=abs_amt,
                category=TaxCategory.NEEDS_REVIEW,
                suggested_categories=DUPLICATE_SUGGESTED,
                transaction_type=TransactionType.DUPLICATE,
                confidence=0.30,
                needs_review=True,
                review_reason=reason_msg,
                explanation=reason_msg,
                matched_rule="DUPLICATE_ROW",
                signals=signals,
                tax_flag=TaxFlag.PENDING_OR_DUPLICATE,
                tax_note="Flagged as potential duplicate row for user review.",
                deductible_rate=0.0,
                deductible_impact=0.0,
            )

        # -------------------------------------------------------------------
        # Stage 2: Internal Transfers, Credit Card Autopay & Tax Payments
        # -------------------------------------------------------------------
        # 2a. Cross-row transfer pairing (same amount, opposite sign, <= 3 days)
        if transfer_pairs and tx.row_index in transfer_pairs:
            partner_idx = transfer_pairs[tx.row_index]
            signals.append(
                DecisionSignal(
                    layer="Stage 2: Transfer Pairing",
                    rule_id="XFER_CROSS_ROW_PAIR",
                    detail=f"Cross-row transfer pairing: matched row {partner_idx} with opposite amount (${abs_amt:.2f}) within 3 days.",
                    weight=0.99,
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
                confidence=0.99,
                needs_review=False,
                explanation=f"Cross-row transfer pairing: matched row {partner_idx} with opposite amount (${abs_amt:.2f}) within 3 days.",
                matched_rule="XFER_CROSS_ROW_PAIR",
                signals=signals,
                tax_flag=TaxFlag.INTERNAL_TRANSFER,
                tax_note="Excluded from Schedule C income and expenses (paired cross-row transfer).",
                deductible_rate=0.0,
                deductible_impact=0.0,
            )

        # 2b. Check for peer-to-peer / third-party online transfers that require review
        online_transfer_match = ONLINE_TRANSFER_RE.search(tx.raw_description)
        if online_transfer_match:
            party_text = online_transfer_match.group(0).upper()
            if not any(k in party_text for k in ("SAVINGS", "CHECKING", "OWN ACCOUNT", "SELF")):
                signals.append(
                    DecisionSignal(
                        layer="Stage 2: Transfer Review",
                        rule_id="P2P_ONLINE_TRANSFER",
                        detail="Online transfer with external party. Requires review to determine if client income, transfer, or personal.",
                        weight=0.50,
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
                        TaxCategory.CLIENT_BOOK_INCOME if tx.amount > 0 else TaxCategory.NON_DEDUCTIBLE_TRANSFER,
                        TaxCategory.NON_DEDUCTIBLE_TRANSFER,
                        TaxCategory.PERSONAL_NON_DEDUCTIBLE,
                    ],
                    transaction_type=TransactionType.INCOME if tx.amount > 0 else TransactionType.EXPENSE,
                    confidence=0.50,
                    needs_review=True,
                    review_reason="Online transfer involving third party: verify whether this is client income, internal transfer, or personal.",
                    explanation="Online transfer involving third party: verify whether this is client income, internal transfer, or personal.",
                    matched_rule="P2P_ONLINE_TRANSFER",
                    signals=signals,
                    tax_flag=TaxFlag.OPAQUE_MERCHANT,
                    deductible_rate=0.0,
                    deductible_impact=0.0,
                )

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


        # Check row template cache for repeating identical transactions
        is_rec = bool(recurring_rows and tx.row_index in recurring_rows)
        tpl_key = (norm_merchant, combined_text, tx.amount, tx.bank_category, is_rec)
        if tpl_key in self._template_cache:
            t = self._template_cache[tpl_key]
            return CategorizedTransaction(
                id=row_key,
                row_index=tx.row_index,
                date=tx.date,
                raw_description=tx.raw_description,
                normalized_merchant=norm_merchant,
                amount=tx.amount,
                abs_amount=abs_amt,
                category=t.category,
                suggested_categories=t.suggested_categories,
                alternative_reasons=t.alternative_reasons,
                transaction_type=t.transaction_type,
                confidence=t.confidence,
                needs_review=t.needs_review,
                review_reason=t.review_reason,
                explanation=t.explanation,
                matched_rule=t.matched_rule,
                signals=t.signals,
                tax_flag=t.tax_flag,
                tax_note=t.tax_note,
                deductible_rate=t.deductible_rate,
                deductible_impact=t.deductible_impact,
                user_overridden=t.user_overridden,
            )

        # -------------------------------------------------------------------
        # Stage 4: Curated Photography & Photobook Merchant Rules
        # -------------------------------------------------------------------
        cache_key = f"{norm_merchant}|{combined_text}"
        if cache_key in self._match_cache:
            matched_category, confidence, explanation, matched_rule_id, tax_flag, sig_layer, sig_rule_id, sig_detail, sig_weight = self._match_cache[cache_key]
            if matched_category is not None and sig_layer:
                signals.append(
                    DecisionSignal(
                        layer=sig_layer,
                        rule_id=sig_rule_id,
                        detail=sig_detail,
                        weight=sig_weight,
                    )
                )
        else:
            matched_category = None
            confidence = 0.0
            explanation = ""
            matched_rule_id = "UNMATCHED"
            tax_flag = TaxFlag.NONE
            sig_layer = ""
            sig_rule_id = ""
            sig_detail = ""
            sig_weight = 0.0

            # Pass 1: Vendor identity matching on normalized_merchant
            for rule in MERCHANT_RULES:
                if rule.pattern.search(norm_merchant):
                    matched_category = rule.category
                    confidence = rule.base_confidence
                    explanation = rule.explanation
                    matched_rule_id = rule.rule_id
                    tax_flag = rule.tax_flag
                    sig_layer = "Stage 4: Domain Merchant Rule"
                    sig_rule_id = rule.rule_id
                    sig_detail = rule.explanation
                    sig_weight = rule.base_confidence
                    signals.append(
                        DecisionSignal(
                            layer=sig_layer,
                            rule_id=sig_rule_id,
                            detail=sig_detail,
                            weight=sig_weight,
                        )
                    )
                    break

            # Pass 2: Fallback check on combined text (description + memo) if vendor wasn't matched
            if matched_category is None:
                for rule in MERCHANT_RULES:
                    if rule.pattern.search(combined_text):
                        matched_category = rule.category
                        confidence = rule.base_confidence
                        explanation = rule.explanation
                        matched_rule_id = rule.rule_id
                        tax_flag = rule.tax_flag
                        sig_layer = "Stage 4: Domain Merchant Rule"
                        sig_rule_id = rule.rule_id
                        sig_detail = rule.explanation
                        sig_weight = rule.base_confidence
                        signals.append(
                            DecisionSignal(
                                layer=sig_layer,
                                rule_id=sig_rule_id,
                                detail=sig_detail,
                                weight=sig_weight,
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
                        sig_layer = "Stage 5: Keyword Heuristic"
                        sig_rule_id = kw_rule.rule_id
                        sig_detail = kw_rule.explanation
                        sig_weight = kw_rule.base_confidence
                        signals.append(
                            DecisionSignal(
                                layer=sig_layer,
                                rule_id=sig_rule_id,
                                detail=sig_detail,
                                weight=sig_weight,
                            )
                        )
                        break

            # -------------------------------------------------------------------
            # Stage 5b: Fuzzy Matching via Levenshtein Edit Distance (Confidence <= 0.65 -> Needs Review)
            # -------------------------------------------------------------------
            if matched_category is None:
                clean_norm = re.sub(r"[^A-Z0-9 ]+", " ", norm_merchant.upper()).strip()
                tokens = [t for t in clean_norm.split() if len(t) >= 4]
                best_target: Optional[Tuple[str, TaxCategory, float]] = None

                for target_name, target_cat in FUZZY_TARGETS:
                    sim_full = string_similarity(clean_norm, target_name)
                    if sim_full >= 0.80 and (best_target is None or sim_full > best_target[2]):
                        best_target = (target_name, target_cat, sim_full)

                    for tok in tokens:
                        sim_tok = string_similarity(tok, target_name)
                        if sim_tok >= 0.80 and len(tok) >= 5 and (best_target is None or sim_tok > best_target[2]):
                            best_target = (target_name, target_cat, sim_tok)

                if best_target is not None:
                    target_name, target_cat, best_sim = best_target
                    matched_category = target_cat
                    confidence = 0.62  # strictly <= 0.65 to ensure it routes to Needs Review
                    explanation = f"Fuzzy matched known photography vendor '{target_name}' (similarity {best_sim:.0%}). Needs review for confirmation."
                    matched_rule_id = f"FUZZY_{target_name.replace(' ', '_')}"
                    sig_layer = "Stage 5b: Fuzzy Matching"
                    sig_rule_id = matched_rule_id
                    sig_detail = explanation
                    sig_weight = 0.62
                    signals.append(
                        DecisionSignal(
                            layer=sig_layer,
                            rule_id=sig_rule_id,
                            detail=sig_detail,
                            weight=sig_weight,
                        )
                    )

            self._match_cache[cache_key] = (
                matched_category,
                confidence,
                explanation,
                matched_rule_id,
                tax_flag,
                sig_layer,
                sig_rule_id,
                sig_detail,
                sig_weight,
            )

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
            tpl_key=tpl_key,
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
        tpl_key: Optional[Tuple] = None,
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
                if category:
                    suggested = [category]
                    for alt_cat, _ in CATEGORY_ALTERNATIVES.get(category, []):
                        if alt_cat not in suggested:
                            suggested.append(alt_cat)
                else:
                    suggested = [
                        TaxCategory.PROPS_REFERENCE_BOOKS,
                        TaxCategory.STUDIO_LOCATIONS,
                        TaxCategory.CLIENT_CREW_MEALS,
                        TaxCategory.PERSONAL_NON_DEDUCTIBLE,
                    ]
            elif category and category not in suggested:
                suggested.insert(0, category)
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

        # Check tax notes for permits, contract labor, and mileage
        if not tax_note:
            if matched_rule == "TRAP_GAS_STATIONS" or GAS_STATION_RE.search(combined_text):
                tax_note = "IRS standard mileage rate (67¢/mi for 2024, 70¢/mi for 2025) vs. actual expenses. Cannot claim both."
            elif final_category == TaxCategory.CONTRACT_LABOR or category == TaxCategory.CONTRACT_LABOR:
                tax_note = "IRS Schedule C Line 11 — Contract Labor. Remember to file Form 1099-NEC if contractor is paid >= $600 in the calendar year."
            elif PERMIT_RE.search(combined_text):
                tax_note = "IRS Schedule C Line 23 — Taxes, Licenses & Shoot Location Permits."

        # Generate top alternative categories and explicit why-not reasons
        alternative_reasons: Dict[str, str] = {}
        target_lookup_cat = category or final_category
        if target_lookup_cat and target_lookup_cat != TaxCategory.NEEDS_REVIEW:
            alts = CATEGORY_ALTERNATIVES.get(target_lookup_cat, [])
            for alt_cat, why_not in alts:
                alternative_reasons[alt_cat.value] = why_not

        if not alternative_reasons:
            if suggested:
                for s_cat in suggested[:3]:
                    s_enum = s_cat if isinstance(s_cat, TaxCategory) else TaxCategory(s_cat)
                    alts = CATEGORY_ALTERNATIVES.get(s_enum, [])
                    if alts:
                        alternative_reasons[s_enum.value] = alts[0][1]
                    else:
                        alternative_reasons[s_enum.value] = "Candidate deduction category based on vendor and amount profile."
            else:
                default_alts = CATEGORY_ALTERNATIVES.get(TaxCategory.NEEDS_REVIEW, [])
                for alt_cat, why_not in default_alts:
                    alternative_reasons[alt_cat.value] = why_not

        final_suggested: List[TaxCategory] = []
        if suggested:
            for s in suggested:
                s_enum = s if isinstance(s, TaxCategory) else TaxCategory(s)
                if s_enum not in final_suggested:
                    final_suggested.append(s_enum)
        for k in alternative_reasons.keys():
            try:
                cat_enum = TaxCategory(k)
                if cat_enum not in final_suggested:
                    final_suggested.append(cat_enum)
            except ValueError:
                pass

        res = CategorizedTransaction(
            id=f"tx-{tx.row_index}",
            row_index=tx.row_index,
            date=tx.date,
            raw_description=tx.raw_description,
            normalized_merchant=norm_merchant,
            amount=tx.amount,
            abs_amount=abs_amt,
            category=final_category,
            suggested_categories=final_suggested,
            alternative_reasons=alternative_reasons,
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
        if tpl_key is not None and not bypass_traps:
            self._template_cache[tpl_key] = res
        return res

    @staticmethod
    def _find_transfer_pairs(transactions: List[RawTransaction]) -> Dict[int, int]:
        """Finds cross-row transfer pairs: same amount, opposite sign, <= 3 days."""
        pairs: Dict[int, int] = {}
        used: set[int] = set()

        transfer_keywords = re.compile(
            r"\b(TRANSFER|SAVINGS|CHECKING|XFER|INTERNAL|FUNDS\s*TRANSFER|OWNER\s*DRAW|MEMBER\s*DRAW|AUTOPAY|PAYMENT\s*THANK\s*YOU)\b",
            re.I,
        )

        parsed_dates = {}
        by_abs_amt = defaultdict(list)
        for tx in transactions:
            if tx.amount == 0.0:
                continue
            try:
                parsed_dates[tx.row_index] = date.fromisoformat(tx.date)
            except (ValueError, TypeError):
                parsed_dates[tx.row_index] = None
            abs_a = round(abs(tx.amount), 2)
            by_abs_amt[abs_a].append(tx)

        for abs_a, tx_list in by_abs_amt.items():
            if len(tx_list) < 2:
                continue
            outflows = [t for t in tx_list if t.amount < 0]
            inflows = [t for t in tx_list if t.amount > 0]
            if not outflows or not inflows:
                continue
            for t_out in outflows:
                if t_out.row_index in used:
                    continue
                d1 = parsed_dates.get(t_out.row_index)
                c1 = t_out.raw_description + " " + (t_out.memo or "")
                for t_in in inflows:
                    if t_in.row_index in used:
                        continue
                    d2 = parsed_dates.get(t_in.row_index)
                    days_diff = abs((d1 - d2).days) if (d1 and d2) else 0
                    if days_diff <= 3:
                        c2 = t_in.raw_description + " " + (t_in.memo or "")
                        if transfer_keywords.search(c1) and transfer_keywords.search(c2):
                            pairs[t_out.row_index] = t_in.row_index
                            pairs[t_in.row_index] = t_out.row_index
                            used.add(t_out.row_index)
                            used.add(t_in.row_index)
                            break
        return pairs

    def analyze_statement(
        self,
        csv_content: str,
        statement_name: str = "uploaded_statement.csv",
        sign_convention: str = "auto",
    ) -> StatementAnalysisResponse:
        raw_txs, detected_format, warnings = parse_statement_csv(csv_content, sign_convention)
        seen_signatures: Dict[Tuple[str, str, float], int] = {}
        transfer_pairs = self._find_transfer_pairs(raw_txs)

        # Collect posted transaction signatures and recurring cadence in a single pass
        posted_signatures: set[Tuple[str, float]] = set()
        recurring_rows: set[int] = set()
        grouped_cadence: Dict[Tuple[str, float], List[int]] = defaultdict(list)
        for r_tx in raw_txs:
            norm = normalize_merchant_name(r_tx.raw_description)
            amt = round(abs(r_tx.amount), 2)
            grouped_cadence[(norm, amt)].append(r_tx.row_index)
            is_pend = bool(
                (r_tx.raw_status and PENDING_INDICATOR_RE.search(r_tx.raw_status))
                or PENDING_INDICATOR_RE.search(r_tx.raw_description)
            )
            if not is_pend:
                posted_signatures.add((norm, amt))

        for row_indices in grouped_cadence.values():
            if len(row_indices) >= 2:
                recurring_rows.update(row_indices)

        categorized: List[CategorizedTransaction] = [
            self.categorize_row(tx, seen_signatures, transfer_pairs, posted_signatures, recurring_rows) for tx in raw_txs
        ]
        return self.build_summary_response(
            statement_name=statement_name,
            detected_format=detected_format,
            transactions=categorized,
            warnings=warnings,
            sign_convention=sign_convention,
        )

    @staticmethod
    def build_summary_response(
        statement_name: str,
        detected_format: str,
        transactions: List[CategorizedTransaction],
        warnings: Optional[List[str]] = None,
        sign_convention: str = "auto",
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
            if tx.transaction_type in (TransactionType.DUPLICATE, TransactionType.EXCLUDED) and not tx.needs_review:
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
                # Stop clipping negative net spend; show refunds exceeding spend explicitly (Bug 8)
                net = round(gross - refunds, 2)
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

        auto_categorized = len(transactions) - needs_review_count - duplicate_count
        net_expenses = round(gross_expenses - total_refund_offsets, 2)
        amount_in_review = round(sum(tx.abs_amount for tx in transactions if tx.needs_review), 2)
        provisional = needs_review_count > 0
        parse_errors = [w for w in (warnings or []) if w.startswith("Row ")]
        parse_warnings = [w for w in (warnings or []) if not w.startswith("Row ")]

        return StatementAnalysisResponse(
            statement_name=statement_name,
            detected_bank_format=detected_format,
            sign_convention=sign_convention,
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
            estimated_deductible_total=round(estimated_deductible, 2),
            amount_in_review=amount_in_review,
            provisional=provisional,
            category_summaries=category_summaries,
            transactions=transactions,
            parse_warnings=parse_warnings,
            parse_errors=parse_errors,
        )
