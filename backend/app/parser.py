from __future__ import annotations

import csv
import io
import re
from datetime import datetime
from typing import List, Optional, Tuple
from .models import RawTransaction


# Common bank noise prefixes/suffixes to strip when normalizing merchant names
NOISE_PREFIX_RE = re.compile(
    r"^(?:POS\s+DEBIT\s*-?\s*|POS\s+PURCHASE\s*-?\s*|CHECKCARD\s+\d{4}\s+|"
    r"VISA\s+PURCHASE\s+|MC\s+PURCHASE\s+|ACH\s+DEBIT\s+|ACH\s+CREDIT\s+|"
    r"RECURRING\s+PAYMENT\s+|APLPAY\s+|GOOGLE\s+PAY\s+)",
    re.I,
)
PROCESSOR_PREFIX_RE = re.compile(r"^(?:SQ\s*\*|TST\*\s*|PP\*\s*|SP\s*\*\s*|IN\s*\*\s*)", re.I)
TRAILING_STORE_AND_REF_RE = re.compile(
    r"(?:\s+#\d+|\s+STORE\s+\d+|\s+\d{4,}|\s+\d{3}-\d{3}-\d{4}|\s+[A-Z]{2}\s+US|\s+US$)",
    re.I,
)


def normalize_merchant_name(raw_description: str) -> str:
    """Cleans bank statement noise to produce a canonical merchant key."""
    cleaned = raw_description.strip()
    cleaned = NOISE_PREFIX_RE.sub("", cleaned)
    cleaned = PROCESSOR_PREFIX_RE.sub("", cleaned)
    # Remove refund/pending tags from merchant identity while keeping core vendor
    cleaned = re.sub(
        r"\b(PENDING|PRE-?AUTH|AUTH\s*HOLD|REFUND|RETURN|CREDIT|REVERSAL|DEPOSIT\s*RET\w*)\b",
        "",
        cleaned,
        flags=re.I,
    )
    cleaned = TRAILING_STORE_AND_REF_RE.sub("", cleaned)
    cleaned = re.sub(r"[*_\-/]+", " ", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned.upper() if cleaned else raw_description.strip().upper()


def parse_Flexible_date(raw_date: str) -> str:
    """Normalizes varied bank date formats into ISO YYYY-MM-DD."""
    cleaned = raw_date.strip()
    if not cleaned:
        return "2025-01-01"
    formats = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%d/%m/%Y",
        "%d-%b-%Y",
        "%d-%b-%y",
        "%b %d, %Y",
        "%Y/%m/%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(cleaned, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return cleaned


def parse_currency_value(val: Optional[str]) -> Optional[float]:
    """Parses messy currency strings like '$1,240.50', '($45.00)', '-120.00 CR'."""
    if val is None:
        return None
    s = val.strip()
    if not s or s in ("-", "--", "N/A"):
        return None

    is_negative = False
    if s.startswith("(") and s.endswith(")"):
        is_negative = True
        s = s[1:-1].strip()
    if s.startswith("-"):
        is_negative = True
        s = s[1:].strip()
    if s.endswith("-"):
        is_negative = True
        s = s[:-1].strip()

    is_cr = False
    if re.search(r"\bCR\b", s, re.I):
        is_cr = True
        s = re.sub(r"\bCR\b", "", s, flags=re.I).strip()
    if re.search(r"\bDR\b", s, re.I):
        s = re.sub(r"\bDR\b", "", s, flags=re.I).strip()

    s = re.sub(r"[$€£,\s]", "", s)
    try:
        num = float(s)
    except ValueError:
        return None

    if is_negative:
        num = -abs(num)
    elif is_cr:
        num = -abs(num)
    return num


def parse_statement_csv(csv_content: str) -> Tuple[List[RawTransaction], str, List[str]]:
    """
    Parses messy CSV bank/credit card statements across three common formats:
      1. Chase / Checking Signed Single-Column ('Amount' where negative = expense, positive = credit/income)
      2. Amex / Inverted Credit Card Single-Column ('Charge' or positive expenses where 'Type'='Charge'/'Credit' or positive = expense)
      3. Split Column ('Debit' / 'Withdrawal' and 'Credit' / 'Deposit')

    Returns (transactions, detected_format, warnings)
    where every RawTransaction.amount is normalized so:
      - Negative (< 0) = Outflow / Expense
      - Positive (> 0) = Inflow / Refund / Income
    """
    warnings: List[str] = []
    # Strip BOM and blank leading lines cleanly
    cleaned_csv = csv_content.lstrip("\ufeff").strip()
    if not cleaned_csv:
        return [], "empty", ["Uploaded CSV is empty."]

    lines = [line for line in cleaned_csv.splitlines() if line.strip()]
    # Skip bank metadata preamble rows before the actual header row
    header_idx = 0
    for idx, line in enumerate(lines[:10]):
        lower = line.lower()
        if ("date" in lower) and any(
            k in lower for k in ("description", "merchant", "payee", "narrative", "memo", "details")
        ):
            header_idx = idx
            break
    if header_idx > 0:
        warnings.append(f"Skipped {header_idx} bank metadata preamble row(s) before CSV header.")

    reader = csv.DictReader(io.StringIO("\n".join(lines[header_idx:])))
    if not reader.fieldnames:
        return [], "unknown", ["Could not detect CSV column headers."]

    field_map = {f.strip().lower(): f for f in reader.fieldnames if f}

    def find_col(candidates: List[str]) -> Optional[str]:
        for c in candidates:
            if c in field_map:
                return field_map[c]
        for k, orig in field_map.items():
            if any(c in k for c in candidates):
                return orig
        return None

    date_col = find_col(["transaction date", "post date", "date", "posted date"])
    desc_col = find_col(["description", "merchant", "payee", "narrative", "details"])
    amount_col = find_col(["amount", "transaction amount", "charge amount"])
    debit_col = find_col(["debit", "withdrawal", "outflow", "charges"])
    credit_col = find_col(["credit", "deposit", "inflow", "payments"])
    type_col = find_col(["type", "transaction type", "dr/cr", "direction"])
    status_col = find_col(["status", "state", "posting status"])
    memo_col = find_col(["memo", "notes", "reference", "extended details"])

    if not desc_col:
        return [], "invalid", ["Missing required description/merchant column in CSV."]

    raw_rows = list(reader)
    if not raw_rows:
        return [], "empty", ["CSV header found, but statement contains 0 transaction rows."]

    # Determine format & sign convention
    detected_format = "Single-Column Signed (Chase / Checking Style)"
    invert_single_amount = False

    if debit_col and credit_col and not amount_col:
        detected_format = "Split Debit/Credit Columns (Mercury / Commercial Checking Style)"
    elif amount_col:
        # Check if this is an Amex-style statement where charges are positive numbers
        sample_vals = []
        has_explicit_charge_col = amount_col.strip().lower() in ("charge amount", "charges")
        for r in raw_rows:
            val = parse_currency_value(r.get(amount_col))
            desc = (r.get(desc_col) or "").upper()
            tx_type = (r.get(type_col) or "").upper() if type_col else ""
            if val is not None and val != 0:
                sample_vals.append((val, desc, tx_type))

        pos_count = sum(1 for v, _, _ in sample_vals if v > 0)
        neg_count = sum(1 for v, _, _ in sample_vals if v < 0)
        # If majority of rows are positive AND they aren't client payouts, it's an Amex positive-charge card statement
        if has_explicit_charge_col or (pos_count > neg_count * 2 and len(sample_vals) >= 3):
            detected_format = "Credit Card Positive-Charge Format (Amex Style — Signs Auto-Normalized)"
            invert_single_amount = True

    transactions: List[RawTransaction] = []
    for idx, row in enumerate(raw_rows, start=1):
        raw_desc = (row.get(desc_col) or "").strip()
        raw_date = (row.get(date_col) or "").strip() if date_col else "2025-01-01"
        raw_status = (row.get(status_col) or "").strip() if status_col else None
        raw_memo = (row.get(memo_col) or "").strip() if memo_col else None
        raw_type = (row.get(type_col) or "").strip().upper() if type_col else ""

        if not raw_desc and not raw_date:
            continue

        signed_amount: Optional[float] = None
        if debit_col and credit_col and (row.get(debit_col) or row.get(credit_col)):
            d_val = parse_currency_value(row.get(debit_col))
            c_val = parse_currency_value(row.get(credit_col))
            if d_val is not None and d_val != 0:
                signed_amount = -abs(d_val)
            elif c_val is not None and c_val != 0:
                signed_amount = abs(c_val)
            else:
                signed_amount = 0.0
        elif amount_col:
            val = parse_currency_value(row.get(amount_col))
            if val is not None:
                if raw_type in ("DEBIT", "CHARGE", "SALE", "PURCHASE") and val > 0:
                    signed_amount = -abs(val)
                elif raw_type in ("CREDIT", "REFUND", "PAYMENT", "DEPOSIT", "RETURN") and val < 0:
                    signed_amount = abs(val)
                elif invert_single_amount:
                    signed_amount = -val
                else:
                    signed_amount = val

        if signed_amount is None or (signed_amount == 0.0 and not raw_desc):
            warnings.append(f"Row {idx}: Skipped malformed or zero-amount row ('{raw_desc}').")
            continue

        transactions.append(
            RawTransaction(
                row_index=idx,
                date=parse_Flexible_date(raw_date),
                raw_description=raw_desc,
                amount=round(signed_amount, 2),
                source_format=detected_format,
                raw_status=raw_status or None,
                memo=raw_memo or None,
            )
        )

    return transactions, detected_format, warnings
