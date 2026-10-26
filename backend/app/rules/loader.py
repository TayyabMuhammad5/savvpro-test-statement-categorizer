from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any, Dict, List, Pattern, Tuple
import yaml

from app.models import TaxCategory, TaxFlag, TransactionType
from .schema import RuleDefinition, TrapDefinition


@dataclass(frozen=True)
class MerchantRule:
    rule_id: str
    pattern: Pattern[str]
    category: TaxCategory
    base_confidence: float
    explanation: str
    default_type: TransactionType = TransactionType.EXPENSE
    tax_flag: TaxFlag = TaxFlag.NONE
    positive_examples: List[str] = field(default_factory=list)
    negative_examples: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class AmbiguityTrap:
    trap_id: str
    pattern: Pattern[str]
    max_confidence: float
    reason: str
    suggested_categories: List[TaxCategory] = field(default_factory=list)
    tax_flag: TaxFlag = TaxFlag.OPAQUE_MERCHANT
    positive_examples: List[str] = field(default_factory=list)
    negative_examples: List[str] = field(default_factory=list)


SCHEDULE_C_MAPPING: Dict[TaxCategory, Tuple[str, float]] = {
    TaxCategory.GEAR_RENTALS: ("Line 20a — Rent/Lease Machinery & Equipment (Cameras/Lenses)", 1.0),
    TaxCategory.CAMERA_EQUIPMENT: ("Line 13 / Line 22 — Section 179 Equipment & Supplies", 1.0),
    TaxCategory.PHOTOBOOK_PRINTING: ("Part III Line 38 — Cost of Goods Sold (Print & Bindery)", 1.0),
    TaxCategory.SOFTWARE_WORKFLOW: ("Line 18 — Office & Digital Workflow Subscriptions", 1.0),
    TaxCategory.STUDIO_LOCATIONS: ("Line 20b / Line 23 — Studio Rent & Shoot Location Permits", 1.0),
    TaxCategory.TRAVEL_TRANSPORT: ("Line 24a — Shoot Travel, Airfare, Lodging & Transit", 1.0),
    TaxCategory.SHIPPING_PACKAGING: ("Line 18 / COGS — Book Fulfillment, Mailers & Postage", 1.0),
    TaxCategory.PROPS_REFERENCE_BOOKS: ("Line 22 — Set Props, Styling & Photo Reference Books", 1.0),
    TaxCategory.CLIENT_CREW_MEALS: ("Line 24b — Deductible Client & Shoot Crew Meals (50%)", 0.5),
    TaxCategory.MARKETING_BOOK_FAIRS: ("Line 8 — Advertising, Portfolio & Art Book Fair Booths", 1.0),
    TaxCategory.INSURANCE_LEGAL: ("Line 15 / Line 17 — Gear Insurance, Copyright & Guilds", 1.0),
    TaxCategory.BANK_MERCHANT_FEES: ("Line 10 / Line 27a — Merchant Processing & FX Fees", 1.0),
    TaxCategory.CONTRACT_LABOR: ("Line 11 — Contract Labor (Second Shooters, Assistants, Retouchers)", 1.0),
    TaxCategory.CLIENT_BOOK_INCOME: ("Part I Line 1 — Gross Receipts (Shoots & Book Sales)", 0.0),
    TaxCategory.NON_DEDUCTIBLE_TRANSFER: ("Excluded — Internal Transfer / Credit Card Payment", 0.0),
    TaxCategory.PERSONAL_NON_DEDUCTIBLE: ("Excluded — Personal / Non-Deductible Expense", 0.0),
    TaxCategory.NEEDS_REVIEW: ("Pending — Requires Photographer Verification", 0.0),
}

# Categories whose vendors are strictly expense-side
EXPENSE_ONLY_CATEGORIES = {
    TaxCategory.GEAR_RENTALS,
    TaxCategory.CAMERA_EQUIPMENT,
    TaxCategory.PHOTOBOOK_PRINTING,
    TaxCategory.SOFTWARE_WORKFLOW,
    TaxCategory.STUDIO_LOCATIONS,
    TaxCategory.TRAVEL_TRANSPORT,
    TaxCategory.SHIPPING_PACKAGING,
    TaxCategory.PROPS_REFERENCE_BOOKS,
    TaxCategory.CLIENT_CREW_MEALS,
    TaxCategory.MARKETING_BOOK_FAIRS,
    TaxCategory.INSURANCE_LEGAL,
    TaxCategory.BANK_MERCHANT_FEES,
    TaxCategory.CONTRACT_LABOR,
}

