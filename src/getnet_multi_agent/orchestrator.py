"""Runs guardrails, the Router's steps and Personality using direct function calls."""
import time
import uuid
from dataclasses import dataclass, field

from getnet_multi_agent.agents import escalation, knowledge, personality, support
from getnet_multi_agent.agents.router import route as run_router
from getnet_multi_agent.config import Settings
from getnet_multi_agent.guardrails import REFUSALS, run_guardrails
from getnet_multi_agent.llm import BudgetExceeded, LLMClient, LLMUnavailable, RequestContext
from getnet_multi_agent.logging_setup import log_event
from getnet_multi_agent.rag.retriever import Retrieved, Retriever
from getnet_multi_agent.schemas import (
    ChatRequest,
    ChatResponse,
    RetrievedChunk,
    Source,
    Step,
    Trace,
    TraceEntry,
    TraceTotal,
)
from getnet_multi_agent.tools.merchant import MerchantData
from getnet_multi_agent.tools.tickets import TicketStore

PARTIAL_NOTES = {
    "en": "I could not find confirmed information for the other part of your question.",
    "pt": "Não encontrei informação confirmada para a outra parte da sua pergunta.",
}
SOURCE_HEADERS = {"en": "Sources:", "pt": "Fontes:"}
ACCOUNT_SOURCE = {"en": "Your Getnet account data", "pt": "Dados da sua conta Getnet"}
GLOBAL_NOTES = {
    "en": "Note: information from Getnet's global site (www.getnet.net) is not confirmed for Brazil.",
    "pt": "Atenção: informações do site global da Getnet (www.getnet.net) não são confirmadas para o Brasil.",
}
NO_VOICE_REASONS = {"llm_failure", "budget_exceeded"}


def build_trace(ctx: RequestContext, language: str, started: float, guard_ms: int, retrieved=()) -> Trace:
    agents: dict[str, TraceEntry] = {"guardrails": TraceEntry(agent="guardrails", latency_ms=guard_ms)}
    for rec in ctx.records:
        entry = agents.setdefault(rec.agent, TraceEntry(agent=rec.agent, model=rec.model))
        # A Knowledge step makes an embedding call and a generation call: show the generation model.
        if not rec.tokens_estimated:
            entry.model = rec.model
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


@dataclass
class RunState:
    language: str
    drafts: list[str] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    route: list[str] = field(default_factory=list)
    retrieved: list[Retrieved] = field(default_factory=list)
    used_account_data: bool = False
    ticket_id: str | None = None
    escalation_reason: str | None = None


def attach_sources(answer: str, state: RunState) -> str:
    """Runs after Personality, so sources and the Brazil caveat cannot be altered by the LLM."""
    lines = [f"- {s.title} ({s.url})" for s in state.sources]
    if state.used_account_data:
        lines.insert(0, f"- {ACCOUNT_SOURCE[state.language]}")
    if lines:
        answer = f"{answer}\n\n{SOURCE_HEADERS[state.language]}\n" + "\n".join(lines)
    if any(s.origin == "global_site" for s in state.sources):
        answer = f"{answer}\n\n{GLOBAL_NOTES[state.language]}"
    return answer


class Orchestrator:
    def __init__(
        self,
        settings: Settings,
        llm: LLMClient,
        retriever: Retriever,
        merchants: MerchantData,
        tickets: TicketStore,
    ):
        self.settings = settings
        self.llm = llm
        self.retriever = retriever
        self.merchants = merchants
        self.tickets = tickets

    def _escalate(self, ctx, state: RunState, request: ChatRequest, masked: str, reason: str) -> None:
        state.route.append("escalation")
        state.escalation_reason = reason
        draft, state.ticket_id = escalation.escalate(
            self.tickets, ctx.request_id, request.user_id, masked, reason, state.route, state.language
        )
        state.drafts.append(draft)

    def _run_step(self, ctx, state: RunState, step: Step, request: ChatRequest, masked: str) -> bool:
        """Runs one step. Returns False when the sequence must stop."""
        query = step.query.strip() or masked
        previous = "\n\n".join(state.drafts)
        if step.agent == "refusal":
            state.route.append("refusal")
            state.drafts = [REFUSALS[state.language]]
            return False
        if step.agent == "escalation":
            self._escalate(ctx, state, request, masked, "explicit_request")
            return False
        state.route.append(step.token)
        if step.agent == "support":
            state.drafts.append(
                support.run(self.llm, ctx, self.merchants, request.user_id, query, state.language)
            )
            state.used_account_data = True
            return True
        if step.source == "rag":
            result = knowledge.answer_from_rag(
                self.llm, ctx, self.retriever, query, state.language, previous
            )
        else:
            result = knowledge.answer_from_web(self.llm, ctx, query, state.language)
        state.retrieved.extend(result.retrieved)
        if result.grounded:
            state.drafts.append(result.answer)
            state.sources.extend(s for s in result.sources if s.url not in {x.url for x in state.sources})
        elif state.drafts:
            # Earlier answers are kept and no handoff happens (constitution principle III).
            state.drafts.append(PARTIAL_NOTES[state.language])
        else:
            self._escalate(ctx, state, request, masked, "no_grounding")
            return False
        return True

    def _run_steps(self, ctx, state: RunState, request: ChatRequest, masked: str) -> None:
        try:
            plan = run_router(self.llm, ctx, masked, request.user_id)
            state.language = plan.language
            for step in plan.steps:
                if not self._run_step(ctx, state, step, request, masked):
                    return
        except BudgetExceeded:
            self._escalate(ctx, state, request, masked, "budget_exceeded")
        except LLMUnavailable:
            self._escalate(ctx, state, request, masked, "llm_failure")
        except support.ToolFailure:
            self._escalate(ctx, state, request, masked, "tool_failure")

    def handle(self, request: ChatRequest) -> ChatResponse:
        started = time.monotonic()
        request_id = str(uuid.uuid4())
        ctx = RequestContext(request_id=request_id, budget=self.settings.request_token_budget)
        guard = run_guardrails(request.message, self.settings.max_message_chars)
        guard_ms = int((time.monotonic() - started) * 1000)
        state = RunState(language=guard.language)

        if guard.refusal:
            # Deterministic refusals make no LLM call and skip Personality.
            state.route.append("refusal")
            answer = guard.refusal
        else:
            self._run_steps(ctx, state, request, guard.masked_message)
            draft = "\n\n".join(state.drafts)
            if state.escalation_reason in NO_VOICE_REASONS:
                answer = draft
            else:
                answer = personality.apply_voice(self.llm, ctx, draft, state.language, state.ticket_id)
            answer = attach_sources(answer, state)

        trace = build_trace(
            ctx,
            state.language,
            started,
            guard_ms,
            [
                RetrievedChunk(
                    url=r.chunk.url,
                    title=r.chunk.title,
                    similarity=r.similarity,
                    match=r.match,
                    text=r.chunk.text,
                )
                for r in state.retrieved
            ],
        )
        log_event(
            "request_complete",
            request_id=request_id,
            app_rev=self.settings.app_rev,
            user_id=request.user_id,
            message=guard.masked_message,
            route=state.route,
            language=state.language,
            refusal_reason=guard.refusal_reason,
            escalation_reason=state.escalation_reason,
            ticket_id=state.ticket_id,
            answer_chars=len(answer),
            total=trace.total.model_dump(),
        )
        return ChatResponse(
            answer=answer,
            route=state.route,
            sources=state.sources,
            ticket_id=state.ticket_id,
            trace=trace,
            request_id=request_id,
        )
