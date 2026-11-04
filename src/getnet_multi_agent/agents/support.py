"""Customer Support agent: function calling over merchant tools. user_id is injected by code."""
import json

from google.genai import types

from getnet_multi_agent.llm import LLMClient, LLMUnavailable, RequestContext
from getnet_multi_agent.prompts import support as prompt
from getnet_multi_agent.prompts.common import delimit
from getnet_multi_agent.tools.merchant import MerchantData

NOT_FOUND = {
    "en": "I couldn't find a merchant account for the id you provided, so I can't show settlements or card machine data.",
    "pt": "Não encontrei uma conta de estabelecimento para o id informado, então não consigo mostrar recebimentos ou dados da maquininha.",
}

# The declarations have no parameters, so the LLM has no way to choose a user_id.
TOOLS = [
    types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="get_receivables",
                description="Returns settlement dates and amounts of the current merchant's sales.",
                parameters=types.Schema(type="OBJECT", properties={}),
            ),
            types.FunctionDeclaration(
                name="get_terminal_status",
                description="Returns the current merchant's card machine connectivity, last errors and suggested actions.",
                parameters=types.Schema(type="OBJECT", properties={}),
            ),
        ]
    )
]


class ToolFailure(Exception):
    """A tool reported a failure, which triggers escalation."""


def _tool_config(mode: str) -> types.ToolConfig:
    return types.ToolConfig(function_calling_config=types.FunctionCallingConfig(mode=mode))


def run(llm: LLMClient, ctx: RequestContext, merchants: MerchantData, user_id: str, query: str, language: str) -> str:
    registry = {
        "get_receivables": lambda: merchants.get_receivables(user_id),
        "get_terminal_status": lambda: merchants.get_terminal_status(user_id),
    }
    contents = [types.Content(role="user", parts=[types.Part(text=delimit("question", query))])]
    limit = llm.settings.max_tool_iterations
    for iteration in range(limit + 1):
        # The first turn must use a tool. The turn after the last allowed iteration must answer.
        mode = "ANY" if iteration == 0 else "NONE" if iteration == limit else "AUTO"
        result = llm.generate(
            ctx,
            "support",
            llm.settings.answer,
            contents,
            system=prompt.system_prompt(language),
            tools=TOOLS,
            tool_config=_tool_config(mode),
        )
        if not result.function_calls:
            if result.text.strip():
                return result.text.strip()
            raise LLMUnavailable("empty support answer")
        # The complete model content goes back unchanged, keeping thought signatures.
        contents.append(result.content)
        parts = []
        for call in result.function_calls:
            tool = registry.get(call.name)
            output = tool() if tool else {"status": "error", "error": "unknown_tool"}
            if output["status"] == "error":
                raise ToolFailure(output.get("error", "tool_error"))
            if output["status"] == "not_found":
                return NOT_FOUND[language]
            parts.append(
                types.Part.from_function_response(
                    name=call.name, response={"untrusted_data": json.loads(json.dumps(output))}
                )
            )
        contents.append(types.Content(role="user", parts=parts))
    raise LLMUnavailable("support did not produce an answer")
