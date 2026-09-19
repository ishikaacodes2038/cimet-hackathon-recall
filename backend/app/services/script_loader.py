from functools import lru_cache
from pathlib import Path

import yaml

from app.models.script import JourneyScript

# backend/app/services/script_loader.py -> repo root is three parents up
REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "scripts"

# Selectable languages, in order shown in the UI. "en" and "en-AU" are
# distinct SELECTIONS (different accent/voice on the frontend) but share the
# exact same script CONTENT — there's no wording difference between
# "English" and "English (Australian)", only which BCP-47 voice/recognition
# tag the browser uses. SCRIPT_FILE_FOR maps each selectable code to the
# script file that actually backs it.
SUPPORTED_LANGUAGES = {
    "en": "English",
    "en-AU": "English (Australian)",
    "hi": "Hindi",
    "fil": "Filipino (Tagalog)",
}
SCRIPT_FILE_FOR = {
    "en": "en",
    "en-AU": "en",
    "hi": "hi",
    "fil": "fil",
}
DEFAULT_LANGUAGE = "en-AU"  # CIMET is an Australian company — this is the sensible default


@lru_cache
def load_energy_script(language: str = DEFAULT_LANGUAGE) -> JourneyScript:
    if language not in SUPPORTED_LANGUAGES:
        language = DEFAULT_LANGUAGE
    file_key = SCRIPT_FILE_FOR[language]
    path = SCRIPTS_DIR / "energy" / f"recovery.{file_key}.yaml"
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return JourneyScript.model_validate(raw)
