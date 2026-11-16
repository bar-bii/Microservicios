import threading
from contextlib import closing
from dataclasses import dataclass
from typing import Protocol

import pypdfium2 as pdfium

PDF_SIGNATURE = b"%PDF-"
PDFIUM_LINE_BREAK = "\r\n"
PDFIUM_LOCK = threading.Lock()


class InvalidPDFError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    content: str
    page_count: int


class PDFExtractor(Protocol):
    def extract(self, pdf_bytes: bytes) -> ExtractionResult: ...


class PdfiumPDFExtractor:
    def extract(self, pdf_bytes: bytes) -> ExtractionResult:
        if not pdf_bytes.startswith(PDF_SIGNATURE):
            raise InvalidPDFError("uploaded file is not a valid PDF")

        try:
            pages = _read_pages(pdf_bytes)
        except pdfium.PdfiumError as exc:
            raise InvalidPDFError("uploaded file is not a valid PDF") from exc

        return ExtractionResult(
            content="\n".join(pages),
            page_count=len(pages),
        )


def _read_pages(pdf_bytes: bytes) -> list[str]:
    with PDFIUM_LOCK:
        document = pdfium.PdfDocument(pdf_bytes)
        page_count = len(document)

    try:
        return [_read_page(document, index) for index in range(page_count)]
    finally:
        with PDFIUM_LOCK:
            document.close()


def _read_page(document: pdfium.PdfDocument, index: int) -> str:
    with (
        PDFIUM_LOCK,
        closing(document[index]) as page,
        closing(page.get_textpage()) as text_page,
    ):
        text = text_page.get_text_range()

    return text.replace(PDFIUM_LINE_BREAK, "\n")
