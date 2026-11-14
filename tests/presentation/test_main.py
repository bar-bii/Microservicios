import multiprocessing
from pathlib import Path

from fastapi.testclient import TestClient

from presentation.access_log import AccessLogMiddleware
from presentation.main import app

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "application" / "fixtures"


def test_main_installs_access_log_middleware():
    assert any(middleware.cls is AccessLogMiddleware for middleware in app.user_middleware)


def test_app_extracts_in_worker_processes_when_configured(monkeypatch):
    monkeypatch.setenv("EXTRACTION_EXECUTOR", "process")
    pdf_bytes = (FIXTURES_DIR / "hello.pdf").read_bytes()

    with TestClient(app) as client:
        response = client.post(
            "/extract",
            files={"file": ("hello.pdf", pdf_bytes, "application/pdf")},
        )

        assert response.status_code == 200
        assert response.json() == {"content": "Hello PDF", "page_count": 1}
        assert multiprocessing.active_children()

    assert not multiprocessing.active_children()
