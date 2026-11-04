from types import SimpleNamespace as NS

import pytest

from getnet_multi_agent.llm import RequestContext
from getnet_multi_agent.rag.chunker import Chunk
from getnet_multi_agent.rag.crawler import CrawlResult, Page
from getnet_multi_agent.rag.glossary import matched_groups
from getnet_multi_agent.rag.ingest import build_chunks, ingest
from getnet_multi_agent.rag.retriever import Retriever
from getnet_multi_agent.rag.store import KnowledgeStore


def chunk(i, text="body", heading="h"):
    return Chunk(f"c{i}", f"https://x/{i}", "T", "brazil_site", heading, text)


class FakeLLM:
    def __init__(self, vector=(1.0, 0.0)):
        self.vector = list(vector)
        self.texts = []

    def embed(self, ctx, agent, texts):
        self.texts.extend(texts)
        return [self.vector for _ in texts]


@pytest.fixture
def store(tmp_path):
    return KnowledgeStore(tmp_path / "chroma")


def ctx():
    return RequestContext(request_id="r", budget=1000)


def test_R30_vector_search_uses_cosine_with_similarity_one_minus_distance(store):
    store.replace([chunk(1), chunk(2)], [[1.0, 0.0], [0.0, 1.0]])
    hits = dict((c.id, s) for c, s in store.query([1.0, 0.0], 2))
    assert hits["c1"] == pytest.approx(1.0, abs=1e-5)
    assert hits["c2"] == pytest.approx(0.0, abs=1e-5)


def test_R29_retrieves_portuguese_content_through_english_alias(store):
    store.replace(
        [chunk(1, "O que é antecipação de vendas?"), chunk(2, "Outro assunto")],
        [[0.0, 1.0], [1.0, 0.0]],
    )
    llm = FakeLLM()
    results = Retriever(store, llm, 6, 0.62).retrieve(ctx(), "How does receivables advance work?")
    assert results[0].chunk.id == "c1" and results[0].match in ("lexical", "both")
    assert "antecipação" in llm.texts[0]


@pytest.mark.parametrize(
    "pair",
    [
        ("Get Clássica", "Get Classic"),
        ("Link de Pagamento", "Payment Link"),
        ("antecipação", "receivables advance"),
        ("crediário", "installments"),
        ("parcelas", "installments"),
    ],
)
def test_R29_glossary_contains_the_required_aliases(pair):
    assert matched_groups(pair[0]) == matched_groups(pair[1]) != []


def test_R30_chunk_below_threshold_without_glossary_match_does_not_qualify(store):
    store.replace([chunk(1, "unrelated")], [[0.5, 0.866]])
    assert Retriever(store, FakeLLM(), 6, 0.62).retrieve(ctx(), "capital of Mongolia") == []


def test_R30_chunk_at_threshold_qualifies(store):
    store.replace([chunk(1, "related")], [[1.0, 0.0]])
    results = Retriever(store, FakeLLM(), 6, 0.62).retrieve(ctx(), "capital of Mongolia")
    assert results[0].match == "vector" and results[0].similarity == pytest.approx(1.0, abs=1e-5)


def test_R51_results_never_exceed_top_k(store):
    chunks = [chunk(i, "crediário parcelas") for i in range(10)]
    store.replace(chunks, [[1.0, 0.0]] * 10)
    assert len(Retriever(store, FakeLLM(), 4, 0.62).retrieve(ctx(), "crediário")) == 4


def test_R28_empty_store_returns_no_context_without_llm_call(store):
    llm = FakeLLM()
    assert Retriever(store, llm, 6, 0.62).retrieve(ctx(), "pix") == [] and llm.texts == []


def page(url, origin, body):
    return Page(url, url, f"<html><body><h2>{body}</h2><p>Long enough body for {body}</p></body></html>", origin, "T")


class FakeCrawler:
    def __init__(self, pages):
        self.pages = pages

    def crawl(self):
        return CrawlResult(self.pages, [])


def test_R27_ingest_persists_and_survives_a_new_store_instance(settings, tmp_path):
    store = KnowledgeStore(tmp_path / "kb")
    pages = [page("https://a/1", "brazil_site", "one"), page("https://b/en", "global_site", "two")]
    assert ingest(settings, FakeLLM(), store, crawler=FakeCrawler(pages)) == 2
    del store
    assert KnowledgeStore(tmp_path / "kb").count() == 2


def test_R27_failed_refresh_keeps_current_knowledge_base(settings, store):
    store.replace([chunk(1)], [[1.0, 0.0]])
    assert ingest(settings, FakeLLM(), store, crawler=FakeCrawler([])) == 0
    assert store.count() == 1


def test_R27_interrupted_build_is_not_treated_as_complete(tmp_path):
    store = KnowledgeStore(tmp_path / "kb")
    store.client.create_collection("knowledge_base_building")
    assert KnowledgeStore(tmp_path / "kb").count() == 0
    assert "knowledge_base_building" not in {c.name for c in store.client.list_collections()}


def test_R25_repetition_is_computed_per_host():
    shared = "<p>Footer-like repeated sentence on the host</p>"
    pages = [
        Page(f"https://a/{i}", f"https://a/{i}", f"<html><body><h2>P{i}</h2><p>Unique content number {i} here</p>{shared}</body></html>", "brazil_site", "T")
        for i in range(5)
    ]
    assert all("repeated sentence" not in c.text for c in build_chunks(pages))
