"""Knowledge agent: RAG over Getnet's sites or Google Search grounding, in separate calls."""
from dataclasses import dataclass, field

from google.genai import types
from pydantic import ValidationError

from getnet_multi_agent.llm import LLMClient, LLMUnavailable, RequestContext
from getnet_multi_agent.prompts import knowledge as prompt
from getnet_multi_agent.prompts.common import delimit
from getnet_multi_agent.rag.retriever import Retrieved, Retriever
from getnet_multi_agent.schemas import KnowledgeOutput, Source

MAX_WEB_SOURCES = 5


@dataclass
class KnowledgeResult:
    grounded: bool
    answer: str = ""
    sources: list[Source] = field(default_factory=list)
    retrieved: list[Retrieved] = field(default_factory=list)


def _format_context(retrieved: list[Retrieved]) -> str:
    return "\n\n".join(
        f"[{i}] (from {r.chunk.url})\n{r.chunk.text}" for i, r in enumerate(retrieved, start=1)
    )


def answer_from_rag(
    llm: LLMClient, ctx: RequestContext, retriever: Retriever, query: str, language: str, previous: str
) -> KnowledgeResult:
    retrieved = retriever.retrieve(ctx, query)
    if not retrieved:
        return KnowledgeResult(grounded=False)
    contents = "\n\n".join(
        [
            delimit("retrieved_context", _format_context(retrieved)),
            delimit("previous_step_output", previous or "None."),
            delimit("question", query),
        ]
    )
    result = llm.generate(
        ctx,
        "knowledge",
        llm.settings.answer,
        contents,
        system=prompt.rag_system_prompt(language),
        response_schema=KnowledgeOutput,
    )
    try:
        output = KnowledgeOutput.model_validate_json(result.text)
    except ValidationError as exc:
        raise LLMUnavailable("invalid knowledge output") from exc
    # Code maps citations to URLs, so a source can only be a chunk that was really retrieved.
    cited = [retrieved[n - 1] for n in dict.fromkeys(output.citations) if 1 <= n <= len(retrieved)]
    if not output.grounded or not output.answer.strip() or not cited:
        return KnowledgeResult(grounded=False, retrieved=retrieved)
    sources: dict[str, Source] = {}
    for item in cited:
        sources.setdefault(
            item.chunk.url, Source(url=item.chunk.url, title=item.chunk.title, origin=item.chunk.origin)
        )
    return KnowledgeResult(True, output.answer.strip(), list(sources.values()), retrieved)


def answer_from_web(llm: LLMClient, ctx: RequestContext, query: str, language: str) -> KnowledgeResult:
    """Grounding runs alone here: it is never combined with function calling in one request."""
    result = llm.generate(
        ctx,
        "knowledge",
        llm.settings.answer,
        delimit("question", query),
        system=prompt.web_system_prompt(language),
        tools=[types.Tool(google_search=types.GoogleSearch())],
    )
    sources: dict[str, Source] = {}
    for uri, title in result.grounding_sources:
        sources.setdefault(uri, Source(url=uri, title=title, origin="web"))
    if not result.text.strip() or not sources:
        return KnowledgeResult(grounded=False)
    return KnowledgeResult(True, result.text.strip(), list(sources.values())[:MAX_WEB_SOURCES])
