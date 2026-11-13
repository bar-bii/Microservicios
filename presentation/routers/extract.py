from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from application.document_service import DocumentService
from application.pdf_extractor import InvalidPDFException, PypdfPDFExtractor

router = APIRouter()
_document_service = DocumentService(PypdfPDFExtractor())


def get_document_service() -> DocumentService:
    return _document_service


@router.post("/extract", status_code=200)
async def extract(
    file: Annotated[UploadFile, File()],
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> dict[str, str | int]:
    pdf_bytes = await file.read()

    try:
        result = await service.process(pdf_bytes)
    except InvalidPDFException as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"content": result.content, "page_count": result.page_count}
