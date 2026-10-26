from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field

from app.models import TaxCategory, TaxFlag, TransactionType


class RuleDefinition(BaseModel):
    rule_id: str
    pattern: str
    category: TaxCategory
    base_confidence: float = Field(ge=0.0, le=1.0)
    explanation: str
    default_type: TransactionType = TransactionType.EXPENSE
    tax_flag: TaxFlag = TaxFlag.NONE
    positive_examples: List[str] = Field(default_factory=list)
    negative_examples: List[str] = Field(default_factory=list)


class TrapDefinition(BaseModel):
    trap_id: str
    pattern: str
    max_confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    suggested_categories: List[TaxCategory] = Field(default_factory=list)
    tax_flag: TaxFlag = TaxFlag.OPAQUE_MERCHANT
    positive_examples: List[str] = Field(default_factory=list)
    negative_examples: List[str] = Field(default_factory=list)
