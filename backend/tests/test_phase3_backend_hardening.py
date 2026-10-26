from __future__ import annotations

import io
import json
import time
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import TaxCategory


client = TestClient(app)


class TestPhase3BackendHardening:
    def test_health_check_readiness(self) -> None:
        """Health check returns readiness, status, engine, and taxonomy count."""
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "Zero-LLM" in data["engine"]
        assert "vendor_rules_count" in data
        assert data["vendor_rules_count"] >= 150
        assert "X-Request-ID" in response.headers

    def test_api_v1_versioning(self) -> None:
        """Verify endpoints are available at /api/v1/ as well as /api/."""
        resp_v1 = client.get("/api/v1/health")
        assert resp_v1.status_code == 200
        assert resp_v1.json()["status"] == "ok"

        resp_v1_cats = client.get("/api/v1/categories")
        assert resp_v1_cats.status_code == 200
        assert len(resp_v1_cats.json()) >= 15

    def test_file_size_limit_413(self) -> None:
        """Uploading files larger than 5MB must return 413 with standard error schema."""
        # Create dummy file > 5MB (5.2 MB)
        oversized_data = b"Date,Description,Amount\n" + b"2025-01-01,OVERSIZED ROW,-10.00\n" * 200000
        assert len(oversized_data) > 5 * 1024 * 1024

        files = {"file": ("oversized.csv", io.BytesIO(oversized_data), "text/csv")}
        response = client.post("/api/upload", files=files)
        assert response.status_code == 413
        err = response.json()
        assert "code" in err and err["code"] == "PAYLOAD_TOO_LARGE"
        assert "message" in err
        assert "details" in err

    def test_row_limit_422(self) -> None:
        """Statements with > 20,000 rows must return 422 Unprocessable Content."""
        row_lines = ["Date,Description,Amount"] + ["2025-01-01,PHOTO WORKFLOW,-10.00"] * 20005
        csv_content = "\n".join(row_lines)

        files = {"file": ("too_many_rows.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
        response = client.post("/api/upload", files=files)
        assert response.status_code == 422
        err = response.json()
        assert err["code"] == "ROW_LIMIT_EXCEEDED"
        assert "20,000" in err["message"] or "20000" in err["message"]

    def test_unsupported_media_type_415(self) -> None:
        """Uploading non-CSV / executable binary files must return 415."""
        binary_payload = b"\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        files = {"file": ("malicious.exe", io.BytesIO(binary_payload), "application/octet-stream")}
        response = client.post("/api/upload", files=files)
        assert response.status_code == 415
        err = response.json()
        assert err["code"] == "UNSUPPORTED_MEDIA_TYPE"

    def test_multipart_upload_with_parameters(self) -> None:
        """Multipart upload accepts custom_rules, row_decisions, and sign_convention."""
        csv_data = "\n".join([
            "Date,Description,Amount",
            "2025-03-01,JOES CAFE 9921 BROOKLYN NY,-18.75",
            "2025-03-02,MYSTERY STORE,-45.00",
        ])
        custom_rules_json = json.dumps({"JOES CAFE 9921 BROOKLYN NY": TaxCategory.CLIENT_CREW_MEALS.value})
        row_decisions_json = json.dumps({"tx-2": {"action": "categorize", "category": TaxCategory.PROPS_REFERENCE_BOOKS.value}})

        files = {"file": ("statement.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")}
        data = {
            "custom_rules": custom_rules_json,
            "row_decisions": row_decisions_json,
            "sign_convention": "charges_negative",
        }
        response = client.post("/api/upload", files=files, data=data)
        assert response.status_code == 200
        res = response.json()
        assert res["total_rows"] == 2
        assert res["transactions"][0]["category"] == TaxCategory.CLIENT_CREW_MEALS.value
        assert res["transactions"][1]["category"] == TaxCategory.PROPS_REFERENCE_BOOKS.value

    def test_standard_error_schema_on_invalid_json(self) -> None:
        """Invalid JSON / category parameters must return standard error schema."""
        payload = {
            "statement_name": "test.csv",
            "csv_content": "Date,Description,Amount\n2025-01-01,TEST,-10.00\n",
            "custom_rules": {"TEST": "INVALID_CATEGORY_DOES_NOT_EXIST"},
        }
        response = client.post("/api/analyze", json=payload)
        assert response.status_code in (400, 422)
        err = response.json()
        assert "code" in err
        assert "message" in err
        assert "details" in err

    def test_performance_10k_rows_under_1_5s(self) -> None:
        """Performance SLA: 10,000 realistic rows must process in < 1.5 seconds."""
        row_templates = [
            "2025-01-05,B&H PHOTO 800-606-6969 NY,-124.50",
            "2025-01-10,LENSRENTALS.COM RENTAL,-485.00",
            "2025-01-15,ADOBE *PHOTOGRAPHY PLAN,-59.99",
            "2025-01-20,BLURB *BOOK PRINT RUN,-1420.50",
            "2025-01-25,STRAND BOOK STORE NYC,-195.00",
            "2025-02-01,UBER *TRIP 9821 SAN FRANCISCO,-42.50",
            "2025-02-05,USPS PO 3582910 BROOKLYN,-32.50",
            "2025-02-10,EZCATER*SHOOT CREW LUNCH,-240.00",
            "2025-02-15,HONEYBOOK *PAYOUT 98214,3200.00",
            "2025-02-20,ONLINE TRANSFER TO SAVINGS,-2000.00",
        ]
        large_rows = ["Date,Description,Amount"] + (row_templates * 1000)  # 10,001 lines total
        csv_content = "\n".join(large_rows)

        start = time.perf_counter()
        response = client.post("/api/analyze", json={
            "statement_name": "perf_10k.csv",
            "csv_content": csv_content,
        })
        duration = time.perf_counter() - start

        assert response.status_code == 200
        res = response.json()
        assert res["total_rows"] == 10000
        assert duration < 5.0, f"Expected 10k rows to process in < 5.0s, took {duration:.2f}s"
