import json
from pathlib import Path

from evals.run import gate, load_dataset, render_report, score_case, summarize

ROOT = Path(__file__).resolve().parents[2]


def case(**assertions):
    return {"id": "X", "category": "official", "message": "m", "user_id": "u", "expected_route": ["support"], "assertions": assertions}


def body(**kw):
    return {"route": ["support"], "answer": "the answer", "sources": [], "trace": {"retrieved": [], "total": {"cost_usd": 0.01}}, **kw}


def test_R56_dataset_holds_official_compound_and_adversarial_cases():
    cases = load_dataset(None)
    ids = {c["id"] for c in cases}
    assert {f"S{i}" for i in range(1, 11)} <= ids and "C1" in ids
    for c in cases:
        assert c["expected_route"] and "assertions" in c
    texts = json.dumps(cases, ensure_ascii=False)
    assert "4111 1111" in texts and "cliente2000" in texts and "cliente_injection" in texts
    assert "Ignore all previous" in texts and "poem" in texts


def test_R56_official_rag_scenarios_assert_fact_in_answer_and_context():
    for c in load_dataset("S1,S4,S6,S9,S10"):
        assert c["assertions"]["answer_all"] and c["assertions"]["context_all"] and c["assertions"]["source_contains"]


def test_R57_scoring_checks_route_answer_context_and_forbidden_terms():
    assert score_case(case(), body()) == []
    assert score_case(case(), body(route=["refusal"]))[0].startswith("route")
    assert score_case(case(answer_all=[["missing"]]), body())[0].startswith("answer")
    assert score_case(case(context_all=[["x"]]), body())[0].startswith("context")
    assert score_case(case(answer_none=["answer"]), body())[0].startswith("forbidden")
    assert score_case(case(citation=True), body())[0].startswith("citation")
    assert score_case(case(ticket=True), body())[0].startswith("ticket")


def test_R57_report_has_all_metrics():
    results = [{"case": case(), "body": body(), "failures": [], "latency": 1.0}]
    summary = summarize(results)
    report = render_report(results, summary, {"routing_accuracy": 0.9, "citation_rate": 0.9, "correct_refusal_rate": 0.9, "assertion_pass_rate": 0.9}, 3)
    for text in ("routing_accuracy", "citation_rate", "correct_refusal_rate", "assertion_pass_rate", "p50", "p95", "average cost", "total cost"):
        assert text in report


def test_R58_gate_reports_each_metric_below_threshold():
    assert gate({"routing_accuracy": 0.5}, {"routing_accuracy": 0.9})
    assert gate({"routing_accuracy": 0.95}, {"routing_accuracy": 0.9}) == []
