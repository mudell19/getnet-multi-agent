# Getnet Multi-Agent Constitution

## Core Principles

### I. Router-Led Orchestration in Plain Python

- Orchestration MUST be plain Python with direct function calls between agents. Agent frameworks
  MUST NOT be used.
- The Router is the primary entry point. It MUST run the guardrails and then return an ordered list
  of steps and the user's language, as `en` or `pt`.
- The orchestrator MUST run that sequence and pass each agent's output to the next.
- Every answer MUST pass through a final Personality step, which applies the brand voice in the
  language given by the Router and MUST NOT add facts.
- Sources MUST be attached by code after the Personality step.
- If the Personality step fails, the agent draft MUST be returned. Deterministic refusals MUST skip
  the Personality step.
- Each agent's prompt MUST live in a dedicated module and state role, scope, output format and
  refusal rules. The current date MUST be injected into agent prompts by code.

Rationale: an explicit sequence keeps data flow readable and testable, and the Personality step
changes tone without becoming a source of facts.

### II. Deterministic Guardrails First

- Guardrails MUST run before routing, with deterministic checks first.
- The deterministic checks MUST include a message length limit, masking of card numbers validated
  by Luhn and of CPF numbers, and prompt-injection heuristics in English and Portuguese.
- Masking MUST happen before the text reaches any LLM or log.
- Unsafe or out-of-scope requests MUST receive a polite refusal.

Rationale: sensitive data and obvious attacks are stopped without cost or model variance.

### III. Grounded Answers or Human Handoff

- Domain answers MUST be grounded in retrieved context and cite source URLs.
- Vector search MUST use cosine space, with similarity defined as 1 minus distance.
- When retrieval similarity is below threshold or the answer cannot be grounded, the system MUST
  NOT guess. It MUST hand off to a Human Escalation Agent, which records a ticket and returns its
  id.

Rationale: in a payments domain, a ticket is a better outcome than a plausible invented answer.

### IV. Code-Owned Identity and Untrusted Data

- The `user_id` MUST come only from the request and MUST be injected into tools by code. The LLM
  MUST NOT choose it.
- Tools MUST return only that user's data.
- Retrieved content (RAG, web, tool results) is untrusted data. It MUST be delimited in prompts and
  MUST NOT be treated as instructions.

Rationale: authorization cannot depend on model behavior, and retrieved text is an attack surface.

### V. Right Model per Task

- Each model MUST be chosen and justified for its task, never the cheapest or the most expensive by
  default.
- Routing and input classification MUST use `GEMINI_ROUTER_MODEL` with thinking level minimal.
- The Personality step MUST use `GEMINI_PERSONALITY_MODEL` with thinking level minimal.
- Answering agents MUST use `GEMINI_MODEL` with thinking level low.
- Embeddings MUST use `GEMINI_EMBEDDING_MODEL`.
- All model names and thinking levels MUST come from environment variables.

Rationale: quality and cost are decided per task and can change without a code edit.

### VI. Single LLM Wrapper with Cost Control and Traceability

- Every LLM call MUST go through one client wrapper.
- The wrapper MUST record model, `latency_ms`, and prompt, output and thinking tokens from
  `usage_metadata`.
- The wrapper MUST compute cost in USD from a price table configured via environment variables,
  including Google Search requests counted from grounding metadata, because they are not part of
  `usage_metadata`.
- The wrapper MUST log each call as structured JSON with the `request_id` and MUST enforce a
  per-request token budget.
- Thinking tokens are billed as output, so cost MUST be controlled by thinking level, not by
  shrinking `max_output_tokens`.
- The wrapper MUST preserve the complete model content, including thought signatures, across
  tool-calling turns.
- Google Search grounding and function calling MUST run in separate LLM calls, never in the same
  request.
- Every API response MUST return the route taken, sources, and a trace with per-agent model,
  latency, tokens and cost, plus the request total.
- Cost limits MUST be explicit and configurable: max message length, top-k retrieved chunks, max
  tool-call iterations per request, and per-request token budget.

Rationale: one choke point makes cost, budget and behavior measurable on every request.

### VII. Structured Contracts and Graceful Degradation

- Every LLM output that drives control flow MUST be parsed into a Pydantic model.
- Every tool MUST return a structured result and handle its own failures.
- Every LLM call MUST have a timeout and one retry on 429 or 5xx.
- When the budget is exceeded or the LLM stays unavailable, the API MUST still return valid JSON
  and hand off.

Rationale: failures become defined states of the workflow instead of malformed responses.

### VIII. Evals Are Part of the Product

- `evals/dataset.jsonl` MUST hold the official scenarios plus adversarial cases: prompt injection,
  injection inside retrieved content, card number in message, asking for another user's data, and
  out of scope. Each case MUST have an expected route and assertions.
- `evals/run.py` MUST run the cases against the live API and write `evals/report.md` with routing
  accuracy, citation rate, correct refusal rate, p50 and p95 latency, and average cost per request.
- `evals/run.py` MUST exit non-zero below configured thresholds so it works as a regression gate.

Rationale: stubbed tests prove the code paths, and only live evals measure model behavior.

### IX. Requirement Traceability and Layered Tests

- Every requirement MUST have an ID (R1, R2...) and at least one pytest test referencing that ID in
  its name. This overrides the `FR-###` numbering in the spec template and the "tests are OPTIONAL"
  note in the tasks template.
- Unit tests MUST mock the LLM.
- Integration tests MUST call the HTTP endpoint and run the full orchestration with the LLM stubbed
  at the wrapper, asserting route, data flow between agents, `user_id` injection, refusals and
  handoff.

Rationale: an ID in a test name makes coverage of each requirement checkable by search.

### X. Simplicity Over Abstraction

- Only what the spec and this constitution ask for MUST be built.
- An abstraction, configuration option or dependency that neither of them requires MUST NOT be
  added.

Rationale: every extra layer is code to review and maintain, with no requirement behind it.

## Technology and Delivery Constraints

- Runtime: Python 3.12, managed with uv.
- HTTP layer: FastAPI.
- LLM: Google Gemini via the `google-genai` SDK is the only runtime LLM provider.
- Secrets MUST be supplied only via `.env`, with a committed `.env.example`.
- The app MUST run with `docker compose up` and with plain `docker build` and `docker run`.

## Development Workflow

- Each SDD phase (constitution, spec, plan, tasks) and each completed task MUST get its own commit.
- Commits MUST go on the repository default branch, with no feature or docs branches, and MUST be
  pushed immediately, so the remote history proves the stages and their times.

## Governance

- This constitution supersedes other project practices and Spec Kit template defaults.
- Amendments MUST be committed on the default branch and MUST update the version and the Last
  Amended date in the same commit.
- Versioning follows semantic versioning: MAJOR for removing or redefining a principle in a
  backward-incompatible way, MINOR for adding a principle or section or materially expanding
  guidance, PATCH for clarifications and wording.
- Statements here about provider behavior were written without web research or API calls. Those
  contracts MUST be verified in the plan phase. A statement found to be wrong MUST be corrected by
  amendment before implementation depends on it.
- Each plan MUST pass a Constitution Check against every principle, repeated after design. Any
  violation MUST be justified in the plan's Complexity Tracking table.
- Each task MUST be checked against the applicable principles before its commit.

**Version**: 1.0.0 | **Ratified**: 2026-11-04 | **Last Amended**: 2026-11-04
