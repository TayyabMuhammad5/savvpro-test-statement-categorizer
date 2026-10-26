# Focal & Folio — Photography & Photobook Tax Statement Categorizer

A production-ready bank and credit card statement categorizer built for **Independent Editorial Photographers & Fine-Art Photobook Publishers** preparing their IRS **Schedule C (Form 1040)** tax filing.

> **Zero-LLM Guarantee ("The One Big Rule"):** Every categorization decision, refund reconciliation, duplicate check, and confidence score in `backend/app/brain.py` and `backend/app/rules.py` is **100% deterministic Python code** (compiled word-boundary regexes, multi-stage domain heuristics, and accounting state machines). No external AI/LLM APIs (OpenAI, Claude, Gemini, etc.) are called or required at runtime.

---

## 1. Quick Start & Setup

### Prerequisites
- **Python 3.10+**
- **Node.js 18+** and `npm`

### Step 1: Start the Python Backend (FastAPI)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Start the FastAPI server on http://localhost:8000
uvicorn app.main:app --reload --port 8000
```

- **Interactive Swagger API Docs:** `http://localhost:8000/docs`
- **Health Check:** `http://localhost:8000/api/health`

### Step 2: Start the React Frontend (Vite + TypeScript + Tailwind CSS)

Open a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` in your browser. Vite automatically proxies `/api/*` requests to `http://localhost:8000`.

### Step 3: Run the Automated Test Suite

The backend includes **17 unit, parser, and API integration tests** covering photography & photobook categories, contra-expense refund accounting, internal transfer filtering, Section 179 capital asset thresholds, 50% meal deductions, Amex sign inversion, and ambiguity traps:

```bash
cd backend
# Run via pytest
PYTHONPATH=. pytest -v

# Or run with zero external test runner dependencies via unittest
python3 run_tests.py
```

---

## 2. Project Structure

```text
savvpro-test-statement-categorizer/
├── README.md                  # Setup, usage, and architecture guide
├── DESIGN.md                  # Customer persona, tax rules, and Brain decision pipeline
├── AI_USAGE.md                # AI tools used, bugs caught & fixed, and token usage logs
├── .gitignore                 # Excludes virtualenvs, node_modules, .env, and secrets
├── sample_statements/         # Synthetic messy CSV statements (strictly fake data)
│   ├── chase_studio_credit_card_2025.csv
│   ├── amex_editorial_shoot_2025.csv
│   └── mercury_studio_checking_2025.csv
├── backend/                   # Python FastAPI Backend + Deterministic Brain
│   ├── requirements.txt
│   ├── run_tests.py
│   ├── app/
│   │   ├── __init__.py
│   │   ├── models.py          # Pydantic schemas, TaxCategory & TaxFlag enums
│   │   ├── rules.py           # Compiled regex rules, Schedule C lines & ambiguity traps
│   │   ├── parser.py          # Multi-bank CSV parser (Chase, Amex, Mercury split columns)
│   │   ├── brain.py           # 9-stage deterministic categorization & confidence engine
│   │   ├── sample_data.py     # Built-in synthetic studio statements
│   │   └── main.py            # FastAPI endpoints (/api/analyze, /api/upload, /api/presets)
│   └── tests/
│       ├── test_brain.py      # Unit tests for rules, refunds, transfers & edge cases
│       ├── test_parser.py     # Unit tests for CSV schemas, preambles & currency formats
│       └── test_api.py        # Integration tests for API endpoints & learned rules
└── frontend/                  # React 18 + TypeScript + Vite + Tailwind CSS UI
    ├── package.json
    ├── vite.config.ts
    ├── tsconfig.json
    └── src/
        ├── types.ts
        ├── api.ts
        ├── App.tsx            # Upload, review queue, Brain inspector, Schedule C totals
        └── main.tsx
```

---

## 3. Testing with Included Messy Sample Statements

You can switch between three synthetic statements in the UI (or upload files from `sample_statements/`):

1. **`chase_studio_credit_card_2025.csv` (Single-Column Signed Format)**
   - Tests Section 179 flagging on a `$3,299.00` B&H Photo medium-format lens & strobe purchase, a `$485.00` LensRentals pending hold alongside the posted charge, a `+$150.00` LensRentals security deposit return, a `+$180.00` Blurb book-printing defect credit, Capture One foreign transaction fees, Strand Book Store monograph research, and `Needs Review` routing for `JOES CAFE 9921`, `AMAZON.COM*MKTPL`, `TARGET`, and `VENMO *MARCUS VANCE`.
2. **`amex_editorial_shoot_2025.csv` (Positive-Charge Format + Metadata Preamble)**
   - Tests skipping 2 bank header preamble rows, auto-inverting Amex's positive charge sign convention, detecting a duplicate `$284.00` Indie Film Lab batch row, categorizing LA Art Book Fair exhibitor booths, IngramSpark distribution, Bowker ISBN blocks, and Adorama flash return credits (`-$79.00` credit on card).
3. **`mercury_studio_checking_2025.csv` (Split Debit/Credit Columns Format)**
   - Tests separate `Debit` and `Credit` columns, distinguishing HoneyBook client shoot retainers (`+$4,850.00`), Pixieset print store payouts (`+$1,640.00`), and Blurb author royalties (`+$612.50`) from a `+$124.00` B&H Photo sales-tax overpayment refund, while isolating `$2,000.00` transfers to savings and `$3,500.00` owner draws.
