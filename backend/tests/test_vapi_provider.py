"""Verifies the Vapi wiring at the code level, without a live account:

1. VapiVoiceProvider builds the request Vapi's documented POST /call
   endpoint expects, and correctly parses the call id back out.
2. POST /voice/session, when VOICE_PROVIDER=vapi, actually places that call
   (this is the wiring gap that was found and fixed — previously the
   session endpoint never called start_call() at all, so no real call could
   ever have been placed even with valid credentials).
3. The /vapi/webhook adapter correctly finds the session from call metadata
   and drives the same orchestrator used by /voice/message.

None of this proves the assumed request/response envelope matches Vapi's
real API — that still needs on-site verification against a live account —
but it does prove the integration is actually connected end to end now.
"""

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_voice_provider
from app.main import app
from app.providers.voice.vapi import VapiVoiceProvider

client = TestClient(app)


def make_fake_vapi_provider(handler) -> VapiVoiceProvider:
    transport = httpx.MockTransport(handler)
    return VapiVoiceProvider(
        api_key="test-key", assistant_id="asst-1", phone_number_id="phone-1", transport=transport
    )


def test_vapi_provider_start_call_builds_correct_request_and_parses_id():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["body"] = httpx.Request(request.method, request.url, content=request.content).content
        return httpx.Response(201, json={"id": "call-abc123"})

    provider = make_fake_vapi_provider(handler)
    call_id = provider.start_call("+61411111111", "session-xyz")

    assert call_id == "call-abc123"
    assert captured["method"] == "POST"
    assert captured["url"] == "https://api.vapi.ai/call"


def test_vapi_provider_end_call_and_transfer_call_hit_expected_paths():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        return httpx.Response(200, json={})

    provider = make_fake_vapi_provider(handler)
    provider.end_call("call-1")
    provider.transfer_call("call-1", "+61499999999")

    assert calls == [("POST", "/call/call-1/end"), ("POST", "/call/call-1/transfer")]


def test_vapi_provider_raises_on_http_error_rather_than_silently_succeeding():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "unauthorized"})

    provider = make_fake_vapi_provider(handler)
    with pytest.raises(httpx.HTTPStatusError):
        provider.start_call("+61411111111", "session-xyz")


def test_voice_session_places_a_real_call_when_provider_is_vapi():
    """This is the regression test for the wiring gap: /voice/session must
    actually call start_call() when running against a real provider."""
    placed_calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/call":
            placed_calls.append(request)
            return httpx.Response(201, json={"id": "call-live-1"})
        return httpx.Response(200, json={})

    fake_provider = make_fake_vapi_provider(handler)
    app.dependency_overrides[get_voice_provider] = lambda: fake_provider
    try:
        resp = client.post("/voice/session", json={"lead_id": "LEAD-1001"})
        body = resp.json()
        assert resp.status_code == 200
        assert body["call_id"] == "call-live-1"
        assert len(placed_calls) == 1
    finally:
        app.dependency_overrides.pop(get_voice_provider, None)


def test_voice_session_surfaces_call_placement_failure_instead_of_faking_success():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "vapi is down"})

    fake_provider = make_fake_vapi_provider(handler)
    app.dependency_overrides[get_voice_provider] = lambda: fake_provider
    try:
        # start_call raises inside the mock-provider branch check in voice.py,
        # which only special-cases the failure when settings.voice_provider
        # is actually "vapi" — so this also exercises that branch via a
        # settings override.
        from app.api import voice as voice_module

        original_settings_fn = voice_module.get_settings

        class _FakeSettings:
            voice_provider = "vapi"

        voice_module.get_settings = lambda: _FakeSettings()
        try:
            resp = client.post("/voice/session", json={"lead_id": "LEAD-1002"})
            body = resp.json()
            assert resp.status_code == 200
            assert body["session_id"] == ""
            assert body["call_placement_error"]
        finally:
            voice_module.get_settings = original_settings_fn
    finally:
        app.dependency_overrides.pop(get_voice_provider, None)


def test_vapi_webhook_finds_session_and_drives_the_same_orchestrator():
    start_resp = client.post("/voice/session", json={"lead_id": "LEAD-1001"})
    session_id = start_resp.json()["session_id"]

    webhook_resp = client.post(
        "/vapi/webhook",
        json={
            "messages": [{"role": "user", "content": "Yes that's fine"}],
            "call": {"metadata": {"session_id": session_id}},
        },
    )
    assert webhook_resp.status_code == 200
    body = webhook_resp.json()
    assert body["choices"][0]["message"]["role"] == "assistant"
    assert "date of birth" in body["choices"][0]["message"]["content"].lower()


def test_vapi_webhook_404s_for_unknown_session():
    resp = client.post(
        "/vapi/webhook",
        json={"messages": [{"role": "user", "content": "hello"}], "call": {"metadata": {"session_id": "nope"}}},
    )
    assert resp.status_code == 404
