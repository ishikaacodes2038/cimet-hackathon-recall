"""Journey-completion sandbox.

Stands in for the real CIMET journey-completion sandbox described in the
brief ("A journey-completion sandbox or mock, with the expected payload
shape"). Swap `submit` for a real HTTP call once the actual sandbox
endpoint/schema is provided on-site — no orchestrator code needs to change.

Submissions are persisted to a local JSONL file so a completed run leaves
durable, inspectable evidence for the "working outcome" judging criterion.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from app.models.journey import JourneyState
from app.models.script import JourneyScript

REPO_ROOT = Path(__file__).resolve().parents[3]
SUBMISSIONS_LOG = REPO_ROOT / "data" / "submissions.jsonl"


class SubmissionResult(BaseModel):
    success: bool
    submission_id: str = ""
    errors: list[str] = []


def build_submission_payload(state: JourneyState, script: JourneyScript) -> dict:
    return {
        "lead_id": state.lead_id,
        "vertical": script.vertical,
        "fields": {name: cf.value for name, cf in state.collected_fields.items()},
        "consent_status": state.consent_status.value,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }


def validate_payload(payload: dict, script: JourneyScript) -> list[str]:
    errors = []
    fields = payload.get("fields", {})
    for name in script.required_field_names():
        if name not in fields or fields[name] in (None, ""):
            errors.append(f"missing required field: {name}")
    if payload.get("consent_status") != "GRANTED":
        errors.append("cannot submit without granted consent")
    return errors


class JourneySandbox:
    def submit(self, payload: dict, script: JourneyScript) -> SubmissionResult:
        errors = validate_payload(payload, script)
        if errors:
            return SubmissionResult(success=False, errors=errors)

        submission_id = f"SUB-{uuid.uuid4().hex[:10].upper()}"
        record = {"submission_id": submission_id, **payload}

        SUBMISSIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(SUBMISSIONS_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

        return SubmissionResult(success=True, submission_id=submission_id)


journey_sandbox = JourneySandbox()
