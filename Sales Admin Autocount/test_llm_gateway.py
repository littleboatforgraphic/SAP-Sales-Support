"""
Tests for routing LLM calls through the llm-gateway (no network; the OpenAI client is stubbed).
Run: python test_llm_gateway.py  (or pytest test_llm_gateway.py)
"""
from types import SimpleNamespace

import llm_client
from config import settings


def _fake_openai(calls):
    def create(**kw):
        calls.append(kw)
        usage = SimpleNamespace(prompt_tokens=120, completion_tokens=30,
                                prompt_tokens_details=SimpleNamespace(cached_tokens=20))
        return SimpleNamespace(usage=usage, choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])

    class FakeOpenAI:
        def __init__(self, base_url=None, api_key=None):
            self.base_url, self.api_key = base_url, api_key
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))
    return FakeOpenAI


def _client(monkey, gateway_url, gateway_key="sk-gw"):
    calls = []
    orig = (llm_client.OpenAI, settings.llm_gateway_url, settings.llm_gateway_key)
    llm_client.OpenAI = _fake_openai(calls)
    settings.llm_gateway_url, settings.llm_gateway_key = gateway_url, gateway_key
    monkey.append(lambda: (setattr(llm_client, "OpenAI", orig[0]),
                           setattr(settings, "llm_gateway_url", orig[1]),
                           setattr(settings, "llm_gateway_key", orig[2])))
    return llm_client.LLMClient(), calls


def test_gateway_routing_and_tags():
    undo = []
    try:
        client, calls = _client(undo, "http://gateway/v1")
        assert client.client.base_url == "http://gateway/v1" and client.client.api_key == "sk-gw"
        assert client.vision_client is client.client
        result = client.chat_completion([{"role": "user", "content": "hi"}], operation="enquiry")
        assert calls[0]["extra_body"]["metadata"]["tags"] == ["app:sales-autocount", "op:enquiry"]
        assert result["cached_input_tokens"] == 20 and result["total_tokens"] == 150
        client.chat_completion([{"role": "user", "content": "hi"}])
        assert calls[1]["extra_body"]["metadata"]["tags"][-1] == "op:chat"
    finally:
        [u() for u in undo]


def test_direct_ilmu_when_gateway_unset():
    undo = []
    try:
        client, calls = _client(undo, "")
        assert client.client.base_url == settings.ilmu_base_url
        client.chat_completion([{"role": "user", "content": "hi"}], operation="enquiry")
        assert "extra_body" not in calls[0]
    finally:
        [u() for u in undo]


if __name__ == "__main__":
    test_gateway_routing_and_tags()
    test_direct_ilmu_when_gateway_unset()
    print("[PASS] llm gateway tests")
