"""Support tools over simulated merchant data. Each returns a structured result and handles failures."""
import json
from datetime import timedelta
from pathlib import Path

from getnet_multi_agent.logging_setup import log_event
from getnet_multi_agent.prompts.common import today

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "merchants.json"


def _date(offset_days: int) -> str:
    return (today() + timedelta(days=offset_days)).isoformat()


class MerchantData:
    def __init__(self, path: Path = DEFAULT_PATH):
        self.path = path

    def _merchant(self, user_id: str) -> dict | None:
        return json.loads(self.path.read_text(encoding="utf-8")).get(user_id)

    def get_receivables(self, user_id: str) -> dict:
        try:
            merchant = self._merchant(user_id)
            if merchant is None:
                return {"status": "not_found"}
            return {
                "status": "ok",
                "currency": "BRL",
                "receivables": [
                    {
                        "sale_date": _date(r["sale_offset_days"]),
                        "settlement_date": _date(r["settlement_offset_days"]),
                        "amount": r["amount"],
                        "payment_method": r["payment_method"],
                    }
                    for r in merchant["receivables"]
                ],
            }
        except (OSError, ValueError, KeyError) as exc:
            log_event("tool_failed", tool="get_receivables", error=type(exc).__name__)
            return {"status": "error", "error": "merchant_data_unavailable"}

    def get_terminal_status(self, user_id: str) -> dict:
        try:
            merchant = self._merchant(user_id)
            if merchant is None:
                return {"status": "not_found"}
            terminal = merchant["terminal"]
            return {
                "status": "ok",
                "model": terminal["model"],
                "connectivity": terminal["connectivity"],
                "last_seen_date": _date(terminal["last_seen_offset_days"]),
                "last_errors": [
                    {
                        "date": _date(e["offset_days"]),
                        "code": e["code"],
                        "message": e["message"],
                        "suggested_action": e["suggested_action"],
                    }
                    for e in terminal["last_errors"]
                ],
                "suggested_actions": terminal["suggested_actions"],
            }
        except (OSError, ValueError, KeyError) as exc:
            log_event("tool_failed", tool="get_terminal_status", error=type(exc).__name__)
            return {"status": "error", "error": "merchant_data_unavailable"}
