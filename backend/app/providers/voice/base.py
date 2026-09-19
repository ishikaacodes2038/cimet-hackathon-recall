"""VoiceProvider interface.

Everything above this line (state machine, orchestrator, guardrails,
escalation, handoff) is voice-vendor-agnostic — it only ever sees text
turns in and text turns out via ConversationOrchestrator.handle_utterance.
This interface is what lets the actual phone/STT/TTS vendor be swapped
without touching any of that code, per the brief's explicit architectural
requirement ("Do NOT tightly couple the entire application to a single
voice vendor").
"""

from abc import ABC, abstractmethod
from typing import Optional


class VoiceProvider(ABC):
    @abstractmethod
    def start_call(self, phone_number: str, session_id: str) -> str:
        """Places (or prepares to receive) a call. Returns a provider call id."""
        ...

    @abstractmethod
    def receive_audio(self, call_id: str) -> Optional[bytes]:
        """Pulls the next chunk of raw audio from the call, if using a pull model."""
        ...

    @abstractmethod
    def speech_to_text(self, audio_chunk: bytes) -> str:
        ...

    @abstractmethod
    def text_to_speech(self, call_id: str, text: str) -> None:
        """Speaks `text` back to the customer on the given call."""
        ...

    @abstractmethod
    def end_call(self, call_id: str) -> None:
        ...

    @abstractmethod
    def transfer_call(self, call_id: str, destination: str) -> None:
        """Warm-transfers the live call to a human agent's line/extension."""
        ...
