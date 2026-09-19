from fastapi import APIRouter

from app.services.script_loader import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES

router = APIRouter(tags=["meta"])


@router.get("/languages")
def list_languages() -> dict:
    return {"default": DEFAULT_LANGUAGE, "supported": SUPPORTED_LANGUAGES}
