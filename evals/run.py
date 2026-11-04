"""Runs evals/dataset.jsonl against the live API, writes evals/report.md, and gates on thresholds."""
import argparse
import json
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
CONCURRENCY = 3
REQUEST_TIMEOUT_SECONDS = 120


def score_case(case: dict, body: dict) -> list[str]:
    """Returns failed assertions, each prefixed with the kind of check."""
    a = case["assertions"]
    failures = []
    if body.get("route") != case["expected_route"]:
        failures.append(f"route: got {body.get('route')}")
    answer = body.get("answer", "").lower()
    context = " ".join(c["text"] for c in body.get("trace", {}).get("retrieved", [])).lower()
    sources = body.get("sources", [])
    for group in a.get("answer_all", []):
        if not any(term.lower() in answer for term in group):
            failures.append(f"answer: missing {group}")
    for group in a.get("context_all", []):
        if not any(term.lower() in context for term in group):
            failures.append(f"context: missing {group}")
    for term in a.get("answer_none", []):
        if term.lower() in json.dumps(body, ensure_ascii=False).lower():
            failures.append(f"forbidden: {term}")
    if a.get("citation") and not sources:
        failures.append("citation: no sources")
    if a.get("source_contains") and not any(a["source_contains"] in s["url"] for s in sources):
        failures.append(f"citation: no source matching {a['source_contains']}")
    if a.get("ticket") and not body.get("ticket_id"):
        failures.append("ticket: no ticket_id")
    return failures


def run_one(client: httpx.Client, base_url: str, case: dict) -> dict:
    start = time.monotonic()
    try:
        response = client.post(
            f"{base_url}/chat", json={"message": case["message"], "user_id": case["user_id"]}
        )
        body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        body = {"route": None, "answer": "", "error": type(exc).__name__}
    latency = time.monotonic() - start
    return {"case": case, "body": body, "failures": score_case(case, body), "latency": latency}


def _rate(items: list[bool]) -> float:
    return sum(items) / len(items) if items else 1.0


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(int(len(ordered) * fraction), len(ordered) - 1)] if ordered else 0.0


def summarize(results: list[dict]) -> dict:
    latencies = [r["latency"] for r in results]
    costs = [r["body"].get("trace", {}).get("total", {}).get("cost_usd", 0.0) for r in results]
    cited = [r for r in results if r["case"]["assertions"].get("citation")]
    refused = [r for r in results if r["case"]["assertions"].get("refusal")]
    return {
        "routing_accuracy": _rate([r["body"].get("route") == r["case"]["expected_route"] for r in results]),
        "citation_rate": _rate([not [f for f in r["failures"] if f.startswith("citation")] for r in cited]),
        "correct_refusal_rate": _rate([r["body"].get("route") == ["refusal"] and not r["failures"] for r in refused]),
        "assertion_pass_rate": _rate([not r["failures"] for r in results]),
        "p50_latency_s": statistics.median(latencies) if latencies else 0.0,
        "p95_latency_s": _percentile(latencies, 0.95),
        "avg_cost_usd": sum(costs) / len(costs) if costs else 0.0,
        "total_cost_usd": sum(costs),
    }


def thresholds_from_env() -> dict:
    return {
        "routing_accuracy": float(os.environ.get("EVAL_MIN_ROUTING_ACCURACY", "0.9")),
        "citation_rate": float(os.environ.get("EVAL_MIN_CITATION_RATE", "0.9")),
        "correct_refusal_rate": float(os.environ.get("EVAL_MIN_REFUSAL_RATE", "0.9")),
        "assertion_pass_rate": float(os.environ.get("EVAL_MIN_ASSERTION_RATE", "0.9")),
    }


def gate(summary: dict, thresholds: dict) -> list[str]:
    return [f"{k}: {summary[k]:.3f} < {v:.3f}" for k, v in thresholds.items() if summary[k] < v]


def render_report(results: list[dict], summary: dict, thresholds: dict, repeats: int) -> str:
    breaches = gate(summary, thresholds)
    lines = [
        "# Evaluation Report",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S %z')}. Each case ran {repeats} time(s), for {len(results)} requests.",
        "",
        f"**Gate: {'FAIL' if breaches else 'PASS'}**",
        "",
        "| Metric | Value | Minimum |",
        "|--------|-------|---------|",
    ]
    for key in ("routing_accuracy", "citation_rate", "correct_refusal_rate", "assertion_pass_rate"):
        lines.append(f"| {key} | {summary[key]:.1%} | {thresholds[key]:.0%} |")
    lines += [
        f"| p50 latency | {summary['p50_latency_s']:.2f} s | |",
        f"| p95 latency | {summary['p95_latency_s']:.2f} s | |",
        f"| average cost per request | ${summary['avg_cost_usd']:.5f} | |",
        f"| total cost of this run | ${summary['total_cost_usd']:.4f} | |",
        "",
        "## Cases",
        "",
        "| Case | Category | Expected route | Passed | Routes seen |",
        "|------|----------|----------------|--------|-------------|",
    ]
    by_case: dict[str, list[dict]] = {}
    for result in results:
        by_case.setdefault(result["case"]["id"], []).append(result)
    for case_id, runs in by_case.items():
        case = runs[0]["case"]
        passed = sum(not r["failures"] for r in runs)
        routes = sorted({" > ".join(r["body"].get("route") or ["none"]) for r in runs})
        lines.append(
            f"| {case_id} | {case['category']} | {' > '.join(case['expected_route'])} | {passed}/{len(runs)} | {'; '.join(routes)} |"
        )
    failed = [r for r in results if r["failures"]]
    if failed:
        lines += ["", "## Failures", ""]
        for r in failed:
            excerpt = " ".join(r["body"].get("answer", "").split())[:200].replace("|", "/")
            lines.append(f"- **{r['case']['id']}**: {'; '.join(r['failures'])}. Answer: {excerpt}")
    return "\n".join(lines) + "\n"


def load_dataset(only: str | None) -> list[dict]:
    cases = [json.loads(l) for l in (ROOT / "dataset.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    if only:
        selected = set(only.split(","))
        cases = [c for c in cases if c["id"] in selected or c["category"] in selected]
    return cases


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.environ.get("EVAL_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--repeats", type=int, default=int(os.environ.get("EVAL_REPEATS", "3")))
    parser.add_argument("--only", help="comma-separated case ids or categories")
    parser.add_argument("--report", default=str(ROOT / "report.md"))
    args = parser.parse_args()

    cases = load_dataset(args.only)
    with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client, ThreadPoolExecutor(CONCURRENCY) as pool:
        results = list(
            pool.map(lambda c: run_one(client, args.base_url, c), [c for c in cases for _ in range(args.repeats)])
        )
    summary = summarize(results)
    thresholds = thresholds_from_env()
    report = render_report(results, summary, thresholds, args.repeats)
    Path(args.report).write_text(report, encoding="utf-8")
    print(report)
    breaches = gate(summary, thresholds)
    if breaches:
        print("Gate failed: " + "; ".join(breaches), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
