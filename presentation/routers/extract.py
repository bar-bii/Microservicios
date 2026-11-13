from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from application.config import UploadConfig
from application.document_service import DocumentService
from application.pdf_extractor import InvalidPDFError

PDF_MIME_TYPE = "application/pdf"

router = APIRouter()
_upload_config = UploadConfig.from_env()


class ExtractResponse(BaseModel):
    content: str
    page_count: int


def get_document_service(request: Request) -> DocumentService:
    return request.app.state.document_service


def get_upload_config() -> UploadConfig:
    return _upload_config


@router.post("/extract", status_code=200)
async def extract(
    file: Annotated[UploadFile, File()],
    service: Annotated[DocumentService, Depends(get_document_service)],
    upload_config: Annotated[UploadConfig, Depends(get_upload_config)],
) -> ExtractResponse:
    if file.content_type != PDF_MIME_TYPE:
        raise HTTPException(status_code=415, detail=f"uploaded file must be {PDF_MIME_TYPE}")

    pdf_bytes = await file.read(upload_config.max_upload_bytes + 1)
    if len(pdf_bytes) > upload_config.max_upload_bytes:
        raise HTTPException(status_code=413, detail="uploaded file exceeds size limit")

    try:
        result = await service.process(pdf_bytes)
    except InvalidPDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ExtractResponse(content=result.content, page_count=result.page_count)
