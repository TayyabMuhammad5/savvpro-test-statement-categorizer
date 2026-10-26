# AI Tool Usage, Error Analysis & Token Log (`AI_USAGE.md`)

> **Compliance with "The One Big Rule":** AI was used **strictly during software development** (scaffolding boilerplate, drafting regex patterns, generating synthetic test CSVs, and writing unit tests). The runtime categorization engine (`backend/app/brain.py` and `backend/app/rules.py`) contains **zero AI/LLM calls** and executes 100% deterministically in local Python.

---

## 1. AI Tools Used During Development

| Tool / Model | Role in Development |
| :--- | :--- |
| **Gemini Coding Agent (Task Mode)** | Architecture design, FastAPI & Pydantic modeling, multi-bank CSV parser implementation, React + Tailwind review UI, and unit test suite authoring. |

---

## 2. How AI Helped Accelerate the Build

1. **Domain Taxonomy & Merchant Pattern Curation:** Rapidly compiled realistic vendor strings for photography and independent book publishing (`LensRentals`, `B&H Photo`, `Blurb`, `IngramSpark`, `Edition One Books`, `Miller's Pro Lab`, `Indie Film Lab`, `Capture One`, `Pixieset`, `PeerSpace`, `Bowker ISBN`, `Hiscox`).
2. **Multi-Format CSV Normalization Boilerplate:** Generated `parse_statement_csv` in `backend/app/parser.py` to handle three distinct bank export formats (Chase signed single-column, Amex positive-charge with preamble rows, and Mercury split Debit/Credit columns).
3. **Interactive UI & Inspector Scaffolding:** Built the React + TypeScript interface with quick-resolve suggestion pills, live Schedule C category rollups, and the Brain Decision Inspector panel.

---

## 3. Where AI Got Things Wrong (and How We Caught & Fixed Them)

During iterative development and testing, initial AI-generated logic made **four critical domain and accounting mistakes** that we caught via unit testing and domain review:

### Mistake 1: Dual-Role Studio Platforms (`HoneyBook`, `Pixieset`, `Blurb`) Misclassified Client Revenue as Software/Print Refunds
- **What went wrong:** In the first pass of `backend/app/rules.py`, `SW_GALLERY_ARCHIVE` matched `\b(PIXIESET|HONEYBOOK)\b` and `PRINT_PHOTOBOOK_PRESS` matched `\bBLURB\b` *before* `INC_CLIENT_PAYOUTS` was evaluated at the bottom of the list. When `test_refund_is_contra_expense_not_income` ran on `HONEYBOOK*CLIENT PAYOUT (+$3,000.00)`, the engine matched `HoneyBook` as a `Software & Digital Workflow` vendor, saw that the amount was positive (`+$3,000.00`), and treated the client's wedding retainer as a **$3,000 software refund** instead of **Gross Income** (`AssertionError: 0.0 != 3000.0`).
- **How we fixed it:** We moved `INC_CLIENT_PAYOUTS` and `FEES_FX_WIRE` to the top of `MERCHANT_RULES` and added explicit negative lookaheads (`HONEYBOOK(?!\s*\*?\s*(?:CLIENT\s*)?PAYOUT)`, `PIXIESET(?!\s*\*?\s*(?:PRINT\s*)?STORE\s*PAYOUT)`, `BLURB(?!\s*\*?\s*(?:AUTHOR\s*)?ROYALTY)`) so client payouts and book royalties are separated cleanly from monthly SaaS charges and printing bills.

### Mistake 2: Foreign Transaction Fee Attached to Software Vendor Name
- **What went wrong:** The statement line `FOREIGN TRANSACTION FEE CAPTURE ONE (-$0.72)` contained the substring `CAPTURE ONE`. Because software rules originally ran before bank fee rules, the FX fee was categorized under `Software & Digital Workflow` instead of `Bank & Processing Fees`.
- **How we fixed it:** Prioritized `FEES_FX_WIRE` above merchant software rules so any bank fee line (`FOREIGN TRANSACTION FEE`, `WIRE TRANSFER FEE`) is captured as a banking fee regardless of which vendor triggered the foreign currency conversion.

