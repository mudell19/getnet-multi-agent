import pytest
from fastapi.testclient import TestClient

from getnet_multi_agent.main import create_app
from getnet_multi_agent.orchestrator import Orchestrator


@pytest.fixture
def client(settings):
    return TestClient(create_app(Orchestrator(settings), is_ready=lambda: True))


LONG = "x" * 2001


def test_R1_R4_chat_accepts_exact_payload_and_returns_contract(client):
    r = client.post("/chat", json={"message": LONG, "user_id": "cliente1988"})
    assert r.status_code == 200
    body = r.json()
    assert {"answer", "route", "sources", "trace", "request_id"} <= body.keys()
    assert "ticket_id" not in body


def test_R2_accepts_any_non_empty_user_id(client):
    r = client.post("/chat", json={"message": LONG, "user_id": "some_user_identifier"})
    assert r.status_code == 200


@pytest.mark.parametrize(
    "payload",
    [
        {"message": "hi"},
        {"user_id": "a"},
        {"message": "", "user_id": "a"},
        {"message": "hi", "user_id": "   "},
        {"message": 5, "user_id": "a"},
    ],
)
def test_R2_R3_validation_errors_are_json(client, payload):
    r = client.post("/chat", json=payload)
    assert r.status_code == 422 and r.json()["error"] == "validation_error"


def test_R3_malformed_body_is_json_and_does_not_echo_input(client):
    r = client.post("/chat", content="{bad 4111111111111111")
    assert r.status_code == 422 and "4111" not in r.text


def test_R5_health_reports_readiness(settings):
    state = {"ready": False}
    client = TestClient(create_app(Orchestrator(settings), is_ready=lambda: state["ready"]))
    assert client.get("/health").status_code == 503
    state["ready"] = True
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ready"


def test_R6_requests_are_stateless(client):
    a = client.post("/chat", json={"message": LONG, "user_id": "a"}).json()
    b = client.post("/chat", json={"message": LONG, "user_id": "a"}).json()
    assert a["request_id"] != b["request_id"] and a["trace"]["total"]["prompt_tokens"] == 0
