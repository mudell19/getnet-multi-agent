"""Runs guardrails, the Router's steps and Personality using direct function calls."""
import time
import uuid

from getnet_multi_agent.config import Settings
from getnet_multi_agent.guardrails import run_guardrails
from getnet_multi_agent.llm import RequestContext
from getnet_multi_agent.logging_setup import log_event
from getnet_multi_agent.schemas import ChatRequest, ChatResponse, Trace, TraceEntry, TraceTotal


def build_trace(ctx: RequestContext, language: str, started: float, guard_ms: int, retrieved=()) -> Trace:
    agents: dict[str, TraceEntry] = {"guardrails": TraceEntry(agent="guardrails", latency_ms=guard_ms)}
    for rec in ctx.records:
        entry = agents.setdefault(rec.agent, TraceEntry(agent=rec.agent, model=rec.model))
        entry.latency_ms += rec.latency_ms
        entry.prompt_tokens += rec.prompt_tokens
        entry.output_tokens += rec.output_tokens
        entry.thinking_tokens += rec.thinking_tokens
        entry.search_requests += rec.search_requests
        entry.cost_usd = round(entry.cost_usd + rec.cost_usd, 8)
        entry.tokens_estimated = entry.tokens_estimated or rec.tokens_estimated
    entries = list(agents.values())
    total = TraceTotal(
        latency_ms=int((time.monotonic() - started) * 1000),
        prompt_tokens=sum(e.prompt_tokens for e in entries),
        output_tokens=sum(e.output_tokens for e in entries),
        thinking_tokens=sum(e.thinking_tokens for e in entries),
        search_requests=sum(e.search_requests for e in entries),
        cost_usd=round(sum(e.cost_usd for e in entries), 8),
    )
    return Trace(language=language, agents=entries, retrieved=list(retrieved), total=total)


class Orchestrator:
    def __init__(self, settings: Settings):
        self.settings = settings

    def handle(self, request: ChatRequest) -> ChatResponse:
        started = time.monotonic()
        request_id = str(uuid.uuid4())
        ctx = RequestContext(request_id=request_id, budget=self.settings.request_token_budget)
        guard = run_guardrails(request.message, self.settings.max_message_chars)
        guard_ms = int((time.monotonic() - started) * 1000)
        answer = guard.refusal or "Service starting."
        response = ChatResponse(
            answer=answer,
            route=["refusal"],
            sources=[],
            trace=build_trace(ctx, guard.language, started, guard_ms),
            request_id=request_id,
        )
        log_event("request_complete", request_id=request_id, route=response.route)
        return response
