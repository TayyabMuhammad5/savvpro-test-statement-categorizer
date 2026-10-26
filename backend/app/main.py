from __future__ import annotations

from typing import Dict, List
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from .brain import StatementCategorizerBrain
from .models import (
    BatchAnalyzeRequest,
    StatementAnalysisResponse,
    TaxCategory,
)
from .rules import SCHEDULE_C_MAPPING
from .sample_data import SAMPLE_STATEMENTS

app = FastAPI(
    title="Focal & Folio — Statement Categorizer API",
    description=(
        "Deterministic, zero-LLM Schedule C statement categorizer for Independent "
        "Photographers & Photobook Publishers. Handles messy multi-bank CSVs, "
        "contra-expense refunds, Section 179 gear thresholds, 50% meal limits, "
        "duplicate holds, and explicit Needs Review routing."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health_check() -> Dict[str, str]:
    return {"status": "ok", "engine": "Deterministic Rule & Heuristic Brain v1.0 (Zero-LLM)"}


@app.get("/api/categories")
def list_categories() -> List[Dict[str, object]]:
    return [
        {
            "category": cat.value,
            "schedule_c_line": line,
            "deductible_rate": rate,
        }
        for cat, (line, rate) in SCHEDULE_C_MAPPING.items()
    ]


@app.get("/api/presets")
def list_presets() -> List[Dict[str, str]]:
    return [
        {
            "id": item["id"],
            "name": item["name"],
            "filename": item["filename"],
            "description": item["description"],
            "csv": item["csv"],
        }
        for item in SAMPLE_STATEMENTS.values()
    ]


@app.post("/api/analyze", response_model=StatementAnalysisResponse)
def analyze_statement_payload(payload: BatchAnalyzeRequest) -> StatementAnalysisResponse:
    custom_map: Dict[str, TaxCategory] = {}
    for merchant, cat_str in payload.custom_rules.items():
        try:
            custom_map[merchant] = TaxCategory(cat_str)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid category: {cat_str}") from exc

    brain = StatementCategorizerBrain(custom_rules=custom_map)
    return brain.analyze_statement(
        csv_content=payload.csv_content,
        statement_name=payload.statement_name,
    )


@app.post("/api/upload", response_model=StatementAnalysisResponse)
async def upload_statement_file(file: UploadFile = File(...)) -> StatementAnalysisResponse:
    raw_bytes = await file.read()
    try:
        csv_text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        csv_text = raw_bytes.decode("latin-1")

    brain = StatementCategorizerBrain()
    return brain.analyze_statement(
        csv_content=csv_text,
        statement_name=file.filename or "uploaded_statement.csv",
    )
