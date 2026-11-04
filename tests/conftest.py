from types import SimpleNamespace as NS
import os
from pathlib import Path

import pytest

from getnet_multi_agent.config import ModelRole, Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    os.environ.setdefault("TZ", "America/Sao_Paulo")
    return Settings(
        api_key="test",
        router=ModelRole("router-model", "minimal", 0.30, 2.50),
        personality=ModelRole("personality-model", "minimal", 0.30, 2.50),
        answer=ModelRole("answer-model", "low", 0.75, 3.75),
        embedding=ModelRole("embedding-model", None, 0.20, 0.0),
        price_search_per_1k=14.0,
        max_message_chars=2000,
        rag_top_k=6,
        rag_max_pages=80,
        rag_min_similarity=0.62,
        max_tool_iterations=3,
        request_token_budget=20000,
        llm_timeout_seconds=30.0,
        data_dir=tmp_path,
        app_rev="test",
    )


class StubLLM:
    """Replaces the wrapper: scripted output per agent, recording every call."""

    def __init__(self, settings, script=None):
        self.settings = settings
        self.script = script or {}
        self.calls = []

    def generate(self, ctx, agent, role, contents, system=None, tools=None, tool_config=None, response_schema=None):
        from getnet_multi_agent.llm import CallRecord, LLMResult

        self.calls.append(NS(agent=agent, role=role, contents=contents, system=system, tools=tools, ctx=ctx))
        queue = self.script.get(agent)
        if not queue:
            raise AssertionError(f"Unexpected LLM call for {agent}")
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        ctx.records.append(CallRecord(agent=agent, model=role.model, latency_ms=1, prompt_tokens=10, output_tokens=5, cost_usd=0.001))
        if isinstance(item, LLMResult):
            return item
        return LLMResult(text=item)

    def agents_called(self):
        return [c.agent for c in self.calls]
