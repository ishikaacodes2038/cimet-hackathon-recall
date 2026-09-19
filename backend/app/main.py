import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.api.auth import router as auth_router
from app.api.call_records import router as call_records_router
from app.api.escalation import router as escalation_router
from app.api.handoff import router as handoff_router
from app.api.health import router as health_router
from app.api.journey import router as journey_router
from app.api.leads import router as leads_router
from app.api.meta import router as meta_router
from app.api.metrics import router as metrics_router
from app.api.vapi_webhook import router as vapi_webhook_router
from app.api.voice import router as voice_router
from app.config import get_settings

settings = get_settings()

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("cimet.energy_voice_agent")

app = FastAPI(
    title="CIMET Energy Voice Agent",
    description="AI voice agent that recovers dropped-off Energy comparison journeys.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(health_router)
app.include_router(leads_router)
app.include_router(voice_router)
app.include_router(journey_router)
app.include_router(escalation_router)
app.include_router(handoff_router)
app.include_router(metrics_router)
app.include_router(call_records_router)
app.include_router(meta_router)
app.include_router(vapi_webhook_router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Never let a raw stack trace (or the request that triggered it) leak to a caller.
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "internal_error"})


@app.get("/")
def root() -> dict:
    return {"service": "cimet-energy-voice-agent", "status": "running"}


STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.get("/console")
def quick_console() -> FileResponse:
    # Zero-build test console (no Node/npm needed) — same API the real
    # React console in frontend/ uses, served same-origin so there's no
    # CORS configuration to worry about while testing.
    return FileResponse(STATIC_DIR / "quick_console.html")