# Regex indicators
REFUND_INDICATOR_RE = re.compile(
    r"\b(REFUND|RETURN|CREDIT|REVERSAL|REBATE|DEPOSIT\s*RET|SEC\s*DEP\s*RELEASE|OVERPAYMENT|DISPUTE\s*CREDIT|DEFECT\s*CREDIT)\b",
    re.I,
)

PENDING_INDICATOR_RE = re.compile(
    r"\b(PENDING|PRE-?AUTH|AUTH\s*HOLD|PROVISIONAL)\b",
    re.I,
)


def _load_yaml_file(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or []


def load_rules_from_yaml(base_dir: Path | None = None) -> Dict[str, List[Any]]:
    """Loads and validates all rules from YAML files."""
    if base_dir is None:
        base_dir = Path(__file__).parent

    # 1. Transfers
    transfers_raw = _load_yaml_file(base_dir / "transfers.yaml")
    transfer_rules: List[MerchantRule] = []
    for item in transfers_raw:
        def_obj = RuleDefinition.model_validate(item)
        compiled_pat = re.compile(def_obj.pattern, re.I)
        transfer_rules.append(
            MerchantRule(
                rule_id=def_obj.rule_id,
                pattern=compiled_pat,
                category=def_obj.category,
                base_confidence=def_obj.base_confidence,
                explanation=def_obj.explanation,
                default_type=def_obj.default_type,
                tax_flag=def_obj.tax_flag,
                positive_examples=def_obj.positive_examples,
                negative_examples=def_obj.negative_examples,
            )
        )

    # 2. Merchants
    merchants_raw = _load_yaml_file(base_dir / "merchants.yaml")
    merchant_rules: List[MerchantRule] = []
    for item in merchants_raw:
        def_obj = RuleDefinition.model_validate(item)
        compiled_pat = re.compile(def_obj.pattern, re.I)
        merchant_rules.append(
            MerchantRule(
                rule_id=def_obj.rule_id,
                pattern=compiled_pat,
                category=def_obj.category,
                base_confidence=def_obj.base_confidence,
                explanation=def_obj.explanation,
                default_type=def_obj.default_type,
                tax_flag=def_obj.tax_flag,
                positive_examples=def_obj.positive_examples,
                negative_examples=def_obj.negative_examples,
            )
        )

    # 3. Keywords
    keywords_raw = _load_yaml_file(base_dir / "keywords.yaml")
    keyword_rules: List[MerchantRule] = []
    for item in keywords_raw:
        def_obj = RuleDefinition.model_validate(item)
        compiled_pat = re.compile(def_obj.pattern, re.I)
        keyword_rules.append(
            MerchantRule(
                rule_id=def_obj.rule_id,
                pattern=compiled_pat,
                category=def_obj.category,
                base_confidence=def_obj.base_confidence,
                explanation=def_obj.explanation,
                default_type=def_obj.default_type,
                tax_flag=def_obj.tax_flag,
                positive_examples=def_obj.positive_examples,
                negative_examples=def_obj.negative_examples,
            )
        )

    # 4. Traps
    traps_raw = _load_yaml_file(base_dir / "traps.yaml")
    trap_rules: List[AmbiguityTrap] = []
    for item in traps_raw:
        trap_obj = TrapDefinition.model_validate(item)
        compiled_pat = re.compile(trap_obj.pattern, re.I)
        trap_rules.append(
            AmbiguityTrap(
                trap_id=trap_obj.trap_id,
                pattern=compiled_pat,
                max_confidence=trap_obj.max_confidence,
                reason=trap_obj.reason,
                suggested_categories=trap_obj.suggested_categories,
                tax_flag=trap_obj.tax_flag,
                positive_examples=trap_obj.positive_examples,
                negative_examples=trap_obj.negative_examples,
            )
        )

    return {
        "transfers": transfer_rules,
        "merchants": merchant_rules,
        "keywords": keyword_rules,
        "traps": trap_rules,
    }


# Initial load at module import
_DATA = load_rules_from_yaml()
TRANSFER_RULES = _DATA["transfers"]
MERCHANT_RULES = _DATA["merchants"]
KEYWORD_HEURISTICS = _DATA["keywords"]
AMBIGUITY_TRAPS = _DATA["traps"]
