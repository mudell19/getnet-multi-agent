"""Structured JSON logs on stdout."""
import json
import logging
import sys

_logger = logging.getLogger("getnet")
if not _logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(_handler)
    _logger.setLevel(logging.INFO)
    _logger.propagate = False


def log_event(event: str, **fields) -> None:
    _logger.info(json.dumps({"event": event, **fields}, ensure_ascii=False, default=str))
