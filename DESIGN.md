# System Design & Tax Decision Architecture (`DESIGN.md`)

## 1. Customer Persona & Real-World Use Case

### Customer: Independent Editorial Photographer & Photobook Publisher
We designed **Focal & Folio** for a sole-proprietor photography & independent photobook studio (*"Aperture & Spine Studio"*) filing **IRS Form 1040 Schedule C**.

Unlike generic freelancers, a working photographer and photobook publisher has a complex financial footprint that mixes:
1. **High-Value Depreciable Camera & Lighting Hardware** (`B&H Photo`, `Adorama`, `Leica`, `Profoto`, `MPB.com`) subject to the **$2,500 IRS De Minimis Safe Harbor / Section 179 threshold**.
2. **Short-Term Shoot Equipment Rentals & Security Deposits** (`LensRentals.com`, `ShareGrid`, `BorrowLenses`), which frequently generate pre-authorization holds (`PENDING`) and partial security-deposit refunds days after a shoot.
3. **Photobook Printing, Bindery & Fine-Art Darkroom COGS** (`Blurb`, `Edition One Books`, `IngramSpark`, `Miller's Pro Lab`, `Indie Film Lab`, `Ilford`, `Moab Paper`), where defective print batches generate vendor credits that must offset **Cost of Goods Sold (Part III)** rather than inflating gross income.
4. **Dual-Role Studio Platforms** (`HoneyBook`, `Pixieset`, `Pic-Time`, `Blurb`): a monthly outflow (`-$38.00`) to `Pixieset` or `HoneyBook` is a **Software Subscription (Line 18)**, whereas an inflow (`+$1,640.00`) from `PIXIESET*PRINT STORE PAYOUT` or `BLURB*AUTHOR ROYALTY` is **Gross Business Revenue (Line 1)**.
5. **Reference Monographs, Props & Styling** (`Strand Book Store`, `Arcana Books on the Arts`, `Printed Matter`, `Dashwood Books`, `Savage Universal`).

### Schedule C Tax Category Taxonomy

| Category | IRS Schedule C Mapping | Deductible Rate | Treatment |
| :--- | :--- | :---: | :--- |
| **Gear & Lens Rentals** | Line 20a — Rent/Lease Equipment | 100% | Operating Expense |
| **Camera Equipment & Lighting** | Line 13 / Line 22 — Section 179 / Supplies | 100% | Expense (Flags $\ge\$2,500$ for Sec. 179) |
| **Photobook Printing & Lab COGS** | Part III Line 38 — Cost of Goods Sold | 100% | Cost of Goods Sold |
| **Software & Digital Workflow** | Line 18 — Office & Digital Subscriptions | 100% | Operating Expense |
| **Studio, Darkroom & Permits** | Line 20b — Rent/Lease Other Business Property | 100% | Operating Expense |
| **Shoot Travel & Transport** | Line 24a — Travel (Air, Hotel, Rideshare) | 100% | Operating Expense |
| **Shipping & Book Fulfillment** | Line 18 / COGS — Postage, Mailers & Couriers | 100% | Operating Expense |
| **Props, Styling & Reference Books** | Line 22 — Supplies & Monograph Research | 100% | Operating Expense |
| **Client & Crew Meals (50%)** | Line 24b — Deductible Meals | **50%** | 50% Statutory Cap Applied |
| **Marketing, Book Fairs & Portfolio** | Line 8 — Advertising & Exhibitor Booths | 100% | Operating Expense |
| **Insurance, Copyright & Guilds** | Line 15 / Line 17 — Insurance & Legal | 100% | Operating Expense |
| **Bank & Processing Fees** | Line 10 / Line 27a — FX & Wire Fees | 100% | Operating Expense |
| **Client Shoot & Book Income** | Part I Line 1 — Gross Receipts | N/A | Gross Taxable Revenue |
| **Non-Deductible / Transfer** | Excluded — Internal Transfers & Autopay | 0% | Excluded from P&L |
| **Personal / Non-Deductible** | Excluded — Personal Draw / Personal Spend | 0% | Excluded from P&L |
| **Needs Review** | Held — Requires User Confirmation | 0% | Held Until Reviewed |

