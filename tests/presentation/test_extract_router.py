from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from presentation.main import app

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "application" / "fixtures"


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_extract_returns_content_and_page_count_for_valid_pdf(client):
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
def test_extract_returns_400_for_corrupt_or_non_pdf_file(invalid_bytes, client):
    response = client.post(
        "/extract",
        files={"file": ("invalid.pdf", invalid_bytes, "application/pdf")},
    )

    assert response.status_code == 400


def test_extract_returns_422_when_file_is_missing(client):
    response = client.post("/extract")

    assert response.status_code == 422


def test_extract_returns_415_when_mime_is_not_pdf(client):
    pdf_bytes = (FIXTURES_DIR / "hello.pdf").read_bytes()

    response = client.post(
        "/extract",
        files={"file": ("hello.pdf", pdf_bytes, "text/plain")},
    )

    assert response.status_code == 415


def test_extract_returns_413_when_file_exceeds_max_size(client):
    from application.config import UploadConfig
    from presentation.routers.extract import get_upload_config

    app.dependency_overrides[get_upload_config] = lambda: UploadConfig(max_upload_bytes=10)
    try:
        pdf_bytes = (FIXTURES_DIR / "hello.pdf").read_bytes()

        response = client.post(
            "/extract",
            files={"file": ("hello.pdf", pdf_bytes, "application/pdf")},
        )

        assert response.status_code == 413
    finally:
        app.dependency_overrides.clear()
