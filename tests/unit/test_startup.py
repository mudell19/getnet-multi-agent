from fastapi.testclient import TestClient

import getnet_multi_agent.main as main


class FakeStore:
    def __init__(self, path):
        self.value = FakeStore.initial

    def count(self):
        return self.value


def run_startup(monkeypatch, settings, initial):
    FakeStore.initial = initial
    calls = []
    monkeypatch.setattr(main, "KnowledgeStore", FakeStore)
    monkeypatch.setattr(main, "LLMClient", lambda s: None)
    monkeypatch.setattr(main, "load_settings", lambda: settings)
    monkeypatch.setattr(main, "ingest", lambda *a, **k: calls.append(a))
    with TestClient(main.create_app()) as client:
        status = client.get("/health").status_code
    return calls, status


def test_R27_startup_ingests_when_collection_is_empty(monkeypatch, settings):
    calls, status = run_startup(monkeypatch, settings, 0)
    assert calls and status == 503


def test_R27_startup_does_not_ingest_when_collection_exists(monkeypatch, settings):
    calls, status = run_startup(monkeypatch, settings, 5)
    assert calls == [] and status == 200


def test_R28_ingestion_failure_does_not_stop_the_service(monkeypatch, settings):
    def boom(*args, **kwargs):
        raise RuntimeError("source down")

    monkeypatch.setattr(main, "ingest", boom)
    main._ingest_safely(settings, None, None)
