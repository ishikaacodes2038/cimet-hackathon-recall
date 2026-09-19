import pytest

from app.guardrails import dnc as dnc_module
from app.services import call_records as call_records_module
from app.services import journey_sandbox as journey_sandbox_module


@pytest.fixture(autouse=True)
def isolate_submissions_log(tmp_path, monkeypatch):
    """Tests must never write into the real data/submissions.jsonl — that
    file is demo evidence, not a scratch pad for CI runs."""
    monkeypatch.setattr(journey_sandbox_module, "SUBMISSIONS_LOG", tmp_path / "submissions.jsonl")


@pytest.fixture(autouse=True)
def isolate_call_records_db(tmp_path, monkeypatch):
    """Same reasoning as the submissions log — call_records.db is durable
    demo evidence, not a place for test runs to leave rows."""
    monkeypatch.setattr(call_records_module, "DB_PATH", tmp_path / "call_records.db")


@pytest.fixture(autouse=True)
def isolate_dnc_registry():
    """The DNC registry is a mutable module-level set (add_to_dnc() writes
    into it). Without resetting it between tests, a hard-refusal scenario in
    one test would leak into and DNC-block every later test that reuses the
    same synthetic lead's phone number — reset to the seeded stub state
    before every test."""
    original = set(dnc_module._dnc_registry)
    yield
    dnc_module._dnc_registry.clear()
    dnc_module._dnc_registry.update(original)
