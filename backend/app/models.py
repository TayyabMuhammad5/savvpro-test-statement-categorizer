from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class TransactionType(str, Enum):
    EXPENSE = "expense"
    REFUND = "refund"          # Contra-expense: money returned from a vendor, reduces category expense
    INCOME = "income"          # Client retainers, print store payouts, book royalties
    TRANSFER = "transfer"      # Credit card autopay, transfers to savings, owner draws (non-taxable/non-deductible)
    DUPLICATE = "duplicate"    # Pending authorization hold or duplicate row excluded from totals


class TaxCategory(str, Enum):
    GEAR_RENTALS = "Gear & Lens Rentals"
    CAMERA_EQUIPMENT = "Camera Equipment & Lighting"
    PHOTOBOOK_PRINTING = "Photobook Printing & Lab COGS"
    SOFTWARE_WORKFLOW = "Software & Digital Workflow"
    STUDIO_LOCATIONS = "Studio, Darkroom & Permits"
    TRAVEL_TRANSPORT = "Shoot Travel & Transport"
    SHIPPING_PACKAGING = "Shipping & Book Fulfillment"
    PROPS_REFERENCE_BOOKS = "Props, Styling & Reference Books"
    CLIENT_CREW_MEALS = "Client & Crew Meals (50%)"
    MARKETING_BOOK_FAIRS = "Marketing, Book Fairs & Portfolio"
    INSURANCE_LEGAL = "Insurance, Copyright & Guilds"
    BANK_MERCHANT_FEES = "Bank & Processing Fees"
    CLIENT_BOOK_INCOME = "Client Shoot & Book Income"
    NON_DEDUCTIBLE_TRANSFER = "Non-Deductible / Transfer"
    PERSONAL_NON_DEDUCTIBLE = "Personal / Non-Deductible"
    NEEDS_REVIEW = "Needs Review"


class TaxFlag(str, Enum):
    NONE = "NONE"
    SECTION_179_CANDIDATE = "SECTION_179_CANDIDATE"   # Equipment >= $2,500 De Minimis Safe Harbor threshold
    MEALS_50_PERCENT = "MEALS_50_PERCENT"             # IRS 50% deduction limit on business meals
    CONTRA_EXPENSE_REFUND = "CONTRA_EXPENSE_REFUND"   # Vendor refund/deposit return offsetting expense, NOT income
    INTERNAL_TRANSFER = "INTERNAL_TRANSFER"           # Movement between own accounts / credit card bill payment
    PENDING_OR_DUPLICATE = "PENDING_OR_DUPLICATE"     # Unsettled hold or duplicate transaction row
    OPAQUE_MERCHANT = "OPAQUE_MERCHANT"               # Multi-category vendor (Amazon, Target, PayPal, Cafe)


class RawTransaction(BaseModel):
    row_index: int
    date: str
    raw_description: str
    amount: float  # Signed normalized: negative = money out (expense/outflow), positive = money in (refund/income/credit)
    source_format: str = "standard"
    raw_status: Optional[str] = None
    memo: Optional[str] = None


class DecisionSignal(BaseModel):
    layer: str
    rule_id: str
    detail: str
    weight: float


class CategorizedTransaction(BaseModel):
    id: str
    row_index: int
    date: str
    raw_description: str
    normalized_merchant: str
    amount: float  # Signed amount: negative = money out (spend), positive = money in (refund/income)
    abs_amount: float
    category: TaxCategory
    suggested_categories: List[TaxCategory] = Field(default_factory=list)
    transaction_type: TransactionType
    confidence: float = Field(ge=0.0, le=1.0)
    needs_review: bool
    review_reason: Optional[str] = None
    explanation: str
    matched_rule: str
    signals: List[DecisionSignal] = Field(default_factory=list)
    tax_flag: TaxFlag = TaxFlag.NONE
    tax_note: Optional[str] = None
    deductible_rate: float = 1.0
    deductible_impact: float = 0.0  # Net impact on deductible Schedule C expenses (refunds are negative)
    user_overridden: bool = False


class CategorySummary(BaseModel):
    category: TaxCategory
    schedule_c_line: str
    transaction_count: int
    gross_spend: float
    refunds_and_credits: float
    net_spend: float
    deductible_rate: float
    deductible_amount: float


class StatementAnalysisResponse(BaseModel):
    statement_name: str
    detected_bank_format: str
    total_rows: int
    auto_categorized_count: int
    needs_review_count: int
    duplicate_or_pending_count: int
    transfer_count: int
    refund_count: int
    gross_income: float
    gross_expenses: float
    total_refund_offsets: float
    net_expenses: float
    estimated_deductible_total: float
    category_summaries: List[CategorySummary]
    transactions: List[CategorizedTransaction]
    parse_warnings: List[str] = Field(default_factory=list)


class ReviewUpdateRequest(BaseModel):
    transaction_id: str
    new_category: TaxCategory
    transaction_type: Optional[TransactionType] = None
    remember_merchant: bool = True


class BatchAnalyzeRequest(BaseModel):
    statement_name: str = "uploaded_statement.csv"
    csv_content: str
    custom_rules: Dict[str, str] = Field(default_factory=dict)
