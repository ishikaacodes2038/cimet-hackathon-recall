import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

from app.models.lead import Lead

REPO_ROOT = Path(__file__).resolve().parents[3]
LEADS_PATH = REPO_ROOT / "data" / "synthetic" / "energy_leads.json"


@lru_cache
def _load_leads() -> dict[str, Lead]:
    with open(LEADS_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return {item["lead_id"]: Lead.model_validate(item) for item in raw}


def get_lead(lead_id: str) -> Optional[Lead]:
    return _load_leads().get(lead_id)


def list_leads() -> list[Lead]:
    return list(_load_leads().values())
