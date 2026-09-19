"""Mock voice provider — a local text loop standing in for a real phone call.

This is what /voice/session and /voice/message run on. It's not a lesser
fallback bolted on afterwards: STT and TTS are the two biggest sources of
non-determinism and demo risk in a 12-hour build, so the entire
conversational core (state machine, extraction, guardrails, escalation) was
built and adversarially tested against this text interface FIRST. Swapping
in VapiVoiceProvider only changes how text gets in and out — every line of
orchestration logic already exercised here runs unmodified on a real call.
"""

import uuid
from typing import Optional

from app.providers.voice.base import VoiceProvider


class MockVoiceProvider(VoiceProvider):
    def start_call(self, phone_number: str, session_id: str) -> str:
        return f"mock-call-{uuid.uuid4().hex[:8]}"

    def receive_audio(self, call_id: str) -> Optional[bytes]:
        return None  # text goes straight through /voice/message instead

    def speech_to_text(self, audio_chunk: bytes) -> str:
        return audio_chunk.decode("utf-8", errors="ignore")

    def text_to_speech(self, call_id: str, text: str) -> None:
        return None  # the API response body IS the "speech" in text mode

    def end_call(self, call_id: str) -> None:
        return None

    def transfer_call(self, call_id: str, destination: str) -> None:
        return None
