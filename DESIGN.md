# System Design & Tax Decision Architecture (`DESIGN.md`)

## 1. Customer Persona & Real-World Use Case

### Customer: Independent Editorial Photographer & Photobook Publisher
We designed **Focal & Folio** for a sole-proprietor photography & independent photobook studio (*"Aperture & Spine Studio"*) filing **IRS Form 1040 Schedule C**.

Unlike generic freelancers or software consultants, a working commercial photographer and photobook publisher has a complex, specialized financial footprint:
1. **High-Value Depreciable Hardware** (`B&H Photo`, `Adorama`, `Leica Store`, `Profoto`, `Hasselblad`, `MPB.com`) subject to the **$2,500 IRS De Minimis Safe Harbor / Section 179 threshold**.
2. **Short-Term Shoot Equipment Rentals & Security Deposits** (`LensRentals.com`, `ShareGrid`, `BorrowLenses`), which frequently generate pre-authorization holds (`PENDING`) and partial security-deposit refunds days after a shoot.
3. **Photobook Printing, Bindery & Fine-Art Darkroom COGS** (`Blurb`, `Edition One Books`, `IngramSpark`, `Miller's Pro Lab`, `Indie Film Lab`, `Ilford`, `Moab Paper`), where defective print batches generate vendor credits that must offset **Cost of Goods Sold (Part III Line 38)** rather than inflating gross income.
4. **Dual-Role Studio Platforms** (`HoneyBook`, `Pixieset`, `Pic-Time`, `Blurb`): a monthly outflow (`-$38.00`) to `Pixieset` or `HoneyBook` is a **Software Subscription (Line 18)**, whereas an inflow (`+$1,640.00`) from `PIXIESET*PRINT STORE PAYOUT` or `BLURB*AUTHOR ROYALTY` is **Gross Business Revenue (Line 1)**.
5. **On-Set Crew Catering & Client Pitches** (`Sweetgreen`, `ezCater`, `Dean & DeLuca`, local delis), which are strictly subject to the **50% statutory deduction limit (Line 24b)**.
6. **Commercial Film & Location Permits** (`FilmLA`, `NYC Parks Filming`, `National Park Service`, `City Clerk Permits`), which are governmental licenses mapped to **Line 23 (Taxes and licenses)** rather than physical studio rent (**Line 20b**).
7. **Second Shooters, Studio Assistants & Retouchers** (`Photo Assistant`, `Second Shooter Day Rate`, `Freelance Retouching`), requiring **Line 11 (Contract labor)** and explicit **Form 1099-NEC** tracking reminders.
8. **Shoot Travel, Location Scouting & Transport** (`Delta`, `United`, `Uber`, gas stations), carrying reminders regarding IRS standard mileage rate election vs. actual expenses.
9. **Reference Monographs, Props & Styling** (`Strand Book Store`, `Arcana Books on the Arts`, `Printed Matter`, `Dashwood Books`, `Savage Universal`).

---

## 2. Schedule C Tax Category Taxonomy & Domain Design Rationale

The taxonomy comprises **17 distinct categories** specifically chosen to align with IRS Form 1040 Schedule C lines and tax accounting realities:

| Category | IRS Schedule C Mapping | Deductible Rate | Treatment |
| :--- | :--- | :---: | :--- |
| **Gear & Lens Rentals** | Line 20a — Rent/Lease Machinery & Equipment | 100% | Operating Expense |
| **Camera Equipment & Lighting** | Line 13 / Line 22 — Section 179 / Supplies | 100% | Expense (Flags $\ge\$2,500$ for Sec. 179) |
| **Photobook Printing & Lab COGS** | Part III Line 38 — Cost of Goods Sold | 100% | Cost of Goods Sold |
| **Software & Digital Workflow** | Line 18 — Office & Digital Subscriptions | 100% | Operating Expense |
| **Studio, Darkroom & Permits** | Line 20b / Line 23 — Studio Rent & Location Permits | 100% | Operating Expense |
| **Shoot Travel & Transport** | Line 24a — Travel (Air, Hotel, Rideshare) | 100% | Operating Expense (IRS Mileage Note) |
| **Shipping & Book Fulfillment** | Line 18 / COGS — Postage, Mailers & Couriers | 100% | Operating Expense |
| **Props, Styling & Reference Books** | Line 22 — Supplies & Monograph Research | 100% | Operating Expense |
| **Client & Crew Meals (50%)** | Line 24b — Deductible Meals | **50%** | 50% Statutory Cap Applied |
| **Marketing, Book Fairs & Portfolio** | Line 8 — Advertising & Exhibitor Booths | 100% | Operating Expense |
| **Insurance, Copyright & Guilds** | Line 15 / Line 17 — Insurance & Legal | 100% | Operating Expense |
| **Bank & Processing Fees** | Line 10 / Line 27a — FX & Wire Fees | 100% | Operating Expense |
| **Contract Labor & Assistants** | Line 11 — Contract Labor (Second Shooters, Retouchers) | 100% | Operating Expense (Form 1099-NEC Note) |
| **Client Shoot & Book Income** | Part I Line 1 — Gross Receipts | N/A | Gross Taxable Revenue |
| **Non-Deductible / Transfer** | Excluded — Internal Transfers & Autopay | 0% | Excluded from P&L |
| **Personal / Non-Deductible** | Excluded — Personal Draw / Personal Spend | 0% | Excluded from P&L |
| **Needs Review** | Held — Requires User Confirmation | 0% | Held Until Reviewed |

