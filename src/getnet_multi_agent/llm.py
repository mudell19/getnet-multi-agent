"""The single wrapper for every LLM call: cost, tokens, budget, timeout, retry and logging."""
import time
from dataclasses import dataclass, field
from typing import Any

from google import genai
from google.genai import errors, types

from getnet_multi_agent.config import ModelRole, Settings
from getnet_multi_agent.logging_setup import log_event

EMBED_BATCH_SIZE = 50
RETRY_DELAY_SECONDS = 1.0


class BudgetExceeded(Exception):
    """The per-request token budget would be exceeded."""


class LLMUnavailable(Exception):
    """The LLM failed after the allowed retry, or returned an unusable response."""


@dataclass
class CallRecord:
    agent: str
    model: str
    latency_ms: int
    prompt_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    search_requests: int = 0
    cost_usd: float = 0.0
    tokens_estimated: bool = False


@dataclass
class RequestContext:
    request_id: str
    budget: int
    tokens_used: int = 0
    records: list[CallRecord] = field(default_factory=list)


@dataclass
class LLMResult:
    text: str
    content: Any = None
    function_calls: list[Any] = field(default_factory=list)
    grounding_sources: list[tuple[str, str]] = field(default_factory=list)


def compute_cost(role: ModelRole, record: CallRecord, price_search_per_1k: float) -> float:
    """Thinking tokens are billed as output. Search requests are outside usage_metadata."""
    tokens = record.prompt_tokens * role.input_per_m
    tokens += (record.output_tokens + record.thinking_tokens) * role.output_per_m
    return round(tokens / 1_000_000 + record.search_requests * price_search_per_1k / 1000, 8)


def estimate_tokens(contents: Any) -> int:
    if isinstance(contents, str):
        return len(contents) // 4
    total = 0
    for item in contents:
        if isinstance(item, str):
            total += len(item) // 4
        else:
            for part in item.parts or []:
                total += len(part.text or "") // 4
    return total


class LLMClient:
    def __init__(self, settings: Settings, client: Any = None):
        self.settings = settings
        self.client = client or genai.Client(api_key=settings.api_key)
        self._timeout_ms = int(settings.llm_timeout_seconds * 1000)

    def _with_retry(self, call):
        """One retry on 429 or 5xx. Anything else, or a second failure, is LLMUnavailable."""
        for attempt in (1, 2):
            try:
                return call()
            except errors.APIError as exc:
                retryable = exc.code == 429 or (exc.code or 0) >= 500
                if retryable and attempt == 1:
                    time.sleep(RETRY_DELAY_SECONDS)
                    continue
                raise LLMUnavailable(f"API error {exc.code}") from exc
            except Exception as exc:
                raise LLMUnavailable(type(exc).__name__) from exc

    def _check_budget(self, ctx: RequestContext, estimate: int) -> None:
        if ctx.tokens_used + estimate > ctx.budget:
            log_event(
                "budget_exceeded",
                request_id=ctx.request_id,
                tokens_used=ctx.tokens_used,
                estimate=estimate,
                budget=ctx.budget,
            )
            raise BudgetExceeded()

    def _record(self, ctx: RequestContext, role: ModelRole, record: CallRecord) -> None:
        record.cost_usd = compute_cost(role, record, self.settings.price_search_per_1k)
        ctx.records.append(record)
        ctx.tokens_used += record.prompt_tokens + record.output_tokens + record.thinking_tokens
        log_event("llm_call", request_id=ctx.request_id, **record.__dict__)

    def generate(
        self,
        ctx: RequestContext,
        agent: str,
        role: ModelRole,
        contents: Any,
        system: str | None = None,
        tools: list | None = None,
        tool_config: Any = None,
        response_schema: Any = None,
    ) -> LLMResult:
        self._check_budget(ctx, estimate_tokens(contents) + len(system or "") // 4)
        config = types.GenerateContentConfig(
            system_instruction=system,
            thinking_config=types.ThinkingConfig(thinking_level=role.thinking),
            tools=tools,
            tool_config=tool_config,
            response_mime_type="application/json" if response_schema else None,
            response_schema=response_schema,
            http_options=types.HttpOptions(timeout=self._timeout_ms),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        start = time.monotonic()
        response = self._with_retry(
            lambda: self.client.models.generate_content(
                model=role.model, contents=contents, config=config
            )
        )
        usage = response.usage_metadata
        candidate = response.candidates[0] if response.candidates else None
        grounding = getattr(candidate, "grounding_metadata", None)
        record = CallRecord(
            agent=agent,
            model=role.model,
            latency_ms=int((time.monotonic() - start) * 1000),
            prompt_tokens=(usage.prompt_token_count or 0) if usage else 0,
            output_tokens=(usage.candidates_token_count or 0) if usage else 0,
            thinking_tokens=(usage.thoughts_token_count or 0) if usage else 0,
            search_requests=len((grounding.web_search_queries or []) if grounding else []),
        )
        self._record(ctx, role, record)
        # The raw content is kept so thought signatures survive tool-calling turns.
        content = candidate.content if candidate else None
        parts = (content.parts or []) if content else []
        return LLMResult(
            text="".join(p.text for p in parts if p.text and not p.thought),
            content=content,
            function_calls=[p.function_call for p in parts if p.function_call],
            grounding_sources=[
                (chunk.web.uri, chunk.web.title or chunk.web.uri)
                for chunk in ((grounding.grounding_chunks or []) if grounding else [])
                if chunk.web and chunk.web.uri
            ],
        )

    def embed(self, ctx: RequestContext | None, agent: str, texts: list[str]) -> list[list[float]]:
        """Sends Content items: a plain list of strings would be aggregated into one vector."""
        role = self.settings.embedding
        estimate = sum(len(t) // 4 for t in texts)
        if ctx:
            self._check_budget(ctx, estimate)
        vectors: list[list[float]] = []
        start = time.monotonic()
        for i in range(0, len(texts), EMBED_BATCH_SIZE):
            batch = [
                types.Content(parts=[types.Part(text=t)]) for t in texts[i : i + EMBED_BATCH_SIZE]
            ]
            response = self._with_retry(
                lambda b=batch: self.client.models.embed_content(
                    model=role.model,
                    contents=b,
                    config=types.EmbedContentConfig(
                        http_options=types.HttpOptions(timeout=self._timeout_ms)
                    ),
                )
            )
            vectors.extend(e.values for e in response.embeddings)
        if len(vectors) != len(texts):
            raise LLMUnavailable("embedding count mismatch")
        record = CallRecord(
            agent=agent,
            model=role.model,
            latency_ms=int((time.monotonic() - start) * 1000),
            prompt_tokens=estimate,
            tokens_estimated=True,
        )
        target = ctx or RequestContext(request_id="ingestion", budget=0)
        self._record(target, role, record)
        return vectors
