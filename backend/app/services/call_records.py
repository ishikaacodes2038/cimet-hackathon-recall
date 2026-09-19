"""Durable call-record storage.

Every terminal call (completed, escalated, ended by customer, or dropped)
gets one row here — consent status, the language it ran in, everything
collected, whether the customer explicitly reconfirmed the read-back summary
before submission, and the outcome. This is the "store for future reference"
layer: unlike the in-memory session store (which resets on restart), this is
a real SQLite file on disk, queryable and durable.
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from pydantic import BaseModel

from app.models.journey import JourneyState

REPO_ROOT = Path(__file__).resolve().parents[3]
DB_PATH = REPO_ROOT / "data" / "call_records.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS call_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL UNIQUE,
    lead_id TEXT NOT NULL,
    language TEXT NOT NULL,
    consent_status TEXT NOT NULL,
    journey_status TEXT NOT NULL,
    end_reason TEXT,
    escalation_reason TEXT,
    customer_reconfirmed INTEGER NOT NULL,
    collected_fields_json TEXT NOT NULL,
    submission_id TEXT,
    callback_attempt INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_call_records_lead_id ON call_records(lead_id);

-- Append-only, finer-grained trail than the single terminal-state row above.
-- One row per significant moment in a call (started, field captured,
-- escalation triggered, disconnect detected, reconnect attempted, ended) —
-- this is what survives a mid-call crash, since it's written as each event
-- happens rather than only once at the end.
CREATE TABLE IF NOT EXISTS call_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    lead_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    timestamp TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_call_events_session_id ON call_events(session_id);
CREATE INDEX IF NOT EXISTS idx_call_events_lead_id ON call_events(lead_id);

-- Reference to the audio recording of a call (a Vapi-hosted URL, not a file
-- we download and host ourselves — see docs/ARCHITECTURE.md's recording
-- section for why). Never written without consent_confirmed=1.
CREATE TABLE IF NOT EXISTS call_recordings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL UNIQUE,
    lead_id TEXT NOT NULL,
    recording_url TEXT NOT NULL,
    duration_seconds REAL,
    format TEXT,
    consent_confirmed INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_call_recordings_lead_id ON call_recordings(lead_id);

-- "Terminate / close out" (post-call follow-up option #2): a closed lead
-- gets no further recovery attempts. Presence of a row means closed —
-- there's no boolean column to keep the check a simple existence lookup.
CREATE TABLE IF NOT EXISTS closed_leads (
    lead_id TEXT PRIMARY KEY,
    closed_at TEXT NOT NULL
);
"""


@contextmanager
def _connection() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        # A DB created before this session's schema additions won't have
        # the new column yet — executescript's CREATE TABLE IF NOT EXISTS
        # is a no-op on an existing table, so add it separately, tolerating
        # "already exists" for a DB that already has it.
        try:
            conn.execute("ALTER TABLE call_records ADD COLUMN end_reason TEXT")
        except sqlite3.OperationalError:
            pass
        yield conn
        conn.commit()
    finally:
        conn.close()


class CallRecord(BaseModel):
    id: int
    session_id: str
    lead_id: str
    language: str
    consent_status: str
    journey_status: str
    end_reason: Optional[str] = None
    escalation_reason: Optional[str]
    customer_reconfirmed: bool
    collected_fields: dict
    submission_id: Optional[str]
    callback_attempt: int
    created_at: str


class CallEvent(BaseModel):
    id: int
    session_id: str
    lead_id: str
    event_type: str
    payload: dict
    timestamp: str


class CallRecording(BaseModel):
    id: int
    session_id: str
    lead_id: str
    recording_url: str
    duration_seconds: Optional[float]
    format: Optional[str]
    consent_confirmed: bool
    created_at: str


