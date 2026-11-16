import io
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from reportlab.pdfgen import canvas

from application import pdf_extractor
from application.pdf_extractor import ExtractionResult, InvalidPDFError, PdfiumPDFExtractor

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def pdf_with_lines(*pages: tuple[str, ...]) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(595, 842))
    for lines in pages:
        for index, line in enumerate(lines):
            pdf.drawString(40, 800 - 20 * index, line)
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def wait_until(condition: Callable[[], bool], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            pytest.fail("condition was not met in time")
        time.sleep(0.001)


def test_extract_text_from_valid_pdf():
    pdf_bytes = (FIXTURES_DIR / "hello.pdf").read_bytes()

    result = PdfiumPDFExtractor().extract(pdf_bytes)

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
    with pytest.raises(InvalidPDFError):
        PdfiumPDFExtractor().extract(invalid_bytes)


def test_reject_corrupt_pdf_with_valid_signature():
    with pytest.raises(InvalidPDFError):
        PdfiumPDFExtractor().extract(b"%PDF-1.7\ncorrupt body")


def test_extract_text_from_multipage_pdf():
    pdf_bytes = (FIXTURES_DIR / "hello_two_pages.pdf").read_bytes()

    result = PdfiumPDFExtractor().extract(pdf_bytes)

    assert result.content == "Hello PDF\nHello PDF"
    assert result.page_count == 2


def test_lines_within_a_page_are_separated_by_a_line_feed():
    pdf_bytes = pdf_with_lines(("first line", "second line"))

    result = PdfiumPDFExtractor().extract(pdf_bytes)

    assert result.content == "first line\nsecond line"


def test_blank_pages_count_and_contribute_empty_text():
    pdf_bytes = pdf_with_lines(("first page",), (), ("third page",))

    result = PdfiumPDFExtractor().extract(pdf_bytes)

    assert result == ExtractionResult(content="first page\n\nthird page", page_count=3)


def test_extraction_waits_while_another_thread_holds_the_pdfium_lock():
    pdf_bytes = (FIXTURES_DIR / "hello.pdf").read_bytes()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with pdf_extractor.PDFIUM_LOCK:
            extraction = pool.submit(PdfiumPDFExtractor().extract, pdf_bytes)

            with pytest.raises(TimeoutError):
                extraction.result(timeout=0.2)

        assert extraction.result(timeout=5).content == "Hello PDF"


def test_concurrent_extractions_return_the_same_text():
    pdf_bytes = pdf_with_lines(*[(f"page {number}", "second line") for number in range(20)])
    extractor = PdfiumPDFExtractor()
    expected = extractor.extract(pdf_bytes)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(extractor.extract, [pdf_bytes] * 32))

    assert expected.page_count == 20
    assert all(result == expected for result in results)


def test_a_small_pdf_is_extracted_while_a_large_one_is_in_progress():
    filler = "lorem ipsum dolor sit amet consectetur adipiscing elit " * 2
    large_pdf = pdf_with_lines(
        *[tuple(f"page {page} line {line} {filler}" for line in range(40)) for page in range(300)]
    )
    small_pdf = (FIXTURES_DIR / "hello.pdf").read_bytes()
    extractor = PdfiumPDFExtractor()

    with ThreadPoolExecutor(max_workers=1) as pool:
        large_extraction = pool.submit(extractor.extract, large_pdf)
        wait_until(pdf_extractor.PDFIUM_LOCK.locked)

        small_result = extractor.extract(small_pdf)

        assert not large_extraction.done()
        assert small_result.content == "Hello PDF"
        assert large_extraction.result(timeout=30).page_count == 300
