from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional
import uuid

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from .brain import StatementCategorizerBrain
from .models import (
    BatchAnalyzeRequest,
    StatementAnalysisResponse,
    TaxCategory,
)
from .rules import MERCHANT_RULES, SCHEDULE_C_MAPPING
from .sample_data import SAMPLE_STATEMENTS

# Configure structured logging without PII
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("focal_folio.api")

MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5MB
MAX_TRANSACTION_ROWS = 20_000


class APIErrorResponse(BaseModel):
    code: str
    message: str
    details: Any = None


class APIHTTPException(HTTPException):
    def __init__(self, status_code: int, code: str, message: str, details: Any = None):
        super().__init__(status_code=status_code, detail=message)
        self.code = code
        self.message = message
        self.details = details


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

# CORS setup from environment
cors_origins_env = os.getenv("CORS_ORIGINS", "")
if cors_origins_env.strip():
    allowed_origins = [o.strip() for o in cors_origins_env.split(",") if o.strip()]
else:
    allowed_origins = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "*",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_and_logging_middleware(request: Request, call_next):
    req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    start_time = time.perf_counter()

    response = await call_next(request)

    duration_ms = (time.perf_counter() - start_time) * 1000
    response.headers["X-Request-ID"] = req_id

    # Structured log without PII (omits row descriptions, amounts, account numbers)
    logger.info(
        json.dumps({
            "request_id": req_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round(duration_ms, 2),
        })
    )
    return response


# Global Exception Handlers returning standard error schema
@app.exception_handler(APIHTTPException)
async def api_http_exception_handler(request: Request, exc: APIHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
        },
    )


@app.exception_handler(HTTPException)
async def generic_http_exception_handler(request: Request, exc: HTTPException):
    code = "HTTP_ERROR"
    if exc.status_code == 413:
        code = "PAYLOAD_TOO_LARGE"
    elif exc.status_code == 415:
        code = "UNSUPPORTED_MEDIA_TYPE"
    elif exc.status_code == 422:
        code = "UNPROCESSABLE_ENTITY"
    elif exc.status_code == 400:
        code = "BAD_REQUEST"

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": code,
            "message": str(exc.detail),
            "details": None,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "code": "VALIDATION_ERROR",
            "message": "Invalid request parameters or payload format.",
            "details": exc.errors(),
        },
    )


def _validate_csv_content(csv_text: str) -> None:
    """Enforces row limits and basic text validity."""
    line_count = csv_text.count("\n")
    if line_count > MAX_TRANSACTION_ROWS:
        raise APIHTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="ROW_LIMIT_EXCEEDED",
            message=f"Statement exceeds maximum allowed row limit of {MAX_TRANSACTION_ROWS:,} rows (found ~{line_count:,} lines).",
            details={"max_rows": MAX_TRANSACTION_ROWS, "received_lines": line_count},
        )


def _parse_custom_rules_dict(rules_raw: Optional[str | Dict[str, Any]]) -> Dict[str, TaxCategory]:
    if not rules_raw:
        return {}
    if isinstance(rules_raw, str):
        try:
            parsed = json.loads(rules_raw)
        except json.JSONDecodeError as exc:
            raise APIHTTPException(
                status_code=400,
                code="INVALID_JSON",
                message="custom_rules must be valid JSON.",
                details=str(exc),
            )
    else:
        parsed = rules_raw

    custom_map: Dict[str, TaxCategory] = {}
    for merchant, cat_str in parsed.items():
        try:
            custom_map[merchant] = TaxCategory(cat_str)
        except ValueError as exc:
            raise APIHTTPException(
                status_code=400,
                code="INVALID_CATEGORY",
                message=f"Invalid TaxCategory '{cat_str}' specified for merchant '{merchant}'.",
                details={"merchant": merchant, "invalid_category": cat_str},
            ) from exc
    return custom_map


def _parse_row_decisions_dict(decisions_raw: Optional[str | Dict[str, Any]]) -> Dict[str, Any]:
    if not decisions_raw:
        return {}
    if isinstance(decisions_raw, str):
        try:
            return json.loads(decisions_raw)
        except json.JSONDecodeError as exc:
            raise APIHTTPException(
                status_code=400,
                code="INVALID_JSON",
                message="row_decisions must be valid JSON.",
                details=str(exc),
            )
    return decisions_raw


