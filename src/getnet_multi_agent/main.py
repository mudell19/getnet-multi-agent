"""HTTP layer: POST /chat and GET /health."""
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from getnet_multi_agent.config import Settings, load_settings
from getnet_multi_agent.llm import LLMClient
from getnet_multi_agent.logging_setup import log_event
from getnet_multi_agent.orchestrator import Orchestrator
from getnet_multi_agent.rag.ingest import ingest
from getnet_multi_agent.rag.retriever import Retriever
from getnet_multi_agent.rag.store import KnowledgeStore
from getnet_multi_agent.schemas import ChatRequest
from getnet_multi_agent.tools.merchant import MerchantData
from getnet_multi_agent.tools.tickets import TicketStore


def _ingest_safely(settings: Settings, llm: LLMClient, store: KnowledgeStore) -> None:
    """A failed source or embedding call must not stop the service."""
    try:
        ingest(settings, llm, store)
    except Exception as exc:
        log_event("ingest_failed", error=type(exc).__name__, detail=str(exc)[:200])


def _build_runtime(settings: Settings):
    llm = LLMClient(settings)
    store = KnowledgeStore(settings.data_dir / "chroma")
    retriever = Retriever(store, llm, settings.rag_top_k, settings.rag_min_similarity)
    orchestrator = Orchestrator(
        settings, llm, retriever, MerchantData(), TicketStore(settings.data_dir / "tickets" / "tickets.jsonl")
    )

    def start_ingestion() -> None:
        if store.count() == 0:
            threading.Thread(target=_ingest_safely, args=(settings, llm, store), daemon=True).start()

    return orchestrator, (lambda: store.count() > 0), start_ingestion


def create_app(orchestrator=None, is_ready=None) -> FastAPI:
    start_ingestion = None
    if orchestrator is None:
        orchestrator, is_ready, start_ingestion = _build_runtime(load_settings())
    is_ready = is_ready or (lambda: False)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if start_ingestion:
            start_ingestion()
        yield

    app = FastAPI(title="Getnet Multi-Agent Support", lifespan=lifespan)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # The input is left out on purpose: it may hold a card number or CPF.
        details = [
            {"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"]} for e in exc.errors()
        ]
        return JSONResponse({"error": "validation_error", "details": details}, status_code=422)

    @app.post("/chat")
    def chat(request: ChatRequest) -> JSONResponse:
        response = orchestrator.handle(request)
        body = response.model_dump(exclude={"ticket_id"} if response.ticket_id is None else None)
        return JSONResponse(body)

    @app.get("/health")
    def health() -> JSONResponse:
        ready = is_ready()
        return JSONResponse(
            {"status": "ready" if ready else "not_ready"}, status_code=200 if ready else 503
        )

    return app
