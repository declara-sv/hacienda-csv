import base64
import datetime as dt
import json
from decimal import Decimal
from types import SimpleNamespace

import anthropic
import httpx2 as httpx
import pytest

from app.config import Settings
from app.domain import AiCallOutcome
from app.extraction import AiExtractionError, ClaudeAiExtractor, build_ai_extractor
from app.extraction.ai import AiDocument, AiExtraction

PDF = b"%PDF-1.4 fake"


def _doc(**overrides) -> AiDocument:
    data = {
        "tipo_dte": "03",
        "codigo_generacion": "7B8C9D0E-1F2A-4B3C-9D4E-5F6A7B8C9D0E",
        "numero_control": "DTE-03-M001P001-000000000000055",
        "sello_recepcion": "2026ABCDEF0123456789ABCDEF0123456789ABCD",
        "fecha_emision": "2026-10-05",
        "hora_emision": "10:15:30",
        "emisor_nombre": "FARMACIA DEMO DE PRUEBAS SV",
        "emisor_nit": "01234567-8",
        "emisor_nrc": "1234-5",
        "receptor_nombre": "CLIENTE DEMO, S.A. DE C.V.",
        "receptor_nit": "0614-010101-101-1",
        "receptor_nrc": "123456-7",
        "receptor_dui": None,
        "total_no_sujetas": "0.00",
        "total_exentas": "0.00",
        "total_gravadas": "1,000.00",
        "iva": "130.00",
        "iva_retenido": "0.00",
        "total": "$1130.00",
    }
    data.update(overrides)
    return AiDocument(**data)


class FakeMessages:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


def _client(response=None, error=None):
    return SimpleNamespace(messages=FakeMessages(response, error))


def _usage(input_tokens=1200, output_tokens=300, cache_read=None, cache_creation=None):
    return SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_input_tokens=cache_read,
        cache_creation_input_tokens=cache_creation,
    )


def _response(parsed, stop_reason="end_turn", text=None, usage=None):
    if text is None and parsed is not None:
        text = parsed.model_dump_json()
    content = [SimpleNamespace(type="text", text=text)] if text is not None else []
    return SimpleNamespace(stop_reason=stop_reason, content=content, usage=usage or _usage())


def test_request_shape_and_conversion():
    client = _client(_response(AiExtraction(documents=[_doc()])))
    output = ClaudeAiExtractor(client, "claude-opus-5-5").extract(PDF)
    records = output.records

    (call,) = client.messages.calls
    assert call["model"] == "claude-opus-5-5"
    assert call["max_tokens"] == 16000
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert "documents" in json.dumps(call["output_config"]["format"]["schema"])
    assert not {"temperature", "top_p", "top_k", "thinking"} & set(call)
    content = call["messages"][0]["content"]
    assert content[0] == {
        "type": "document",
        "source": {"type": "base64", "media_type": "application/pdf", "data": base64.b64encode(PDF).decode()},
    }
    assert content[1]["type"] == "text"
    assert "exactly as printed" in content[1]["text"]

    (record,) = records
    assert record.tipo_dte == "03"
    assert record.codigo_generacion == "7B8C9D0E-1F2A-4B3C-9D4E-5F6A7B8C9D0E"
    assert record.receptor_nit == "0614-010101-101-1"
    assert record.fecha_emision == dt.date(2026, 10, 5)
    assert record.hora_emision == dt.time(10, 15, 30)
    assert record.total_gravadas == Decimal("1000.00")
    assert record.iva == Decimal("130.00")
    assert record.total == Decimal("1130.00")


def test_dashes_and_blanks_become_none_and_tipo_is_padded():
    client = _client(
        _response(AiExtraction(documents=[_doc(tipo_dte="1", sello_recepcion="-", receptor_nit="")]))
    )
    (record,) = ClaudeAiExtractor(client, "m").extract(PDF).records
    assert record.tipo_dte == "01"
    assert record.sello_recepcion is None
    assert record.receptor_nit is None


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens", "pause_turn"])
def test_bad_stop_reasons_fail(stop_reason):
    client = _client(_response(AiExtraction(documents=[_doc()]), stop_reason=stop_reason))
    with pytest.raises(AiExtractionError):
        ClaudeAiExtractor(client, "m").extract(PDF)


def test_missing_parsed_output_fails():
    with pytest.raises(AiExtractionError):
        ClaudeAiExtractor(_client(_response(None)), "m").extract(PDF)


def test_invalid_amount_fails():
    client = _client(_response(AiExtraction(documents=[_doc(total="mucho")])))
    with pytest.raises(AiExtractionError):
        ClaudeAiExtractor(client, "m").extract(PDF)


