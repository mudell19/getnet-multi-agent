"""Router agent: returns the ordered steps and the user's language."""
from pydantic import ValidationError

from getnet_multi_agent.llm import LLMClient, LLMUnavailable, RequestContext
from getnet_multi_agent.prompts import router as prompt
from getnet_multi_agent.prompts.common import delimit
from getnet_multi_agent.schemas import RoutePlan


def route(llm: LLMClient, ctx: RequestContext, message: str, user_id: str) -> RoutePlan:
    contents = "\n".join([delimit("current_merchant_id", user_id), delimit("user_message", message)])
    result = llm.generate(
        ctx,
        "router",
        llm.settings.router,
        contents,
        system=prompt.system_prompt(),
        response_schema=RoutePlan,
    )
    try:
        return RoutePlan.model_validate_json(result.text)
    except ValidationError as exc:
        raise LLMUnavailable("invalid router output") from exc