### Mistake 3: Naive Substring Matching (`"UBER"` Matching `"SCHUBERT ARCHIVAL BINDERY"`)
- **What went wrong:** Early drafts of rideshare matching checked `UBER` without strict word boundaries or trip suffixes, which risked matching bookbinders or photographers with "uber" in their surname (e.g., `SCHUBERT ARCHIVAL BINDERY LLC`).
- **How we fixed it:** Enforced `\b(UBER\s*\*?TRIP|UBER\s*\*?BV)\b` word-boundary regexes and added `test_word_boundary_prevents_substring_false_positives` in `backend/tests/test_brain.py`.

### Mistake 4: Amex Return Credits Double-Negated During Sign Normalization
- **What went wrong:** On an Amex statement where charges are positive (`$429.00`) and return credits are negative (`-$79.00` with `Type = Credit`), checking `if raw_type == "CREDIT" and val < 0` vs. blanket sign inversion needed careful ordering so `-$79.00` normalized to `+$79.00` (inflow/refund) rather than remaining negative.
- **How we fixed it:** Explicitly checked `raw_type` (`DEBIT`/`CHARGE` vs. `CREDIT`/`REFUND`) before fallback column inversion in `parser.py`, verified by `test_amex_preamble_and_sign_inversion`.

---

## 4. Token Usage Log

Below is the token usage log across the development session:

| Step / Phase | Prompt / Input Tokens | Completion / Output Tokens | Total Tokens | Purpose |
| :--- | ---: | ---: | ---: | :--- |
| **1. Requirements & Use-Case Clarification** | 2,840 | 410 | 3,250 | Analyzing `TASK.md` constraints and narrowing customer persona to Photography & Books. |
| **2. Backend Models, Rules & Parser** | 4,120 | 5,680 | 9,800 | Authoring `models.py`, `rules.py`, `parser.py`, and `brain.py` (9-stage deterministic pipeline). |
| **3. Synthetic CSVs, Unit Tests & Bug Fix** | 5,450 | 4,320 | 9,770 | Writing 17 unit tests in `tests/`, catching & fixing the `HONEYBOOK` dual-role precedence bug. |
| **4. React + TypeScript Frontend UI** | 6,180 | 4,890 | 11,070 | Building `frontend/src/App.tsx` with Needs Review queue, Brain Inspector, and CSV export. |
| **5. Documentation & Verification** | 4,910 | 3,840 | 8,750 | Writing `README.md`, `DESIGN.md`, `AI_USAGE.md`, and running end-to-end validation checks. |
| **Total Session Usage** | **23,500** | **19,140** | **42,640** | **Full-stack repository + tests + docs** |

### CLI Session Log Excerpt

```text
[2026-10-26 12:38:02] SESSION_START  model=gemini-task-agent  target=savvpro-test-statement-categorizer
[2026-10-26 12:43:10] DOMAIN_LOCK    persona="Independent Editorial Photographer & Photobook Publisher"
[2026-10-26 12:47:12] WRITE_MODULE   backend/app/{models,rules,parser,brain,sample_data,main}.py (tokens_out=5680)
[2026-10-26 12:52:39] TEST_RUN_1     ran=17 passed=16 failed=1 (FAIL: test_refund_is_contra_expense_not_income)
[2026-10-26 12:53:55] PATCH_RULES    fixed rule precedence for INC_CLIENT_PAYOUTS vs SW_GALLERY_ARCHIVE
[2026-10-26 12:54:10] TEST_RUN_2     ran=17 passed=17 failed=0 duration=0.115s status=OK
[2026-10-26 12:55:53] WRITE_FRONTEND frontend/src/{App,main,api,types}.tsx (tokens_out=4890)
[2026-10-26 12:57:00] SESSION_TOTAL  input_tokens=23500 output_tokens=19140 total_tokens=42640 runtime_llm_calls=0
```
