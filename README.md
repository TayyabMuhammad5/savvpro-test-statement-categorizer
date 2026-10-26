# Focal & Folio — Photography & Photobook Schedule C Statement Categorizer

[![CI Suite](https://github.com/TayyabMuhammad5/savvpro-test-statement-categorizer/actions/workflows/ci.yml/badge.svg)](https://github.com/TayyabMuhammad5/savvpro-test-statement-categorizer/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)
![React](https://img.shields.io/badge/react-18.2-61dafb.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-1.0.0-009688.svg)
![Zero-LLM](https://img.shields.io/badge/engine-100%25%20Deterministic%20Zero--LLM-emerald.svg)

A production-grade, hardened bank and credit card statement categorizer built for **Independent Editorial Photographers & Fine-Art Photobook Publishers** preparing their IRS **Schedule C (Form 1040)** tax return.

> **The One Big Rule (Zero-LLM Guarantee):**
> Every categorization decision, contra-expense refund reconciliation, transfer detection, and confidence calculation is **100% deterministic code** (`backend/app/brain.py`, `backend/app/rules/`). Absolutely zero LLM or external AI APIs are called at runtime. No API keys or tokens required. No personal or real bank data in the repository (fake data only). When uncertain, the engine routes to **Needs Review** with plain-English reasons.

---

## Key Capabilities

1. **Schedule C Domain Brain**:
   - 308 photography/publishing vendor rules externalized in validated YAML (`merchants.yaml`, `transfers.yaml`, `keywords.yaml`, `traps.yaml`).
   - Contract Labor (Line 11) with Form 1099-NEC tax tracking notes.
   - Equipment purchases $\ge \$2,500$ automatically flagged as Section 179 / De Minimis Safe Harbor capital assets (Line 13).
   - 50% statutory deduction limit on client and crew on-set meals (Line 24b).
   - Studio locations, darkrooms, and commercial film permits mapped to Line 20b / Line 23.
2. **Accounting Integrity**:
   - **Contra-Expense Refunds**: Vendor credits and deposit returns reduce corresponding expense lines (e.g. Blurb defect credit reduces Line 4 printing COGS, LensRentals deposit returns reduce Line 20a rentals) and **never** inflate gross studio revenue.
   - **Internal Transfer Pairing**: $O(N)$ amount-bucket cross-row pairing detects matching deposits and withdrawals within 3 days.
   - **Zero-Guessing Sign Inversion**: Replaced majority-vote sign inversion with explicit evidence matching (Charge column headers, Type column values, split Debit/Credit).
3. **Multi-Signal Evidence Scoring & Fuzzy Review Routing**:
   - Deterministic Levenshtein edit distance and token similarity strictly capped at confidence 0.62 ($\le 0.65$), safely routing misspelled merchants to Needs Review with suggestions.
   - Top-2 alternative categories evaluated with plain-English *"why not"* explanations.
   - Sniffs bank category metadata (`Professional Services`, `Merchandise`) and detects recurring monthly subscription cadence.
4. **Hardened API**:
   - 5MB maximum file size limit (`413 Content Too Large`).
   - 20,000 maximum row limit (`422 Unprocessable Content`).
   - Binary/executable payload rejection (`415 Unsupported Media Type`).
   - Standardized error schema: `{ code, message, details }`.
   - Structured JSON logging without PII and `X-Request-ID` tracing middleware.
   - High-throughput performance: 10,000 realistic statement rows process in **< 1.1 seconds**.

---

## 1. Quick Start

### Option A: Local Development

#### Prerequisites
- **Python 3.11+**
- **Node.js 20+** and `npm`

#### 1. Backend Setup
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

# Run the FastAPI server on http://localhost:8000
uvicorn app.main:app --reload --port 8000
```
- Interactive Swagger UI: `http://localhost:8000/docs`
- Healthcheck: `http://localhost:8000/api/health`

#### 2. Frontend Setup
Open a second terminal:
```bash
cd frontend
npm install
npm run dev
```
Open `http://localhost:5173` in your browser. Vite automatically proxies `/api/*` to the FastAPI backend.

---

### Option B: Docker Compose

Run the entire containerized stack with a single command:
```bash
docker compose up --build -d
```
- Frontend UI: `http://localhost:5173`
- Backend API: `http://localhost:8000/docs`

To stop:
```bash
docker compose down
```

---

## 2. API Usage & cURL Examples

### Health Check (`GET /api/health` or `GET /api/v1/health`)

```bash
curl -s http://localhost:8000/api/health
```

**Response (`200 OK`):**
```json
{
  "status": "ok",
  "ready": true,
  "version": "1.0.0",
  "engine": "Deterministic Rule & Heuristic Brain v1.0 (Zero-LLM)",
  "vendor_rules_count": 308
}
```

### Analyze Statement Payload (`POST /api/analyze`)

```bash
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "statement_name": "chase_sample.csv",
    "csv_content": "Date,Description,Amount\n2025-03-02,B&H PHOTO 800-606-6969 NY,-3299.00\n2025-03-04,LENSRENTALS.COM RENTAL,-485.00\n2025-03-08,LENSRENTALS.COM DEPOSIT RETURN,150.00\n2025-03-10,BLURB *BOOK PRINT RUN,-1420.50\n2025-03-12,BLURB *DEFECT CREDIT,180.00\n2025-03-21,JOES CAFE 9921 BROOKLYN NY,-18.75\n",
    "custom_rules": {
      "JOES CAFE 9921 BROOKLYN NY": "Client & Crew Meals (50%)"
    }
  }'
```

**Response (`200 OK`):**
```json
{
  "statement_name": "chase_sample.csv",
  "detected_bank_format": "Single-Column Signed (Chase / Checking Style)",
  "sign_convention": "auto",
  "total_rows": 6,
  "auto_categorized_count": 6,
  "needs_review_count": 0,
  "duplicate_or_pending_count": 0,
  "transfer_count": 0,
  "refund_count": 2,
  "gross_income": 0.0,
  "gross_expenses": 5223.25,
  "total_refund_offsets": 330.0,
  "net_expenses": 4893.25,
  "estimated_deductible_total": 4883.88,
  "amount_in_review": 0.0,
  "provisional": false,
  "tax_disclaimer": "This report is a deterministic categorization assistant based on IRS Schedule C guidelines for photography studios and is not tax advice or legal advice. Consult a certified CPA or tax professional before filing."
}
```

### Multipart File Upload (`POST /api/upload`)

```bash
curl -X POST http://localhost:8000/api/upload \
  -F "file=@sample_statements/chase_studio_credit_card_2025.csv" \
  -F "sign_convention=auto"
```

### File Size Limit Rejection (`413 Content Too Large`)

```bash
# Uploading files > 5MB triggers standard error response:
{
  "code": "PAYLOAD_TOO_LARGE",
  "message": "Uploaded file size (6.10 MB) exceeds maximum allowed limit of 5 MB.",
  "details": { "file_size_bytes": 6400024, "max_size_bytes": 5242880 }
}
```

---

## 3. Automated Test Suite & Benchmark Evaluation

### Run Backend Unit & Integration Tests (75 tests)
```bash
cd backend
python -m pytest -v
```

### Run Frontend Unit Tests (Vitest)
```bash
cd frontend
npm test
```

### Run 271-Row Benchmark Evaluation
```bash
python eval/run_eval.py
```

**Real Execution Output:**
```text
================================================================================
      DETERMINISTIC BRAIN BENCHMARK & EVALUATION REPORT
================================================================================
Total Labeled Benchmark Rows   : 271
Auto-Categorized Decisions     : 240 (88.6%)
Routed to 'Needs Review'       : 31 (11.4%)
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

---

## 4. Curated Messy Sample Statements

Located under `sample_statements/` and accessible from the frontend preset selector:

1. **`chase_studio_credit_card_2025.csv` (Signed Single-Column)**
   - 22 rows: B&H Section 179 lens ($3,299), LensRentals pending hold + security deposit refund, Blurb book printing + defect credit, Capture One + FX fee, PeerSpace loft, EzCater crew lunch, Strand Books, review traps (Amazon, Target, Venmo, Joe's Cafe), and Autopay.
2. **`amex_editorial_shoot_2025.csv` (Positive-Charge + Metadata Preamble)**
   - 14 rows: 2 metadata preamble lines, inverted positive charges, Delta flight, Ace Hotel, LA Art Book Fair booth, Indie Film Lab duplicate row, IngramSpark, Bowker ISBNs, Adorama return credit, Blue Bottle & Apple.com traps.
3. **`mercury_studio_checking_2025.csv` (Split Debit/Credit Columns)**
   - 13 rows: HoneyBook client shoot retainers ($4,850), Pixieset & Blurb book royalties, Edition One Books bindery, Brooklyn Darkroom, B&H sales tax refund credit, Owner Draw, Transfer to Savings, unverified Check Deposit & ATM traps.
4. **`european_semicolon_decimal_comma.csv` (European Semicolon & Decimal Comma)**
   - 10 rows: Semicolon delimiter (`;`), decimal commas (`1.420,50 €`), `DD/MM/YYYY` dates: Hahnemühle FineArt paper, Leica Store Berlin, WhiteWall exhibition prints, Blurb EU defect refund, TGV travel, and SEPA client retainer.
5. **`income_heavy_commercial_checking.csv` (Income-Heavy Checking)**
   - 12 rows: High studio client deposits ($6,500 HoneyBook, $4,200 Vogue wire), wire fees, quarterly tax transfer, and owner distribution, confirming non-inversion without explicit Charge columns.
6. **`quoted_multiline_preamble.csv` (Quoted Multiline & Preamble Headers)**
   - 9 rows: Bank metadata preamble headers, multi-line quoted descriptions and itemized memos: Sony Alpha a7R V body, Hasselblad rental, Blurb photobook run, Indie Film Lab, and PeerSpace.

---

## 5. Repository Architecture

```text
savvpro-test-statement-categorizer/
├── README.md                  # Comprehensive setup, API, and architectural guide
├── DESIGN.md                  # Complete architectural walkthrough and benchmark results
├── AI_USAGE.md                # AI pair-programming record and bug resolution log
├── Makefile                   # Standard developer workflow targets
├── docker-compose.yml         # Containerized production stack
├── .github/workflows/ci.yml   # Automated CI testing and evaluation workflow
├── sample_statements/         # 6 curated messy sample statements
├── eval/
│   ├── labeled_transactions.csv  # 271 human-labeled ground truth transactions
│   └── run_eval.py               # Deterministic precision and routing evaluator
├── backend/
│   ├── Dockerfile             # Python 3.11-slim container with non-root user
│   ├── pyproject.toml         # Ruff, mypy strict, and pytest configuration
│   ├── requirements.txt       # Pinned production runtime dependencies
│   ├── requirements-dev.txt   # Test, lint, and coverage tools
│   ├── app/
│   │   ├── models.py          # Pydantic schemas, TaxCategory & TaxFlag enums
│   │   ├── parser.py          # Multi-bank CSV parser with delimiter sniffing & caching
│   │   ├── brain.py           # 9-stage deterministic categorization engine
│   │   ├── sample_data.py     # Built-in synthetic statements and preset registry
│   │   ├── main.py            # FastAPI API endpoints, middleware, and error schemas
│   │   └── rules/             # Externalized YAML rules package
│   │       ├── loader.py      # Rule validator and Pydantic loader
│   │       ├── schema.py      # Rule YAML Pydantic models
│   │       ├── merchants.yaml # 308 domain merchant regex rules with positive/negative tests
│   │       ├── transfers.yaml # Internal transfer and autopay rules
│   │       ├── keywords.yaml  # Contextual token keyword heuristics
│   │       └── traps.yaml     # Ambiguity traps routing opaque vendors to review
│   └── tests/                 # 75 unit, regression, hardening, and golden-file tests
└── frontend/
    ├── Dockerfile             # Multi-stage Vite build + Nginx Alpine container
    ├── nginx.conf             # Nginx reverse proxy configuration
    ├── package.json           # React 18, Vite 5, Tailwind CSS, Vitest
    ├── tailwind.config.js     # Accessible color tokens and typography families
    └── src/
        ├── types.ts           # TypeScript interfaces matching backend models
        ├── api.ts             # API client with typed error handling & multipart upload
        ├── App.tsx            # Full UI (review queue, decision drawer, Schedule C rollups)
        └── __tests__/         # Vitest unit tests (formula injection defense, categories)
```

---

## 6. License & Disclaimer

This project is licensed under the MIT License.

**Tax Disclaimer:**
*Tax classifications, category rollups, and Schedule C summaries are generated deterministically for bookkeeping organization and do not constitute professional tax, accounting, or legal advice. Consult a certified public accountant (CPA) or tax attorney for official Schedule C tax filings.*
