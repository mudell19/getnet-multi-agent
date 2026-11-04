import json
from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest
from google.genai import errors, types

import getnet_multi_agent.llm as llm_module
from getnet_multi_agent.llm import BudgetExceeded, LLMClient, LLMUnavailable, RequestContext


def response(text="ok", prompt=100, output=50, thoughts=None, queries=None, chunks=None, parts=None):
    part = types.Part(text=text)
    return NS(
        usage_metadata=NS(
            prompt_token_count=prompt, candidates_token_count=output, thoughts_token_count=thoughts
        ),
        candidates=[
            NS(
                content=types.Content(role="model", parts=parts or [part]),
                grounding_metadata=NS(web_search_queries=queries, grounding_chunks=chunks)
                if queries or chunks
                else None,
            )
        ],
    )


def api_error(code):
    return errors.APIError(code, {"error": {"message": "x", "status": "x", "code": code}})


@pytest.fixture
def ctx():
    return RequestContext(request_id="req-1", budget=20000)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(llm_module, "RETRY_DELAY_SECONDS", 0)


def make(settings):
    client = MagicMock()
    return LLMClient(settings, client), client


def test_R46_records_tokens_and_cost_with_thinking_billed_as_output(settings, ctx):
    llm, client = make(settings)
    client.models.generate_content.return_value = response(prompt=1000, output=100, thoughts=100)
    llm.generate(ctx, "knowledge", settings.answer, "hi")
    rec = ctx.records[0]
    assert (rec.prompt_tokens, rec.output_tokens, rec.thinking_tokens) == (1000, 100, 100)
    assert rec.model == "answer-model" and rec.latency_ms >= 0
    assert rec.cost_usd == pytest.approx((1000 * 0.75 + 200 * 3.75) / 1e6)


def test_R46_cost_includes_search_requests_from_grounding_metadata(settings, ctx):
    llm, client = make(settings)
    chunks = [NS(web=NS(uri="https://x.test/a", title="x.test"))]
    client.models.generate_content.return_value = response(
        prompt=0, output=0, queries=["a", "b"], chunks=chunks
    )
    result = llm.generate(ctx, "knowledge", settings.answer, "hi")
    assert ctx.records[0].search_requests == 2
    assert ctx.records[0].cost_usd == pytest.approx(2 * 14 / 1000)
    assert result.grounding_sources == [("https://x.test/a", "x.test")]


def test_R46_logs_json_with_request_id(settings, ctx, capsys):
    llm, client = make(settings)
    client.models.generate_content.return_value = response()
    import logging

    records = []
    handler = logging.Handler()
    handler.emit = lambda r: records.append(r.getMessage())
    logging.getLogger("getnet").addHandler(handler)
    llm.generate(ctx, "router", settings.router, "hi")
    logging.getLogger("getnet").removeHandler(handler)
    event = json.loads(records[0])
    assert event["event"] == "llm_call" and event["request_id"] == "req-1"


def test_R47_budget_blocks_call_before_it_is_made(settings):
    llm, client = make(settings)
    ctx = RequestContext(request_id="r", budget=10)
    with pytest.raises(BudgetExceeded):
        llm.generate(ctx, "router", settings.router, "x" * 1000)
    client.models.generate_content.assert_not_called()


def test_R47_budget_counts_thinking_tokens_across_calls(settings):
    llm, client = make(settings)
    ctx = RequestContext(request_id="r", budget=200)
    client.models.generate_content.return_value = response(prompt=100, output=50, thoughts=60)
    llm.generate(ctx, "router", settings.router, "a")
    assert ctx.tokens_used == 210
    with pytest.raises(BudgetExceeded):
        llm.generate(ctx, "router", settings.router, "a")


@pytest.mark.parametrize("code", [429, 500, 503])
def test_R47_retries_once_on_429_and_5xx(settings, ctx, code):
    llm, client = make(settings)
    client.models.generate_content.side_effect = [api_error(code), response()]
    assert llm.generate(ctx, "router", settings.router, "a").text == "ok"
    assert client.models.generate_content.call_count == 2


def test_R47_R55_second_failure_raises_unavailable(settings, ctx):
    llm, client = make(settings)
    client.models.generate_content.side_effect = api_error(503)
    with pytest.raises(LLMUnavailable):
        llm.generate(ctx, "router", settings.router, "a")
    assert client.models.generate_content.call_count == 2


def test_R47_no_retry_on_other_client_errors(settings, ctx):
    llm, client = make(settings)
    client.models.generate_content.side_effect = api_error(400)
    with pytest.raises(LLMUnavailable):
        llm.generate(ctx, "router", settings.router, "a")
    assert client.models.generate_content.call_count == 1


def test_R47_timeout_is_set_on_every_call(settings, ctx):
    llm, client = make(settings)
    client.models.generate_content.return_value = response()
    llm.generate(ctx, "router", settings.router, "a")
    config = client.models.generate_content.call_args.kwargs["config"]
    assert config.http_options.timeout == 30000


def test_R45_thinking_level_comes_from_the_role(settings, ctx):
    llm, client = make(settings)
    client.models.generate_content.return_value = response()
    llm.generate(ctx, "knowledge", settings.answer, "a")
    call = client.models.generate_content.call_args.kwargs
    assert call["model"] == "answer-model"
    assert call["config"].thinking_config.thinking_level.value.lower() == "low"


def test_R48_preserves_complete_content_with_thought_signature(settings, ctx):
    llm, client = make(settings)
    part = types.Part(
        function_call=types.FunctionCall(name="get_receivables", args={}),
        thought_signature=b"signature",
    )
    client.models.generate_content.return_value = response(parts=[part])
    result = llm.generate(ctx, "support", settings.answer, "a")
    assert result.content.parts[0].thought_signature == b"signature"
    assert result.function_calls[0].name == "get_receivables"


def test_R46_embed_sends_content_items_and_records_estimate(settings, ctx):
    llm, client = make(settings)
    client.models.embed_content.return_value = NS(embeddings=[NS(values=[1.0]), NS(values=[2.0])])
    assert llm.embed(ctx, "knowledge", ["aaaa", "bbbb"]) == [[1.0], [2.0]]
    contents = client.models.embed_content.call_args.kwargs["contents"]
    assert all(isinstance(c, types.Content) for c in contents)
    assert ctx.records[0].tokens_estimated and ctx.records[0].prompt_tokens == 2
