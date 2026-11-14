from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from application.config import ConcurrencyConfig
from application.document_service import DocumentService, QueueFullError, extraction_executor
from application.pdf_extractor import PypdfPDFExtractor
from presentation.access_log import AccessLogMiddleware
from presentation.routers.extract import router as extract_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    config = ConcurrencyConfig.from_env()
    with extraction_executor(config) as executor:
        app.state.document_service = DocumentService(PypdfPDFExtractor(), config, executor)
        yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(AccessLogMiddleware)
app.include_router(extract_router)


@app.exception_handler(QueueFullError)
async def queue_full_handler(_request: Request, exc: QueueFullError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": str(exc)},
        headers={"Retry-After": "1"},
    )


@app.get("/health", status_code=200)
def health() -> dict[str, str]:
    return {"status": "ok"}
