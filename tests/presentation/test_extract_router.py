from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from presentation.main import app

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "application" / "fixtures"

client = TestClient(app)


def test_extract_returns_content_and_page_count_for_valid_pdf():
    pdf_bytes = (FIXTURES_DIR / "hello.pdf").read_bytes()

    response = client.post(
        "/extract",
        files={"file": ("hello.pdf", pdf_bytes, "application/pdf")},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"content": "Hello PDF", "page_count": 1}


@pytest.mark.parametrize(
    "invalid_bytes",
    [
        b"this is plain text, not a pdf",
        b"%PDF-1.7\ncorrupt body",
    ],
)
def test_extract_returns_400_for_corrupt_or_non_pdf_file(invalid_bytes):
    response = client.post(
        "/extract",
        files={"file": ("invalid.pdf", invalid_bytes, "application/pdf")},
    )

    assert response.status_code == 400


def test_extract_returns_422_when_file_is_missing():
    response = client.post("/extract")

    assert response.status_code == 422
