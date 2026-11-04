"""API models and the validated models for LLM output that drives control flow."""
from typing import Literal

from pydantic import BaseModel, Field, StrictStr, field_validator, model_validator


class ChatRequest(BaseModel):
    message: StrictStr
    user_id: StrictStr

    @field_validator("message", "user_id")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value


class Source(BaseModel):
    url: str
    title: str
    origin: Literal["brazil_site", "global_site", "web"]


class RetrievedChunk(BaseModel):
    url: str
    title: str
    similarity: float | None
    match: Literal["vector", "lexical", "both"]
    text: str


class TraceEntry(BaseModel):
    agent: str
    model: str | None = None
    latency_ms: int = 0
    prompt_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    search_requests: int = 0
    cost_usd: float = 0.0
    tokens_estimated: bool = False


class TraceTotal(BaseModel):
    latency_ms: int
    prompt_tokens: int
    output_tokens: int
    thinking_tokens: int
    search_requests: int
    cost_usd: float


class Trace(BaseModel):
    language: Literal["en", "pt"]
    agents: list[TraceEntry]
    retrieved: list[RetrievedChunk] = Field(default_factory=list)
    total: TraceTotal


class ChatResponse(BaseModel):
    answer: str
    route: list[str]
    sources: list[Source]
    ticket_id: str | None = None
    trace: Trace
    request_id: str


class Step(BaseModel):
    agent: Literal["support", "knowledge", "escalation", "refusal"]
    source: Literal["rag", "web"] | None = None
    query: str = ""

    @model_validator(mode="after")
    def knowledge_needs_source(self) -> "Step":
        if self.agent == "knowledge" and self.source is None:
            raise ValueError("a knowledge step must name its source")
        if self.agent != "knowledge":
            self.source = None
        return self

    @property
    def token(self) -> str:
        return f"knowledge:{self.source}" if self.agent == "knowledge" else self.agent


class RoutePlan(BaseModel):
    steps: list[Step] = Field(min_length=1)
    language: Literal["en", "pt"]


class KnowledgeOutput(BaseModel):
    grounded: bool
    answer: str
    citations: list[int] = Field(default_factory=list)