def save_call_record(state: JourneyState) -> None:
    """Idempotent per session_id (UNIQUE constraint + INSERT OR REPLACE) —
    safe to call more than once for the same terminal session."""
    with _connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO call_records
                (session_id, lead_id, language, consent_status, journey_status,
                 end_reason, escalation_reason, customer_reconfirmed, collected_fields_json,
                 submission_id, callback_attempt, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                state.session_id,
                state.lead_id,
                state.language,
                state.consent_status.value,
                state.journey_status.value,
                state.end_reason.value if state.end_reason else None,
                state.escalation_reason.value if state.escalation_reason else None,
                int(state.customer_reconfirmed),
                json.dumps({name: cf.value for name, cf in state.collected_fields.items()}),
                state.submission_id,
                state.callback_attempt,
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def list_call_records(limit: int = 100) -> list[CallRecord]:
    with _connection() as conn:
        rows = conn.execute(
            "SELECT * FROM call_records ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [_row_to_record(r) for r in rows]


def get_call_record(session_id: str) -> Optional[CallRecord]:
    with _connection() as conn:
        row = conn.execute(
            "SELECT * FROM call_records WHERE session_id = ?", (session_id,)
        ).fetchone()
        return _row_to_record(row) if row else None


def list_call_records_for_lead(lead_id: str, limit: int = 100) -> list[CallRecord]:
    """Every attempt for one lead, newest first — a lead can now have
    multiple call_records rows (one per session_id) instead of the newest
    overwriting the last, so "show me this lead's call history" is a
    straight query, not a join across guesswork."""
    with _connection() as conn:
        rows = conn.execute(
            "SELECT * FROM call_records WHERE lead_id = ? ORDER BY id DESC LIMIT ?", (lead_id, limit)
        ).fetchall()
        return [_row_to_record(r) for r in rows]


def _row_to_record(row: sqlite3.Row) -> CallRecord:
    return CallRecord(
        id=row["id"],
        session_id=row["session_id"],
        lead_id=row["lead_id"],
        language=row["language"],
        consent_status=row["consent_status"],
        journey_status=row["journey_status"],
        end_reason=row["end_reason"] if "end_reason" in row.keys() else None,
        escalation_reason=row["escalation_reason"],
        customer_reconfirmed=bool(row["customer_reconfirmed"]),
        collected_fields=json.loads(row["collected_fields_json"]),
        submission_id=row["submission_id"],
        callback_attempt=row["callback_attempt"],
        created_at=row["created_at"],
    )


def log_call_event(session_id: str, lead_id: str, event_type: str, payload: Optional[dict] = None) -> None:
    """Append-only, one row per significant moment — this is what survives
    a crash mid-call, since (unlike the single call_records row) it's
    written as each event happens rather than only once at the very end.
    Call sites pass this to FastAPI's BackgroundTasks so a slow disk write
    never adds latency to a live turn."""
    with _connection() as conn:
        conn.execute(
            """
            INSERT INTO call_events (session_id, lead_id, event_type, payload_json, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, lead_id, event_type, json.dumps(payload or {}), datetime.now(timezone.utc).isoformat()),
        )


def list_call_events(session_id: Optional[str] = None, lead_id: Optional[str] = None, limit: int = 200) -> list[CallEvent]:
    """Filter by lead_id (not just session_id) so every attempt for the same
    lead shows up together, per the multi-call-per-lead requirement."""
    with _connection() as conn:
        if session_id:
            rows = conn.execute(
                "SELECT * FROM call_events WHERE session_id = ? ORDER BY id ASC LIMIT ?", (session_id, limit)
            ).fetchall()
        elif lead_id:
            rows = conn.execute(
                "SELECT * FROM call_events WHERE lead_id = ? ORDER BY id ASC LIMIT ?", (lead_id, limit)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM call_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [
            CallEvent(
                id=r["id"],
                session_id=r["session_id"],
                lead_id=r["lead_id"],
                event_type=r["event_type"],
                payload=json.loads(r["payload_json"]),
                timestamp=r["timestamp"],
            )
            for r in rows
        ]


def save_call_recording(
    session_id: str,
    lead_id: str,
    recording_url: str,
    consent_confirmed: bool,
    duration_seconds: Optional[float] = None,
    format: Optional[str] = None,  # noqa: A002 — matches the column name
) -> None:
    if not consent_confirmed:
        # A recording is never stored without a logged consent — fail
        # loudly rather than silently keeping audio that shouldn't exist.
        raise ValueError("cannot save a call recording without consent_confirmed=True")
    with _connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO call_recordings
                (session_id, lead_id, recording_url, duration_seconds, format, consent_confirmed, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, lead_id, recording_url, duration_seconds, format, int(consent_confirmed), datetime.now(timezone.utc).isoformat()),
        )


def get_call_recording(session_id: str) -> Optional[CallRecording]:
    with _connection() as conn:
        row = conn.execute("SELECT * FROM call_recordings WHERE session_id = ?", (session_id,)).fetchone()
        return _row_to_recording(row) if row else None


def list_call_recordings_for_lead(lead_id: str) -> list[CallRecording]:
    with _connection() as conn:
        rows = conn.execute(
            "SELECT * FROM call_recordings WHERE lead_id = ? ORDER BY id DESC", (lead_id,)
        ).fetchall()
        return [_row_to_recording(r) for r in rows]


def _row_to_recording(row: sqlite3.Row) -> CallRecording:
    return CallRecording(
        id=row["id"],
        session_id=row["session_id"],
        lead_id=row["lead_id"],
        recording_url=row["recording_url"],
        duration_seconds=row["duration_seconds"],
        format=row["format"],
        consent_confirmed=bool(row["consent_confirmed"]),
        created_at=row["created_at"],
    )


def close_lead(lead_id: str) -> None:
    with _connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO closed_leads (lead_id, closed_at) VALUES (?, ?)",
            (lead_id, datetime.now(timezone.utc).isoformat()),
        )


def is_lead_closed(lead_id: str) -> bool:
    with _connection() as conn:
        row = conn.execute("SELECT 1 FROM closed_leads WHERE lead_id = ?", (lead_id,)).fetchone()
        return row is not None
