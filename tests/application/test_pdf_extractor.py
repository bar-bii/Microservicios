from pathlib import Path

import pytest

from application.pdf_extractor import InvalidPDFException, PypdfPDFExtractor

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_extract_text_from_valid_pdf():
    pdf_bytes = (FIXTURES_DIR / "hello.pdf").read_bytes()

    result = PypdfPDFExtractor().extract(pdf_bytes)

    assert result.content == "Hello PDF"
    assert result.page_count == 1


@pytest.mark.parametrize(
    "invalid_bytes",
    [
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",
        b"this is plain text, not a pdf",
    ],
)
def test_reject_invalid_pdf_signature(invalid_bytes):
    with pytest.raises(InvalidPDFException):
        PypdfPDFExtractor().extract(invalid_bytes)


def test_reject_corrupt_pdf_with_valid_signature():
    with pytest.raises(InvalidPDFException):
        PypdfPDFExtractor().extract(b"%PDF-1.7\ncorrupt body")