# ---------------------------------------------------------------------------
# API Route Handlers (Top-level for testing and OpenAPI docs)
# ---------------------------------------------------------------------------
def health_check() -> Dict[str, Any]:
    return {
        "status": "ok",
        "ready": True,
        "version": "1.0.0",
        "engine": "Deterministic Rule & Heuristic Brain v1.0 (Zero-LLM)",
        "vendor_rules_count": len(MERCHANT_RULES),
    }


def list_categories() -> List[Dict[str, object]]:
    return [
        {
            "category": cat.value,
            "schedule_c_line": line,
            "deductible_rate": rate,
        }
        for cat, (line, rate) in SCHEDULE_C_MAPPING.items()
    ]


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


def analyze_statement_payload(payload: BatchAnalyzeRequest) -> StatementAnalysisResponse:
    _validate_csv_content(payload.csv_content)
    custom_map = _parse_custom_rules_dict(payload.custom_rules)
    row_decisions = _parse_row_decisions_dict(payload.row_decisions)

    brain = StatementCategorizerBrain(
        custom_rules=custom_map,
        row_decisions=row_decisions,
    )
    return brain.analyze_statement(
        csv_content=payload.csv_content,
        statement_name=payload.statement_name,
        sign_convention=payload.sign_convention,
    )


async def upload_statement_file(
    file: UploadFile = File(...),
    custom_rules: Optional[str] = Form(None),
    row_decisions: Optional[str] = Form(None),
    sign_convention: str = Form("auto"),
) -> StatementAnalysisResponse:
    # Check filename extension
    filename = file.filename or "uploaded_statement.csv"
    lower_name = filename.lower()
    if any(lower_name.endswith(ext) for ext in [".exe", ".bin", ".elf", ".sh", ".bat", ".dll", ".so"]):
        raise APIHTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            code="UNSUPPORTED_MEDIA_TYPE",
            message=f"File '{filename}' has an unsupported media type or binary extension. Please upload a valid CSV statement.",
            details={"filename": filename},
        )

    raw_bytes = await file.read()

    # Enforce max file size (5MB)
    if len(raw_bytes) > MAX_FILE_SIZE_BYTES:
        raise APIHTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            code="PAYLOAD_TOO_LARGE",
            message=f"Uploaded file size ({len(raw_bytes) / 1024 / 1024:.2f} MB) exceeds maximum allowed limit of {MAX_FILE_SIZE_BYTES / 1024 / 1024:.0f} MB.",
            details={"file_size_bytes": len(raw_bytes), "max_size_bytes": MAX_FILE_SIZE_BYTES},
        )

    # Check for binary headers (ELF, Windows PE, etc.)
    if raw_bytes.startswith(b"\x7fELF") or raw_bytes.startswith(b"MZ"):
        raise APIHTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            code="UNSUPPORTED_MEDIA_TYPE",
            message=f"Uploaded file '{filename}' contains executable or binary content. Only plain text CSV statements are supported.",
            details={"filename": filename},
        )

    try:
        csv_text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            csv_text = raw_bytes.decode("latin-1")
        except Exception as exc:
            raise APIHTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                code="UNSUPPORTED_MEDIA_TYPE",
                message="Could not decode statement file as UTF-8 or Latin-1 text.",
                details=str(exc),
            )

    _validate_csv_content(csv_text)
    custom_map = _parse_custom_rules_dict(custom_rules)
    row_decisions_map = _parse_row_decisions_dict(row_decisions)

    brain = StatementCategorizerBrain(
        custom_rules=custom_map,
        row_decisions=row_decisions_map,
    )
    return brain.analyze_statement(
        csv_content=csv_text,
        statement_name=filename,
        sign_convention=sign_convention,
    )


# Register routes for both /api and /api/v1
for prefix in ("/api", "/api/v1"):
    app.add_api_route(f"{prefix}/health", health_check, methods=["GET"])
    app.add_api_route(f"{prefix}/categories", list_categories, methods=["GET"])
    app.add_api_route(f"{prefix}/presets", list_presets, methods=["GET"])
    app.add_api_route(
        f"{prefix}/analyze",
        analyze_statement_payload,
        methods=["POST"],
        response_model=StatementAnalysisResponse,
    )
    app.add_api_route(
        f"{prefix}/upload",
        upload_statement_file,
        methods=["POST"],
        response_model=StatementAnalysisResponse,
    )
