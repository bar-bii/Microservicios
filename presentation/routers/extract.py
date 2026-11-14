from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from starlette.datastructures import UploadFile

from application.config import UploadConfig
from application.document_service import DocumentService
from application.pdf_extractor import InvalidPDFError

PDF_MIME_TYPE = "application/pdf"
FILE_FIELD = "file"
MISSING_FILE_ERROR = {
    "type": "missing",
    "loc": ("body", FILE_FIELD),
    "msg": "Field required",
    "input": None,
}
MULTIPART_REQUEST_BODY = {
    "required": True,
    "content": {
        "multipart/form-data": {
            "schema": {
                "type": "object",
                "required": [FILE_FIELD],
                "properties": {FILE_FIELD: {"type": "string", "format": "binary"}},
            }
        }
    },
}

router = APIRouter()
_upload_config = UploadConfig.from_env()


class ExtractResponse(BaseModel):
    content: str
    page_count: int


def get_document_service(request: Request) -> DocumentService:
    return request.app.state.document_service


def get_upload_config() -> UploadConfig:
    return _upload_config


async def read_pdf_upload(request: Request, max_upload_bytes: int) -> bytes:
    async with request.form() as form:
        file = form.get(FILE_FIELD)
        if not isinstance(file, UploadFile):
            raise RequestValidationError([MISSING_FILE_ERROR])

        if file.content_type != PDF_MIME_TYPE:
            raise HTTPException(status_code=415, detail=f"uploaded file must be {PDF_MIME_TYPE}")

        pdf_bytes = await file.read(max_upload_bytes + 1)

    if len(pdf_bytes) > max_upload_bytes:
        raise HTTPException(status_code=413, detail="uploaded file exceeds size limit")

    return pdf_bytes


@router.post(
    "/extract",
    status_code=200,
    openapi_extra={"requestBody": MULTIPART_REQUEST_BODY},
)
async def extract(
    request: Request,
    service: Annotated[DocumentService, Depends(get_document_service)],
    upload_config: Annotated[UploadConfig, Depends(get_upload_config)],
) -> ExtractResponse:
    with service.admit():
        pdf_bytes = await read_pdf_upload(request, upload_config.max_upload_bytes)

        try:
            result = await service.process_admitted(pdf_bytes)
        except InvalidPDFError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ExtractResponse(content=result.content, page_count=result.page_count)
