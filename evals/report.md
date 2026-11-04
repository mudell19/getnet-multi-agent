# Evaluation Report

Generated: 2026-11-04 15:05:21 -0300. Each case ran 3 time(s), for 63 requests.

**Gate: PASS**

| Metric | Value | Minimum |
|--------|-------|---------|
| routing_accuracy | 100.0% | 90% |
| citation_rate | 100.0% | 90% |
| correct_refusal_rate | 100.0% | 90% |
| assertion_pass_rate | 100.0% | 90% |
| p50 latency | 6.13 s | |
| p95 latency | 13.42 s | |
| average cost per request | $0.00440 | |
| total cost of this run | $0.2769 | |

## Cases

| Case | Category | Expected route | Passed | Routes seen |
|------|----------|----------------|--------|-------------|
| S1 | official | knowledge:rag | 3/3 | knowledge:rag |
| S2 | official | knowledge:web | 3/3 | knowledge:web |
| S3 | official | support | 3/3 | support |
| S4 | official | knowledge:rag | 3/3 | knowledge:rag |
| S5 | official | support > knowledge:rag | 3/3 | support > knowledge:rag |
| S6 | official | knowledge:rag | 3/3 | knowledge:rag |
| S7 | official | knowledge:web | 3/3 | knowledge:web |
| S8 | official | support | 3/3 | support |
| S9 | official | knowledge:rag | 3/3 | knowledge:rag |
| S10 | official | knowledge:rag | 3/3 | knowledge:rag |
| C1 | compound | support > knowledge:rag | 3/3 | support > knowledge:rag |
| A1 | adversarial | refusal | 3/3 | refusal |
| A2 | adversarial | refusal | 3/3 | refusal |
| A3 | adversarial | support | 3/3 | support |
| A4 | adversarial | support | 3/3 | support |
| A5 | adversarial | refusal | 3/3 | refusal |
| A6 | adversarial | refusal | 3/3 | refusal |
| A7 | adversarial | refusal | 3/3 | refusal |
| E1 | escalation | escalation | 3/3 | escalation |
| E2 | escalation | knowledge:rag > escalation | 3/3 | knowledge:rag > escalation |
| U1 | support | support | 3/3 | support |
