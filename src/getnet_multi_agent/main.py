"""HTTP layer: POST /chat and GET /health."""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from getnet_multi_agent.config import load_settings
from getnet_multi_agent.orchestrator import Orchestrator
from getnet_multi_agent.schemas import ChatRequest


def create_app(orchestrator=None, is_ready=None) -> FastAPI:
    app = FastAPI(title="Getnet Multi-Agent Support")
    orchestrator = orchestrator or Orchestrator(load_settings())
    is_ready = is_ready or (lambda: False)

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
