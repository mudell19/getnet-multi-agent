"""create_ticket tool: appends handoffs to a local JSONL file in the data volume."""
import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from getnet_multi_agent.logging_setup import log_event


class TicketStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def create_ticket(
        self, request_id: str, user_id: str, masked_message: str, reason: str, route: list[str], language: str
    ) -> dict:
        ticket_id = f"TCK-{uuid.uuid4().hex[:8].upper()}"
        record = {
            "ticket_id": ticket_id,
            "request_id": request_id,
            "user_id": user_id,
            "message": masked_message,
            "reason": reason,
            "route": list(route),
            "language": language,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock, self.path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as exc:
            log_event("ticket_write_failed", request_id=request_id, error=type(exc).__name__)
            return {"status": "error", "error": "ticket_write_failed"}
        log_event("ticket_created", request_id=request_id, ticket_id=ticket_id, reason=reason)
        return {"status": "ok", "ticket_id": ticket_id}