---

## 2. How "The Brain" Makes Decisions (Zero-LLM Pipeline)

Every row uploaded to the system passes through a deterministic **9-stage decision pipeline** in `backend/app/brain.py`:

```text
Raw CSV Row
  │
  ├─► [Stage 0] Multi-Bank CSV Normalizer (parser.py)
  │     • Auto-detects Chase signed single-column, Amex positive-charge, or Mercury split Debit/Credit
  │     • Strips bank preambles, normalizes dates to ISO YYYY-MM-DD, and canonicalizes merchant names
  │
  ├─► [Stage 1] Pending Hold & Duplicate Row Guard
  │     • Flags rows with status/description matching PENDING / PRE-AUTH
  │     • Detects identical (Date, Normalized Merchant, Signed Amount) tuples to prevent double-counting
  │
  ├─► [Stage 2] Non-Expense Transfer & Autopay Filter
  │     • Catches AUTOMATIC PAYMENT, AUTOPAY, TRANSFER TO SAVINGS, OWNER DRAW, and IRS tax remittances
  │     • Marks as TransactionType.TRANSFER (0% deductible, excluded from revenue and expenses)
  │
  ├─► [Stage 3] User-Learned Merchant Overrides
  │     • Checks session/custom merchant rules confirmed by the user during review (Confidence = 0.99)
  │
  ├─► [Stage 4] Curated Domain Regex Dictionary
  │     • Evaluates dual-role income payouts (HONEYBOOK*PAYOUT, BLURB*ROYALTY) first
  │     • Evaluates 12 compiled word-boundary regex rule groups for photography & book publishing vendors
  │
  ├─► [Stage 5] Token Keyword Heuristics
  │     • Matches domain terms (MEDIUM FORMAT, BOOKBINDING, DARKROOM, CYCLORAMA, ARCHIVAL INK) at 0.78–0.82 confidence
  │
  ├─► [Stage 6] Ambiguity Guardrail Traps
  │     • Traps multi-purpose/opaque vendors (AMAZON, TARGET, APPLE.COM/BILL, VENMO, PAYPAL, JOES CAFE, ATM)
  │     • Caps confidence at <= 0.45 and populates 3–4 context-aware candidate categories
  │
  ├─► [Stage 7] Contra-Expense Refund Reconciler
  │     • Distinguishes true revenue from vendor refunds/deposit releases (+$150 LensRentals, +$180 Blurb credit)
  │     • Marks vendor inflows as TransactionType.REFUND so they subtract from category spend
  │
  ├─► [Stage 8] IRS Policy Annotator
  │     • Flags Camera Equipment >= $2,500 as SECTION_179_CANDIDATE
  │     • Applies 0.50 deductible multiplier to Client & Crew Meals
  │
  └─► [Stage 9] Confidence Gate (< 0.70 → Needs Review)
        • Any transaction with confidence < 0.70 is routed to Needs Review with a plain-English reason
```

---

## 3. Handling Messy Real-World Statements: 8 Edge Cases Solved

1. **Refunds & Security Deposit Releases Are Contra-Expenses, Not Income**
   - *What goes wrong:* A photographer rents a tilt-shift lens for `$485.00` and receives a `+$150.00` deposit return (`LENSRENTALS.COM DEPOSIT RETURN`), or receives a `+$180.00` print defect credit from `BLURB *DEFECT CREDIT`. Naive categorizers treat any positive number as "Income", causing the user to pay income and self-employment tax on their own refunded money.
   - *How our Brain solves it:* Stage 7 checks whether a positive inflow either contains refund indicators (`REFUND`, `RETURN`, `CREDIT`, `DEPOSIT RET`) or originates from a merchant belonging to `EXPENSE_ONLY_CATEGORIES`. It assigns `transaction_type = "refund"` and sets `deductible_impact = -abs_amount * deductible_rate`, reducing net spend in that expense bucket.

