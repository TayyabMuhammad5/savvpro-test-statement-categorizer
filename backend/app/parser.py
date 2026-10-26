from __future__ import annotations

import csv
import io
import re
from datetime import datetime
from functools import lru_cache
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


@lru_cache(maxsize=8192)
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


@lru_cache(maxsize=8192)
def parse_Flexible_date(raw_date: str, prefer_day_first: bool = False) -> Optional[str]:
    """Normalizes varied bank date formats into ISO YYYY-MM-DD. Never fabricates dates."""
    cleaned = raw_date.strip()
    if not cleaned:
        return None
    # Fast path: already YYYY-MM-DD
    if len(cleaned) == 10 and cleaned[4] == "-" and cleaned[7] == "-":
        try:
            from datetime import date
            return date.fromisoformat(cleaned).isoformat()
        except ValueError:
            pass
    if prefer_day_first:
        formats = [
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%d/%m/%y",
            "%d-%m-%Y",
            "%d-%b-%Y",
            "%d-%b-%y",
            "%m/%d/%Y",
            "%m/%d/%y",
            "%b %d, %Y",
            "%Y/%m/%d",
        ]
    else:
        formats = [
            "%Y-%m-%d",
            "%m/%d/%Y",
            "%m/%d/%y",
            "%d/%m/%Y",
            "%d/%m/%y",
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
    return None


@lru_cache(maxsize=8192)
def parse_currency_value(val: Optional[str]) -> Optional[float]:
    """Parses messy currency strings like '$1,240.50', '($45.00)', '-120.00 CR', '1.240,50'."""
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

    # Remove currency symbols and whitespace
    s = re.sub(r"[$€£\s]", "", s)

    # European decimal comma handling:
    # 1. Both dot and comma present (e.g. 1.240,50 vs 1,240.50)
    if "." in s and "," in s:
        if s.rfind(",") > s.rfind("."):
            # 1.240,50 -> dot is thousand separator, comma is decimal
            s = s.replace(".", "").replace(",", ".")
        else:
            # 1,240.50 -> comma is thousand separator, dot is decimal
            s = s.replace(",", "")
    elif "," in s and "." not in s:
        # e.g. 1240,50 or 45,99
        if re.search(r",\d{1,2}$", s):
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    else:
        s = s.replace(",", "")

    try:
        num = float(s)
    except ValueError:
        return None

    if is_negative:
        num = -abs(num)
    elif is_cr:
        num = -abs(num)
    return num


def parse_statement_csv(
    csv_content: str,
    sign_convention: str = "auto",
) -> Tuple[List[RawTransaction], str, List[str]]:
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

    # Header search without 10-line limit
    header_idx = 0
    for idx, line in enumerate(lines):
        lower = line.lower()
        if ("date" in lower) and any(
            k in lower for k in ("description", "merchant", "payee", "narrative", "memo", "details", "name", "amount")
        ):
            header_idx = idx
            break
    if header_idx > 0:
        warnings.append(f"Skipped {header_idx} bank metadata preamble row(s) before CSV header.")

    # Delimiter sniffing (comma, semicolon, tab)
    header_line = lines[header_idx] if header_idx < len(lines) else lines[0]
    delimiter = ","
    if ";" in header_line and header_line.count(";") >= header_line.count(","):
        delimiter = ";"
    elif "\t" in header_line and header_line.count("\t") >= header_line.count(","):
        delimiter = "\t"

    content_from_header = "\n".join(lines[header_idx:])
    reader = csv.DictReader(io.StringIO(content_from_header), delimiter=delimiter)
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

    date_col = find_col(["transaction date", "post date", "date", "posted date", "datum", "date de valeur"])
    desc_col = find_col(["description", "merchant", "payee", "narrative", "details", "libelle", "verwendungszweck"])
    amount_col = find_col(["amount", "transaction amount", "charge amount", "montant", "betrag", "valeur", "value", "importe"])
    debit_col = find_col(["debit", "withdrawal", "outflow", "charges", "ausgaben", "retrait"])
    credit_col = find_col(["credit", "deposit", "inflow", "payments", "einnahmen", "depot"])
    type_col = find_col(["type", "transaction type", "dr/cr", "direction"])
    status_col = find_col(["status", "state", "posting status"])
    memo_col = find_col(["memo", "notes", "reference", "extended details"])
    category_col = find_col(["category", "bank category", "classification"])

    if not desc_col:
        return [], "invalid", ["Missing required description/merchant column in CSV."]

    raw_rows = list(reader)
    if not raw_rows:
        return [], "empty", ["CSV header found, but statement contains 0 transaction rows."]

    # Determine format & sign convention
    # Sign is determined from EXPLICIT evidence only:
    #   1. "Charge Amount" / "Charges" column header name
    #   2. Type column with Charge/Sale values  
    #   3. Split Debit/Credit columns
    #   4. Preamble text (e.g. "Amex" in preamble)
    # The old "majority positive => Amex" heuristic is DELETED per spec.
    detected_format = "Single-Column Signed (Chase / Checking Style)"
    invert_single_amount = False

    if sign_convention == "charges_positive":
        invert_single_amount = True
        detected_format = "Single-Column (User Override: Charges Positive)"
    elif sign_convention == "charges_negative":
        invert_single_amount = False
        detected_format = "Single-Column (User Override: Charges Negative)"
    elif debit_col and credit_col and not amount_col:
        detected_format = "Split Debit/Credit Columns (Mercury / Commercial Checking Style)"
    elif amount_col:
        has_explicit_charge_col = amount_col.strip().lower() in ("charge amount", "charges")
        # Check for Type column with Charge/Sale values as explicit evidence
        has_type_evidence = False
        if type_col:
            for r in raw_rows:
                tx_type = (r.get(type_col) or "").strip().upper()
                if tx_type in ("CHARGE", "SALE", "DEBIT", "PURCHASE"):
                    has_type_evidence = True
                    break

        if has_explicit_charge_col:
            detected_format = "Credit Card Positive-Charge Format (Amex Style — Signs Auto-Normalized)"
            invert_single_amount = True
            sign_convention = "charges_positive"
        elif has_type_evidence:
            # Type column provides per-row sign determination; no global inversion needed.
            # The per-row logic below handles DEBIT/CHARGE/SALE -> negative, CREDIT/REFUND -> positive
            detected_format = "Single-Column with Type Indicator"
            sign_convention = "auto"
        else:
            # No explicit evidence to determine sign convention
            # Check if all amounts are same sign (ambiguous)
            sample_vals = []
            for r in raw_rows:
                val = parse_currency_value(r.get(amount_col))
                if val is not None and val != 0:
                    sample_vals.append(val)
            if sample_vals:
                all_positive = all(v > 0 for v in sample_vals)
                all_negative = all(v < 0 for v in sample_vals)
                has_mixed = not all_positive and not all_negative
                if has_mixed:
                    # Mixed signs = Chase-style signed, which is the default
                    sign_convention = "charges_negative"
                elif all_positive:
                    # Ambiguous: could be all-income checking or Amex-style
                    # Do NOT guess — keep as-is and warn
                    sign_convention = "unknown"
                    warnings.append(
                        "All transaction amounts are positive and no Type/Charge column found. "
                        "Sign convention is ambiguous — amounts are kept as-is (positive = inflow). "
                        "If this is a credit card statement where charges are positive, "
                        "select 'charges_positive' in the sign convention selector."
                    )

    has_day_gt_12 = False
    has_month_gt_12 = False
    has_slashes = False
    if date_col:
        for r in raw_rows[:100]:
            d_val = (r.get(date_col) or "").strip()
            parts = re.split(r"[/\-.]", d_val)
            if len(parts) >= 2:
                try:
                    p1, p2 = int(parts[0]), int(parts[1])
                    has_slashes = True
                    if p1 > 12:
                        has_day_gt_12 = True
                    elif p2 > 12:
                        has_month_gt_12 = True
                except ValueError:
                    pass

    prefer_day_first = has_day_gt_12 and not has_month_gt_12
    if not has_day_gt_12 and not has_month_gt_12 and has_slashes:
        warnings.append("Date format is ambiguous (all day/month numbers <= 12). Defaulted to MM/DD/YYYY.")

    transactions: List[RawTransaction] = []
    for idx, row in enumerate(raw_rows, start=1):
        raw_desc = (row.get(desc_col) or "").strip()
        raw_date = (row.get(date_col) or "").strip() if date_col else ""
        raw_status = (row.get(status_col) or "").strip() if status_col else None
        raw_memo = (row.get(memo_col) or "").strip() if memo_col else None
        raw_type = (row.get(type_col) or "").strip().upper() if type_col else ""
        raw_bank_cat = (row.get(category_col) or "").strip() if category_col else None

        if not raw_desc and not raw_date:
            continue

        parsed_date = parse_Flexible_date(raw_date, prefer_day_first=prefer_day_first)
        if not parsed_date:
            warnings.append(f"Row {idx}: Missing or unparseable transaction date ('{raw_date}').")
            parsed_date = "INVALID_DATE"

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
                date=parsed_date,
                raw_description=raw_desc,
                amount=round(signed_amount, 2),
                source_format=detected_format,
                raw_status=raw_status or None,
                memo=raw_memo or None,
                bank_category=raw_bank_cat or None,
            )
        )

    return transactions, detected_format, warnings
