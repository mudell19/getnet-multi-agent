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
