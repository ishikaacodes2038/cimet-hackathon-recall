import logging
from functools import lru_cache

from app.agents.orchestrator import ConversationOrchestrator
from app.config import get_settings
from app.providers.voice.base import VoiceProvider
from app.providers.voice.mock import MockVoiceProvider
from app.services.llm_client import build_llm_client

logger = logging.getLogger("cimet.deps")


@lru_cache
def get_orchestrator() -> ConversationOrchestrator:
    settings = get_settings()
    llm_client = build_llm_client(
        settings.llm_provider, settings.llm_api_key, settings.llm_model, settings.llm_base_url
    )
    return ConversationOrchestrator(llm_client)


@lru_cache
def get_voice_provider() -> VoiceProvider:
    settings = get_settings()
    if settings.voice_provider == "vapi" and settings.vapi_api_key:
        from app.providers.voice.vapi import VapiVoiceProvider

        try:
            return VapiVoiceProvider(
                api_key=settings.vapi_api_key,
                assistant_id=settings.vapi_assistant_id,
                phone_number_id=settings.vapi_phone_number_id,
            )
        except Exception:
            logger.exception("Failed to initialise VapiVoiceProvider; falling back to mock voice provider")
            return MockVoiceProvider()
    return MockVoiceProvider()
