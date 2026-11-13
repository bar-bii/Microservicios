from dataclasses import dataclass
from io import BytesIO
from typing import Protocol

from pypdf import PdfReader
from pypdf.errors import PyPdfError

PDF_SIGNATURE = b"%PDF-"


class InvalidPDFError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    content: str
    page_count: int


class PDFExtractor(Protocol):
    def extract(self, pdf_bytes: bytes) -> ExtractionResult: ...


class PypdfPDFExtractor:
    def extract(self, pdf_bytes: bytes) -> ExtractionResult:
        if not pdf_bytes.startswith(PDF_SIGNATURE):
            raise InvalidPDFError("uploaded file is not a valid PDF")

        try:
            reader = PdfReader(BytesIO(pdf_bytes))
            pages = [page.extract_text() or "" for page in reader.pages]
        except PyPdfError as exc:
            raise InvalidPDFError("uploaded file is not a valid PDF") from exc

        return ExtractionResult(
            content="\n".join(pages),
            page_count=len(pages),
        )
