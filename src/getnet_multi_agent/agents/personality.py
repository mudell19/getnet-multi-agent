"""Personality agent: applies the brand voice. It may not add facts."""
import re

from getnet_multi_agent.llm import BudgetExceeded, LLMClient, LLMUnavailable, RequestContext
from getnet_multi_agent.logging_setup import log_event
from getnet_multi_agent.prompts import personality as prompt
from getnet_multi_agent.prompts.common import delimit


def _numbers(text: str) -> set[str]:
    return {n.lstrip("0") or "0" for n in re.findall(r"\d+", text)}


def is_acceptable(output: str, draft: str, ticket_id: str | None) -> bool:
    """Rejects empty output, numbers absent from the draft, and a lost ticket id."""
    if not output.strip():
        return False
    if ticket_id and ticket_id not in output:
        return False
    return _numbers(output) <= _numbers(draft)


def apply_voice(
    llm: LLMClient, ctx: RequestContext, draft: str, language: str, ticket_id: str | None
) -> str:
    """Returns the rewritten answer, or the agent draft if this step fails."""
    try:
        result = llm.generate(
            ctx,
            "personality",
            llm.settings.personality,
            delimit("draft", draft),
            system=prompt.system_prompt(language),
        )
    except (LLMUnavailable, BudgetExceeded) as exc:
        log_event("personality_failed", request_id=ctx.request_id, error=type(exc).__name__)
        return draft
    if not is_acceptable(result.text, draft, ticket_id):
        log_event("personality_rejected", request_id=ctx.request_id)
        return draft
    return result.text.strip()
