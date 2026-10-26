export type TransactionType = 'expense' | 'refund' | 'income' | 'transfer' | 'duplicate' | 'excluded';

export type TaxFlag =
  | 'NONE'
  | 'SECTION_179_CANDIDATE'
  | 'MEALS_50_PERCENT'
  | 'CONTRA_EXPENSE_REFUND'
  | 'INTERNAL_TRANSFER'
  | 'PENDING_OR_DUPLICATE'
  | 'OPAQUE_MERCHANT';

export interface DecisionSignal {
  layer: string;
  rule_id: string;
  detail: string;
  weight: number;
}

export interface AlternativeReason {
  category: string;
  reason: string;
}

export interface CategorizedTransaction {
  id: string;
  row_index: number;
  date: string;
  raw_description: string;
  normalized_merchant: string;
  amount: number;
  abs_amount: number;
  category: string;
  suggested_categories: string[];
  alternative_reasons?: AlternativeReason[];
  transaction_type: TransactionType;
  confidence: number;
  needs_review: boolean;
  review_reason?: string | null;
  explanation: string;
  matched_rule: string;
  signals: DecisionSignal[];
  tax_flag: TaxFlag;
  tax_note?: string | null;
  deductible_rate: number;
  deductible_impact: number;
  user_overridden: boolean;
  bank_category?: string | null;
}

export interface CategorySummary {
  category: string;
  schedule_c_line: string;
  transaction_count: number;
  gross_spend: number;
  refunds_and_credits: number;
  net_spend: number;
  deductible_rate: number;
  deductible_amount: number;
}

export interface StatementAnalysisResponse {
  statement_name: string;
  detected_bank_format: string;
  total_rows: number;
  auto_categorized_count: number;
  needs_review_count: number;
  duplicate_or_pending_count: number;
  transfer_count: number;
  refund_count: number;
  gross_income: number;
  gross_expenses: number;
  total_refund_offsets: number;
  net_expenses: number;
  estimated_deductible_total: number;
  amount_in_review?: number;
  provisional_spending?: boolean;
  category_summaries: CategorySummary[];
  transactions: CategorizedTransaction[];
  parse_warnings: string[];
  sign_convention?: string;
  tax_disclaimer?: string;
}

export interface SamplePreset {
  id: string;
  name: string;
  filename: string;
  description: string;
  csv: string;
}

export interface RowDecision {
  action?: 'keep' | 'exclude' | 'categorize';
  category?: string;
  transaction_type?: string;
  confirm_income_on_outflow?: boolean;
}

export interface APIError {
  code: string;
  message: string;
  details?: any;
}
