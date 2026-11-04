# Tasks: Getnet Multi-Agent Support System

**Input**: `specs/001-multi-agent-support/` (spec.md, plan.md)

**Tests**: Mandatory under constitution principle IX. Each `R<n>` appears in a test name.

**Commits**: Each completed task gets its own commit on `master`, pushed immediately.

## Phase 1: Setup

- [X] T001 Add dependencies, lockfile, `.env.example`, `.dockerignore` and `src/getnet_multi_agent/config.py` (R45, R51, R60)
- [X] T002 Add `Dockerfile` and `docker-compose.yml` with digest-pinned base image, locked install, health check, log limit and `data` volume (R61)

## Phase 2: Foundational

- [X] T003 Implement the LLM wrapper with cost, budget, timeout, retry and JSON logging in `src/getnet_multi_agent/llm.py`, `logging_setup.py`, with `tests/unit/test_llm.py` (R46, R47, R48, R49, R55)
- [X] T004 Implement guardrails in `src/getnet_multi_agent/guardrails.py` with `tests/unit/test_guardrails.py` (R7, R8, R9, R10)
- [X] T005 Implement schemas, API and health with deterministic refusals in `schemas.py`, `orchestrator.py`, `main.py`, with `tests/integration/test_api.py` (R1 to R6)
- [X] T006 Build the image and call `/chat` and `/health` in the container

## Phase 3: User Story 1 - Grounded answers (P1)

**Independent test**: S1, S4, S6, S9, S10 return the expected route, fact and source.

- [X] T007 [US1] Implement the crawler in `src/getnet_multi_agent/rag/crawler.py` with `tests/unit/test_crawler.py`, then run the first crawl (R19 to R24)
- [X] T008 [US1] Implement extraction and chunking in `rag/extract.py`, `rag/chunker.py` with `tests/unit/test_extract.py` (R25, R26)
- [X] T009 [US1] Implement glossary, store, retriever and ingestion in `rag/glossary.py`, `store.py`, `retriever.py`, `ingest.py` with `tests/unit/test_rag.py` (R27 to R30)
- [X] T010 [US1] Implement Router, Knowledge and Personality agents and prompts in `agents/`, `prompts/`, and wire them in `orchestrator.py`, with `tests/integration/test_orchestration.py` (R12 to R18, R31, R32, R33, R44, R50, R53)
- [X] T011 [US1] Implement the evaluation runner and dataset in `evals/run.py`, `evals/dataset.jsonl` with `tests/unit/test_evals.py` (R56, R57, R58)

## Phase 4: User Story 2 - Merchant support (P1)

**Independent test**: S3 and S8 match the simulated data for each merchant; an unknown id gets not-found.

- [X] T012 [US2] Implement merchant fixture, tools and Support agent in `fixtures/merchants.json`, `tools/merchant.py`, `agents/support.py`, `prompts/support.py` with tests (R34 to R38, R52, R54)

## Phase 5: User Story 6 - Human escalation (P2)

**Independent test**: each trigger returns a `ticket_id` with a matching record.

- [X] T013 [US6] Implement tickets and escalation in `tools/tickets.py`, `agents/escalation.py` and failure paths in `orchestrator.py` with tests (R39 to R43, R55)

## Phase 6: User Stories 3, 4, 5 and 7 - Acceptance in the container

**Independent test**: the ten scenarios and adversarial cases pass in the container.

- [X] T014 [US3] Add multi-step tests for S5, the compound message and partial answers in `tests/integration/test_orchestration.py` (R15, R42, R59)
- [X] T015 [US4] Add web step tests in `tests/integration/test_orchestration.py` (R33, R49)
- [X] T016 [US5] Add adversarial tests in `tests/integration/test_orchestration.py` (R8, R10, R11, R38, R53)
- [X] T017 [US7] Run S1 to S10 in the container and fix routing, retrieval and prompts until each passes, checking RAG facts in context and answer

## Phase 7: Polish

- [X] T018 Add `tests/unit/test_traceability.py` enforcing that every `R<n>` is in a test name, and cover remaining IDs (R16, R62, SC-008)
- [X] T019 Write `README.md` with every section in R62
- [ ] T020 Prove from a clean clone: `docker compose up --build --wait`, S1 to S10, pytest, `evals/run.py`, `docker build --platform linux/amd64`
- [ ] T021 Commit `evals/report.md` and push

## Dependencies & Execution Order

Phases run in order. T010 needs T003 to T009. T012 and T013 need T010. T017 needs T010 to T013. No tasks run in parallel, because they share `orchestrator.py` and each needs its own commit.

## Implementation Strategy

MVP is Phase 3. Container checks come early (T006, T017), and feature work stops at minute 47 in favor of T019 to T021.