2. **Dual-Role Studio Platforms (SaaS Subscription Outflow vs. Client Store Inflow)**
   - *What goes wrong:* Photographers pay `Pixieset`, `HoneyBook`, and `Blurb` for software/printing (`-$38.00`), but also receive client retainers and book royalties from those exact same brands (`PIXIESET*PRINT STORE PAYOUT +$1,640.00`, `BLURB*AUTHOR ROYALTY +$612.50`).
   - *How our Brain solves it:* `INC_CLIENT_PAYOUTS` is evaluated at the top of Stage 4 with explicit payout/royalty patterns, and SaaS/Print rules use negative lookaheads (`HONEYBOOK(?!\s*\*?\s*(?:CLIENT\s*)?PAYOUT)`) so payouts are classified as Gross Income while monthly billing is classified as Software or Printing COGS.

3. **Inverted Sign Conventions Across Banks (Chase vs. Amex vs. Split Checking)**
   - *What goes wrong:* Chase exports charges as negative numbers (`-3299.00`) and credits as positive (`150.00`). American Express exports charges as positive numbers (`$429.00`) and return credits as negative (`-$79.00`), often preceded by 2 lines of account metadata. Commercial checking accounts (Mercury) use separate `Debit` and `Credit` columns.
   - *How our Brain solves it:* `parser.py` strips metadata preamble rows before the header, detects the column layout and sign polarity automatically, and normalizes every transaction to a single signed convention (`< 0` = outflow, `> 0` = inflow) before the Brain inspects it.

4. **Internal Transfers, Owner Draws & Credit Card Autopay**
   - *What goes wrong:* `ONLINE TRANSFER TO SAVINGS (-$2,000)`, `OWNER DRAW (-$3,500)`, and `AUTOMATIC PAYMENT - THANK YOU (+$4,500)` are often misclassified as expenses or revenue.
   - *How our Brain solves it:* Stage 2 isolates all internal account movements and credit card settlements into `Non-Deductible / Transfer` with `$0.00` impact on Schedule C income or deductions.

5. **Opaque Multi-Category Vendors (`AMAZON.COM*MKTPL`, `TARGET`, `APPLE.COM/BILL`, `VENMO`)**
   - *What goes wrong:* An Amazon order of `$142.65` could be gaffer tape and SD cards (`Camera Equipment`), rigid book mailers (`Shipping`), or personal household items. Guessing "Office Supplies" creates audit risk.
   - *How our Brain solves it:* Stage 6 (`AMBIGUITY_TRAPS`) caps confidence at `0.35–0.40` and forces the row into **Needs Review** with clickable quick-assign pills for the most likely studio categories.

6. **The Local Cafe Audit Trap (`JOES CAFE 9921`, `BLUE BOTTLE COFFEE`)**
   - *What goes wrong:* Solo coffee or lunch in a freelancer's home city is strictly non-deductible, whereas catering for a shoot crew (`EZCATER*SHOOT CREW LUNCH`) or a client book-pitch meal is 50% deductible.
   - *How our Brain solves it:* Explicit catering vendors match `MEALS_SHOOT_CATERING` (`91%` confidence, 50% deductible), while generic cafes and restaurants trigger `TRAP_LOCAL_CAFE_DINING` (`45%` confidence → **Needs Review**).

7. **Pending Holds & Duplicate Import Rows**
   - *What goes wrong:* Rental houses place a `PENDING` authorization hold alongside the final charge, or bank exports duplicate a same-day film lab charge (`INDIE FILM LAB $284.00` twice on `2025-04-05`).
   - *How our Brain solves it:* Stage 1 tracks `(date, normalized_merchant, amount)` signatures and `PENDING` status flags, isolating duplicates so they never double-count in tax totals.

8. **Substring False Positives (`"UBER"` inside `"SCHUBERT ARCHIVAL BINDERY"`)**
   - *What goes wrong:* Naive `if "UBER" in description:` logic classifies `SCHUBERT ARCHIVAL BINDERY` as a Rideshare/Travel expense.
   - *How our Brain solves it:* Every rule in `rules.py` uses strict word boundaries (`\bUBER\s*\*?TRIP\b`), verified by a dedicated regression test in `test_brain.py`.
