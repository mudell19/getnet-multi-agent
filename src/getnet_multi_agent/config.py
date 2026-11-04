"""Application settings. Every limit, model and price comes from the environment."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class ModelRole:
    """A model with its thinking level and prices, chosen per task (constitution principle V)."""

    model: str
    thinking: str | None
    input_per_m: float
    output_per_m: float


@dataclass(frozen=True)
class Settings:
    api_key: str
    router: ModelRole
    personality: ModelRole
    answer: ModelRole
    embedding: ModelRole
    price_search_per_1k: float
    max_message_chars: int
    rag_top_k: int
    rag_max_pages: int
    rag_min_similarity: float
    max_tool_iterations: int
    request_token_budget: int
    llm_timeout_seconds: float
    data_dir: Path
    app_rev: str


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}. See .env.example.")
    return value


def load_settings() -> Settings:
    load_dotenv()
    lite = (float(_required("PRICE_LITE_INPUT_PER_M")), float(_required("PRICE_LITE_OUTPUT_PER_M")))
    flash = (float(_required("PRICE_FLASH_INPUT_PER_M")), float(_required("PRICE_FLASH_OUTPUT_PER_M")))
    return Settings(
        api_key=_required("GEMINI_API_KEY"),
        router=ModelRole(_required("GEMINI_ROUTER_MODEL"), _required("GEMINI_ROUTER_THINKING"), *lite),
        personality=ModelRole(
            _required("GEMINI_PERSONALITY_MODEL"), _required("GEMINI_PERSONALITY_THINKING"), *lite
        ),
        answer=ModelRole(_required("GEMINI_MODEL"), _required("GEMINI_MODEL_THINKING"), *flash),
        embedding=ModelRole(
            _required("GEMINI_EMBEDDING_MODEL"), None, float(_required("PRICE_EMBEDDING_PER_M")), 0.0
        ),
        price_search_per_1k=float(_required("PRICE_SEARCH_PER_1K")),
        max_message_chars=int(_required("MAX_MESSAGE_CHARS")),
        rag_top_k=int(_required("RAG_TOP_K")),
        rag_max_pages=int(_required("RAG_MAX_PAGES")),
        rag_min_similarity=float(_required("RAG_MIN_SIMILARITY")),
        max_tool_iterations=int(_required("MAX_TOOL_ITERATIONS")),
        request_token_budget=int(_required("REQUEST_TOKEN_BUDGET")),
        llm_timeout_seconds=float(os.environ.get("LLM_TIMEOUT_SECONDS", "30")),
        data_dir=Path(os.environ.get("DATA_DIR", "data")),
        app_rev=os.environ.get("APP_REV", "dev"),
    )