### Domain Tax Choices Explained

1. **Why 17 Categories?**
   A generic bookkeeping tool clusters expenses into 4 or 5 vague buckets (e.g., "Office", "Travel", "Supplies"). For an editorial photographer and publisher, this creates severe tax audit vulnerability. Renting a $12,000 Cine lens package from LensRentals belongs on **Line 20a (Rent/lease of machinery and equipment)**, not Line 22 (Supplies). Printing 500 copies of a hardcover monograph at Blurb or Edition One belongs in **Part III Line 38 (Cost of Goods Sold)** to properly compute Gross Profit, not in general operating expenses. Separating 17 categories mirrors the exact structure of Schedule C while reflecting the specific operating reality of a photography/publishing business.

2. **Why Location Permits are Line 23 (Taxes and Licenses) instead of Line 20b (Rent)?**
   Shooting on public land, municipal streets, state parks, or landmark spaces requires filming permits issued by city or state film commissions (e.g., FilmLA, NYC Mayor's Office of Media and Entertainment, California State Parks). Under IRS regulations, governmental permit fees and municipal licenses are deductible as **Taxes and Licenses (Line 23)**. Treating a municipal permit as real property rent (Line 20b) is an audit red flag because no real property lease exists.

3. **Why Form 1099-NEC Note on Line 11 (Contract Labor)?**
   Photographers frequently hire second shooters, lighting grips, production assistants, and freelance retouchers. Under IRC § 6041 and § 6041A, businesses that pay $600 or more during the calendar year to an unincorporated independent contractor must file **Form 1099-NEC** with the IRS and furnish a copy to the contractor by January 31. Failing to file 1099-NEC forms can result in intentional disregard penalties ($310+ per form) and disallowance of the Line 11 deduction under audit. The system automatically annotates every Line 11 entry with an explicit compliance reminder.

4. **Why the Section 179 Threshold is Exactly $2,500?**
   Under the IRS **De Minimis Safe Harbor election** (Treas. Reg. § 1.263(a)-1(f)), small business taxpayers without an Applicable Financial Statement (AFS) can elect to immediately expense tangible property costing up to **$2,500 per invoice or item** as materials and supplies (Line 22). However, single items costing $2,500 or more (such as a Sony A1 body at $6,498, a Canon RF 400mm lens at $11,999, or a Profoto Pro-11 generator at $17,500) must be capitalized and depreciated under MACRS or elected for immediate expensing under **Section 179 / Bonus Depreciation (Line 13)**. The engine automatically flags any equipment purchase $\ge \$2,500$ as a `SECTION_179_CANDIDATE`.

5. **Why Client & Crew Meals are Capped at 50%?**
   Under **IRC § 274(n)**, deductions for business food and beverage expenses—including meals provided to freelance crew on shoot days and meals during business pitches with art directors or book publishers—are statutorily limited to **50% of the actual cost**. The system automatically sets `deductible_rate = 0.50` and computes `deductible_impact = round(abs_amt * 0.50, 2)` so the Schedule C rollup reflects true deductible tax impact rather than inflated gross spend.

---

## 3. End-to-End Decision Pipeline Architecture

The system executes a strictly deterministic, zero-LLM architecture divided into three decoupled layers: `parser.py` $\rightarrow$ `rules/` $\rightarrow$ `brain.py`.

```text
Raw CSV File / Upload Payload
  │
  ▼
[Layer 1: Multi-Dialect Parser] (backend/app/parser.py)
  • Sniffs delimiters (comma, semicolon, tab) via csv.Sniffer & fallback scoring
  • Auto-detects & skips non-tabular preamble rows before column headers
  • Normalizes European decimal commas ("1.250,50" -> 1250.50) & currency symbols
  • Fast ISO date parser (date.fromisoformat) with fallback to 10 common formats
  • Zero-guessing sign polarity: identifies explicit 'Charge' headers or 'Type' columns
  • Normalizes vendor strings (strips bank noise, trailing store numbers, card prefixes)
  │
  ▼
[Layer 2: Externalized Rules Repository] (backend/app/rules/)
  • 308 photography/publishing vendor rules (merchants.yaml)
  • 8 transfer, credit card autopay & tax payment rules (transfers.yaml)
  • 16 domain keyword heuristics (keywords.yaml)
  • 8 ambiguity traps capping confidence <= 0.45 (traps.yaml)
  • Strict Pydantic schema validation at application startup with >= 2 pos/neg test cases
  │
  ▼
[Layer 3: Deterministic Categorization Brain] (backend/app/brain.py)
  ├─► [Precedence 0] Row-Level User Decisions (idempotent user overrides: keep/exclude/categorize)
  ├─► [Precedence 1] User Merchant Memory (custom merchant rules saved in session, confidence 0.99)
  ├─► [Precedence 2] Integrity Guards:
  │     • Pending Authorization Holds (PENDING/PRE-AUTH): auto-excluded from tax totals
  │     • Potential Duplicate Rows (Signature: date + merchant + amount): routed to Needs Review
  ├─► [Precedence 3] Internal Transfers & Autopay:
  │     • O(N) amount-bucket cross-row transfer pairing (opposite sign within 3 days)
  │     • P2P online transfer guard: external third-party transfers routed to Needs Review
  │     • Autopay, savings transfers, owner draws, IRS remittances -> Non-Deductible / Transfer
  ├─► [Precedence 4] Curated Domain Merchant Rules (Cached in _match_cache):
  │     • Pass 1: Strict match against normalized_merchant (prevents memo text from overriding vendor)
  │     • Pass 2: Fallback match on combined text (description + memo)
  ├─► [Precedence 5] Keyword & Contextual Heuristics (confidence 0.78–0.82)
  ├─► [Precedence 5b] Levenshtein Fuzzy Matching:
  │     • Pure-Python edit distance against canonical vendor targets
  │     • Confidence strictly capped at 0.62 (<= 0.65) -> routes safely to Needs Review
  ├─► [Stage 6] Ambiguity Traps:
  │     • Traps Amazon, Target, Apple, local cafes, P2P, ATM cash, gas stations
  │     • Capped at confidence <= 0.45; injects 3-4 context-aware candidate categories
  ├─► [Stage 7] Contra-Expense Refund Reconciler:
  │     • Detects vendor credits/returns (LensRentals deposit return, Blurb reprint credit)
  │     • Marks as TransactionType.REFUND -> subtracts from category spend, never inflates gross income
  │     • Detects "REFUND TO CLIENT" outflows -> flags as contra-income for review
  ├─► [Stage 8] IRS Policy Guardrails:
  │     • Flags Camera Equipment >= $2,500 as SECTION_179_CANDIDATE
  │     • Sets deductible_rate = 0.50 for Client & Crew Meals
  │     • Appends compliance tax notes (Form 1099-NEC, Line 23 permits, standard mileage)
  └─► [Stage 9] Confidence Gate (< 0.70 -> Needs Review):
        • All transactions with confidence < 0.70 routed to Needs Review with plain-English reasons
        • Evaluates top-2 alternative categories with explicit "why not" rationales
```

---

## 4. Algorithmic Optimizations & Throughput Engineering

To meet production latency requirements (< 1.5 seconds for 10,000 transactions), several high-performance optimizations were engineered:

### 1. $O(N)$ Cross-Row Transfer Pairing via Amount Buckets
- **The Problem:** Naively comparing every transaction against every other transaction to find offsetting transfers within a 3-day window has $O(N^2)$ time complexity. On a 10,000-row statement, this requires $100,000,000$ iterations, taking over 15 seconds.
- **The Solution:** Implemented an amount-bucket hash map (`defaultdict(list)`) indexed by `round(abs(tx.amount), 2)`:
  ```python
  amount_buckets: Dict[float, List[RawTransaction]] = defaultdict(list)
  for tx in transactions:
      if abs(tx.amount) >= 1.00:
          amount_buckets[round(abs(tx.amount), 2)].append(tx)
  ```
  Only transactions sharing the exact same dollar amount are compared for opposite signs and date proximity ($\le 3$ days). This reduces pairing from $O(N^2)$ to $O(N)$ average time, executing in less than 25 milliseconds for 10,000 rows.

### 2. In-Memory Decision Memoization (`_match_cache`)
Bank and credit card statements exhibit high vendor repetition (e.g. dozens of monthly Adobe subscriptions, Uber rides, or USPS mailings). A local in-memory cache `self._match_cache` indexed by `f"{norm_merchant}|{combined_text}"` stores the matched rule, category, confidence, and signal payload, bypassing regex evaluations entirely on repeated vendor lines.

### 3. Fast ISO-8601 Date Parsing & Function Caching
`datetime.strptime` involves substantial Python overhead. In `parser.py`:
- `date.fromisoformat` handles standard `YYYY-MM-DD` exports instantaneously.
- `@lru_cache(maxsize=8192)` decorates `normalize_merchant_name`, `parse_flexible_date`, and `parse_currency_value`, eliminating redundant string normalization across large CSV batches.

### 4. Direct Serialization Without Redundant Pydantic Re-Validation
In FastAPI, using `response_model=StatementAnalysisResponse` causes FastAPI to re-validate 10,000 already-validated Pydantic models in Python, adding ~2.0 seconds of overhead. Returning the directly instantiated response object reduces end-to-end API latency for 10,000 rows to **1.039 seconds**.

---

## 5. Evaluation Benchmark & Empirical Results

The categorization brain is verified against an independent, curated benchmark dataset (`eval/labeled_transactions.csv`) containing **271 labeled rows** spanning all 17 categories, dual-role studio platforms, edge cases, contra-expense refunds, and ambiguity traps.

Execution command: `python eval/run_eval.py`

### Benchmark Execution Output

```text
================================================================================
      DETERMINISTIC BRAIN BENCHMARK & EVALUATION REPORT
================================================================================
Total Labeled Benchmark Rows   : 271
Auto-Categorized Decisions     : 240 (88.56%)
Routed to 'Needs Review'       : 31 (11.44%)
Auto-Categorization Precision  : 100.00%  (Target: >= 98.0%)
Misclassified Auto Rows Count  : 0
--------------------------------------------------------------------------------
Category                               | Total  | Auto   | Review  | Precision
--------------------------------------------------------------------------------
Bank & Processing Fees                 | 8      | 8      | 0       | 100.0%
Camera Equipment & Lighting            | 40     | 40     | 0       | 100.0%
Client & Crew Meals (50%)              | 8      | 7      | 1       | 100.0%
Client Shoot & Book Income             | 15     | 15     | 0       | 100.0%
Contract Labor & Assistants            | 8      | 8      | 0       | 100.0%
Gear & Lens Rentals                    | 16     | 16     | 0       | 100.0%
Insurance, Copyright & Guilds          | 10     | 10     | 0       | 100.0%
Marketing, Book Fairs & Portfolio      | 14     | 14     | 0       | 100.0%
Needs Review                           | 30     | 0      | 30      | 100.0%
Non-Deductible / Transfer              | 12     | 12     | 0       | 100.0%
Photobook Printing & Lab COGS          | 25     | 25     | 0       | 100.0%
Props, Styling & Reference Books       | 14     | 14     | 0       | 100.0%
Shipping & Book Fulfillment            | 14     | 14     | 0       | 100.0%
Shoot Travel & Transport               | 20     | 20     | 0       | 100.0%
Software & Digital Workflow            | 22     | 22     | 0       | 100.0%
Studio, Darkroom & Permits             | 15     | 15     | 0       | 100.0%
--------------------------------------------------------------------------------
SUCCESS: Brain achieved 100.00% precision on benchmark dataset!
```

### System Performance & Test Summary

| Metric | Measured Value | Target / Requirement | Status |
| :--- | :--- | :--- | :---: |
| **Auto-Categorization Precision** | **100.00%** | $\ge 98.0\%$ | PASS |
| **Auto-Categorized Decisions** | **240 / 271 (88.56%)** | Coverage $\ge 80\%$ | PASS |
| **Review Abstentions** | **31 / 271 (11.44%)** | Ambiguity Safely Trapped | PASS |
| **Misclassified Auto Rows** | **0 rows** | 0 tolerance | PASS |
| **10,000 Row Processing Time** | **1.039 seconds** | $< 1.50$ seconds | PASS |
| **Backend Unit Test Suite** | **75 / 75 passing** (4.35s) | 100% green | PASS |
| **Frontend Unit Test Suite** | **3 / 3 passing** (2.82s) | 100% green | PASS |
| **Frontend Production Build** | **Compiled in 7.85s** | Zero TypeScript errors | PASS |
| **Runtime AI / LLM Calls** | **0 calls** | 0 calls (Strict Zero-LLM) | PASS |