_REQUEST = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


@pytest.mark.parametrize(
    "error",
    [
        anthropic.APIConnectionError(request=_REQUEST),
        anthropic.APITimeoutError(request=_REQUEST),
        anthropic.APIStatusError("overloaded", response=httpx.Response(529, request=_REQUEST), body=None),
        anthropic.AnthropicError("other"),
        ValueError("bad json"),
    ],
)
def test_sdk_errors_are_wrapped(error):
    with pytest.raises(AiExtractionError):
        ClaudeAiExtractor(_client(error=error), "m").extract(PDF)


def _sdk_client(handler):
    return anthropic.Anthropic(
        api_key="test-key",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def _message(text, stop_reason="end_turn"):
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5-5",
        "content": [{"type": "text", "text": text}],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 10},
    }


def test_real_sdk_request_with_mock_transport():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        payload = AiExtraction(documents=[_doc()]).model_dump_json()
        return httpx.Response(200, json=_message(payload))

    output = ClaudeAiExtractor(_sdk_client(handler), "claude-opus-5-5").extract(PDF)
    (record,) = output.records
    assert record.total == Decimal("1130.00")
    assert output.usage is not None
    assert (output.usage.input_tokens, output.usage.output_tokens) == (10, 10)
    assert (output.usage.cache_read_tokens, output.usage.cache_creation_tokens) == (0, 0)

    body = seen["body"]
    assert body["model"] == "claude-opus-5-5"
    assert body["messages"][0]["content"][0]["type"] == "document"
    schema = body["output_config"]["format"]
    assert schema["type"] == "json_schema"
    assert "documents" in json.dumps(schema["schema"])


def test_real_sdk_refusal_text_is_a_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_message("No puedo ayudar con eso.", stop_reason="refusal"))

    with pytest.raises(AiExtractionError) as info:
        ClaudeAiExtractor(_sdk_client(handler), "m").extract(PDF)
    # Billed even though the output was a refusal.
    assert info.value.usage is not None
    assert info.value.usage.input_tokens == 10
    assert info.value.usage.outcome == AiCallOutcome.FAILED


def test_real_sdk_http_error_is_a_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401, json={"type": "error", "error": {"type": "authentication_error", "message": "x"}}
        )

    with pytest.raises(AiExtractionError, match="401"):
        ClaudeAiExtractor(_sdk_client(handler), "m").extract(PDF)


def test_build_ai_extractor():
    assert build_ai_extractor(Settings(anthropic_api_key="", ai_extraction_enabled=True)) is None
    assert build_ai_extractor(Settings(anthropic_api_key="k", ai_extraction_enabled=False)) is None
    extractor = build_ai_extractor(Settings(anthropic_api_key="k", ai_extraction_model="claude-opus-5-5"))
    assert isinstance(extractor, ClaudeAiExtractor)


def test_usage_is_captured_with_cache_tokens_and_missing_ones_as_zero():
    response = _response(
        AiExtraction(documents=[_doc()]), usage=_usage(500, 100, cache_read=40, cache_creation=None)
    )
    output = ClaudeAiExtractor(_client(response), "claude-sonnet-5-5").extract(PDF)
    usage = output.usage
    assert usage is not None
    assert usage.model == "claude-sonnet-5-5"
    assert (usage.input_tokens, usage.output_tokens) == (500, 100)
    assert (usage.cache_read_tokens, usage.cache_creation_tokens) == (40, 0)
    assert usage.duration_ms is not None and usage.duration_ms >= 0
    assert usage.outcome == AiCallOutcome.USED


@pytest.mark.parametrize(
    "response",
    [
        _response(AiExtraction(documents=[_doc()]), stop_reason="max_tokens"),
        _response(None, text="esto no es json"),
        _response(AiExtraction(documents=[_doc(total="mucho")])),
    ],
)
def test_rejected_output_still_reports_tokens(response):
    with pytest.raises(AiExtractionError) as info:
        ClaudeAiExtractor(_client(response), "claude-opus-5-5").extract(PDF)
    usage = info.value.usage
    assert usage is not None
    assert (usage.input_tokens, usage.output_tokens) == (1200, 300)
    assert usage.outcome == AiCallOutcome.FAILED


def test_sdk_error_without_response_reports_a_call_without_tokens():
    error = anthropic.APIConnectionError(request=_REQUEST)
    with pytest.raises(AiExtractionError) as info:
        ClaudeAiExtractor(_client(error=error), "claude-opus-5-5").extract(PDF)
    usage = info.value.usage
    assert usage is not None
    assert usage.input_tokens is None and usage.output_tokens is None
    assert usage.outcome == AiCallOutcome.FAILED
