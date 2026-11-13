from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from application.document_service import QueueFullError
from presentation.routers.extract import get_document_service
from presentation.routers.extract import router as extract_router

__all__ = ["app", "get_document_service"]

app = FastAPI()
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
