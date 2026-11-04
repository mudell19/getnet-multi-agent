# Implementation Plan: Getnet Multi-Agent Support System

**Branch**: `master` (no feature branch, per constitution) | **Date**: 2026-11-04 | **Spec**: [spec.md](spec.md)

## Summary

A stateless FastAPI service runs Input → Router → specialized agents with tools → Personality →
Output, using plain Python function calls. Knowledge answers come from a crawled, persisted Chroma
collection (or Google Search grounding), Support uses simulated merchant data, and escalation
writes tickets to JSONL.

## Technical Context

**Language/Version**: Python 3.12, managed with uv
**Primary Dependencies**: fastapi, uvicorn, google-genai 2.34, chromadb 1.5, beautifulsoup4, lxml, httpx, pydantic, python-dotenv
**Storage**: Chroma persistent collection, HTML cache and tickets JSONL, all under `data/` (a Docker volume)
**Testing**: pytest; LLM mocked in unit tests, stubbed at the wrapper in integration tests; `evals/run.py` live
**Target Platform**: Linux container, amd64 and arm64
**Project Type**: Web service
**Performance Goals**: p95 under 30 s; ready within 10 minutes on first start
**Constraints**: limits from `.env`: 2000 chars, top-k 6, 3 tool iterations, 20000 tokens
**Scale/Scope**: about 73 pages, single process, evaluation-sized traffic

## Provider Contracts Verified (real calls, 2026-11-04, SDK 2.34)

| Contract | Result | Consequence |
|----------|--------|-------------|
| `thinking_level` | `minimal` and `low` accepted on `gemini-3.5-flash-lite` and `gemini-3.8-flash` | Levels pass straight from env |
| `usage_metadata` | `prompt_token_count`, `candidates_token_count`, `thoughts_token_count` (absent when no thinking), `total_token_count` | Missing fields count as 0 |
| Thought signatures | `thought_signature` sits on the function-call part | Wrapper returns the raw `candidate.content`; agents append it unchanged |
| Search counting | `grounding_metadata.web_search_queries` lists queries | Search requests = its length |
| Grounding URLs | `grounding_chunks[].web.uri` is a `vertexaisearch` redirect; `title` is the domain | Cite redirect URI with domain title; documented limit |
| Search plus functions | Same request returns 400 without a special flag | Separate calls, as the constitution requires |
| Embeddings batching | A list of `str` is **aggregated into one vector**; a list of `Content` returns one per item | Always send `Content` items |
| Embeddings usage | The response has no usage metadata | Tokens estimated as chars/4 and marked as estimated |
| Embeddings size | 3072 dimensions; `task_type` gave no change on the sample | No task type sent |
| `RAG_MIN_SIMILARITY=0.62` | EN query to matching PT text: 0.643 to 0.843. Off-topic query: at most 0.48. Unrelated Getnet text can reach 0.74 | Threshold kept; `grounded` flag from Knowledge decides final grounding |

## Constitution Check

| Principle | Design | Status |
|-----------|--------|--------|
| I Orchestration | `orchestrator.py` loops over Router steps; prompts in `prompts/`; date injected by code | Pass |
| II Guardrails | `guardrails.py` runs first; masking precedes LLM and logs | Pass |
| III Grounding | `grounded` flag plus citations; `no_grounding` escalates unless an earlier answer exists | Pass |
| IV Identity | Tools declare no parameters; code passes `user_id`; delimiters on retrieved content | Pass |
| V Models | Roles map to env model and thinking variables | Pass |
| VI Wrapper | All generate and embed calls go through `llm.py` | Pass |
| VII Contracts | Pydantic route plan and knowledge output; failures become escalations | Pass |
| VIII Evals | `evals/dataset.jsonl`, `evals/run.py`, `evals/report.md` | Pass |
| IX Traceability | `R<n>` in test names, enforced by `test_R_ids_covered` | Pass |
| X Simplicity | No queue, no ORM, sync request handling | Pass |

## Key Design Decisions

- **Sync handlers**: FastAPI runs them in its thread pool, and each request owns a `RequestContext` holding budget and trace.
- **Router steps** carry a `query`, the sub-question for that step, so compound messages reach each agent cleanly.
- **Support tools take no arguments** in their declarations, so the LLM cannot choose a `user_id`. Mode is `ANY` on the first turn to force data use.
- **Knowledge output** is JSON: `grounded`, `answer`, `citations` (chunk numbers). Code maps numbers to URLs, so the LLM cannot invent a source.
- **Retrieval**: glossary terms expand the embedded query. Up to half of top-k goes to lexical matches ranked by matched alias groups, and vector hits at or above the threshold fill the rest. No qualifying chunk means no LLM call.
- **Glossary** adds `Get Smart`, Pix account terms and connectivity terms to the aliases in the spec, because S1, S4 and S5 need them.
- **Global caveat and sources** are appended by code after Personality, in the user's language.
- **Personality guard**: output with a digit sequence absent from the draft, or missing the ticket id, is rejected in favor of the draft.
- **Atomic ingestion**: build `kb_building`, then delete `kb` and rename. A leftover `kb_building` is dropped at startup.
- **Refresh** runs with the service stopped, because Chroma's persistent client is single-process.
- **Merchant fixture** lives in the package because the `data/` volume would hide a file there.
- **Dev container runs** bind-mount `./data` to reuse `data/crawl_cache`; compose uses a named volume.

## Project Structure

```text
src/getnet_multi_agent/
├── config.py  logging_setup.py  schemas.py  llm.py  guardrails.py  orchestrator.py  main.py
├── prompts/   router.py  knowledge.py  support.py  personality.py
├── agents/    router.py  knowledge.py  support.py  personality.py  escalation.py
├── tools/     merchant.py  tickets.py
├── rag/       crawler.py  extract.py  chunker.py  glossary.py  store.py  retriever.py  ingest.py
└── fixtures/  merchants.json
tests/unit/  tests/integration/
evals/       dataset.jsonl  run.py  report.md
Dockerfile  docker-compose.yml  .env.example  .dockerignore  README.md
```

**Structure Decision**: single project using the existing `src/` layout.

## Complexity Tracking

No constitution violations to justify.
