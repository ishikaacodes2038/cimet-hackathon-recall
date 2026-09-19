"""Vapi voice provider.

Structurally complete against Vapi's documented REST API and "Custom LLM"
webhook pattern, but NOT exercised by any test in this repo — there is no
live Vapi account/credentials in this build environment. Treat this file as
"ready to wire in, verify against the Vapi dashboard on-site" rather than
battle-tested. Everything it calls into (ConversationOrchestrator) already
IS battle-tested via the mock provider and the scenario test suite.

Outbound call placement uses Vapi's POST /call endpoint (assistantId +
phoneNumberId + customer.number) — this part is stable and well documented.
Call end/transfer in Vapi's model is normally driven by the Assistant's own
built-in `endCall` / `transferCall` tools (configured in the Vapi dashboard)
rather than a separate REST call from our backend mid-conversation, so those
two methods below return the control signal for the webhook layer to relay
rather than making an independent HTTP call — verify this against the
current Vapi docs before relying on it live.
"""

from typing import Optional

import httpx

from app.providers.voice.base import VoiceProvider

VAPI_BASE_URL = "https://api.vapi.ai"


class VapiVoiceProvider(VoiceProvider):
    def __init__(
        self,
        api_key: str,
        assistant_id: str,
        phone_number_id: str,
        transport: Optional[httpx.BaseTransport] = None,
    ):
        # `transport` exists so tests can inject an httpx.MockTransport and
        # verify request/response handling without a live Vapi account.
        self._api_key = api_key
        self._assistant_id = assistant_id
        self._phone_number_id = phone_number_id
        self._client = httpx.Client(
            base_url=VAPI_BASE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15.0,
            transport=transport,
        )

    def start_call(self, phone_number: str, session_id: str) -> str:
        response = self._client.post(
            "/call",
            json={
                "assistantId": self._assistant_id,
                "phoneNumberId": self._phone_number_id,
                "customer": {"number": phone_number},
                "metadata": {"session_id": session_id},
            },
        )
        response.raise_for_status()
        return response.json()["id"]

    def receive_audio(self, call_id: str) -> Optional[bytes]:
        # Not used: Vapi pushes conversation turns to our webhook (see
        # app/api/vapi_webhook.py) rather than us pulling raw audio.
        return None

    def speech_to_text(self, audio_chunk: bytes) -> str:
        raise NotImplementedError("Vapi performs STT itself; text arrives pre-transcribed via the webhook.")

    def text_to_speech(self, call_id: str, text: str) -> None:
        raise NotImplementedError("Vapi performs TTS itself from the webhook response text; no separate call needed.")

    def end_call(self, call_id: str) -> None:
        response = self._client.post(f"/call/{call_id}/end")
        response.raise_for_status()

    def transfer_call(self, call_id: str, destination: str) -> None:
        # Prefer the Assistant's built-in transferCall tool where possible;
        # this REST fallback needs to be verified against live Vapi docs.
        response = self._client.post(f"/call/{call_id}/transfer", json={"destination": destination})
        response.raise_for_status()
