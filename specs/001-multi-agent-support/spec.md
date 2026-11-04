# Feature Specification: Getnet Multi-Agent Support System

**Feature Branch**: none; all work happens on the default branch (`master`), per the constitution

**Created**: 2026-11-04

**Status**: Draft

**Input**: User description: "Build the multi-agent system described in docs/challenge.md, following the constitution. The required workflow is the image docs/agent-workflow.png: Input, Router, specialized agents with their tools, Personality, Output; the custom agent is the Human Escalation Agent. Knowledge base sources, both one level deep from their start page, same host only, deduplicated by final URL and content hash, keeping only HTTP 200 text/html, max RAG_MAX_PAGES pages in total: site.getnet.com.br (www.getnet.com.br redirects there; /duvidas/, /crediario/, /link-de-pagamento/, /pix/ and /todas-as-maquininhas/ must be included) and www.getnet.net/en (/en paths only; /en/our-solutions/in-person-payments must be included). The crawler is sequential, pauses 2 seconds between requests, caches raw HTML under data/crawl_cache/, never refetches a cached URL unless the refresh command is used, and stops crawling a host at the first 403 or 429. Text extraction must preserve tables, product cards and FAQ questions, so it strips script, style, nav, header and footer plus text repeated in 30% or more of the pages instead of relying on trafilatura main-content detection. Chunk by heading and by FAQ question, not by fixed windows. Retrieval combines vector top-k with lexical matching over a product alias glossary, because users write in English while the main source is in Portuguese: Get Clássica = Get Classic, Link de Pagamento = Payment Link, antecipação = receivables advance, crediário, parcelas = installments. Answers use the user's language and name the source; content from the global site is not presented as confirmed for Brazil. Web search via Gemini Google Search grounding for general factual questions like weather and exchange rates. Refusals apply to unsafe or sensitive requests and to messages that are not an information need, such as creative writing. Customer support tools over simulated merchant data in a local JSON: get_receivables(user_id) for settlement dates and amounts, get_terminal_status(user_id) for card machine connectivity, last errors and suggested actions. All ten example scenarios in the challenge are acceptance criteria, with assertions on the expected fact for the five RAG scenarios. A compound message such as 'When will yesterday's sales be deposited and how does receivables advance work?' must run Support then Knowledge. Each Router step names the agent and, for Knowledge, the source: rag or web. The scenario 'My card machine won't connect to the internet, what should I do?' runs Support then Knowledge, combining terminal status with the site's chip and connectivity steps; when a later step cannot be grounded, earlier answers are kept and no handoff happens. Simulated data covers cliente1988 and at least one other merchant and uses dates relative to the current day, so 'yesterday' always resolves; an unknown user_id gets a clear not-found answer. API: POST /chat with the exact payload from the challenge, user_id being any non-empty string with no format validation because the challenge's own example is some_user_identifier, validation errors as JSON, and a response with answer, route, sources, ticket_id when present, trace and request_id; GET /health reports ready once the knowledge base exists. Ingestion runs on startup when the collection is empty, persists in a Docker volume, and has a separate command to refresh; if a source fails, the service still starts. The Human Escalation Agent has a create_ticket tool writing to a local JSONL file in a volume, and is triggered by an explicit request for a person, missing grounding, tool or LLM failure, or exceeded budget. The API is stateless across requests. The README, in English, covers: how to build, configure, run and test; orchestration architecture with the workflow image; design choices; message workflow; RAG pipeline in four stages (ingestion, storage, retrieval, generation); how LLM tools are used; testing strategy including integration tests of the orchestration; evaluation and observability strategy, including dashboards and alerts for production; and known limits (user_id is trusted without authentication, no conversation memory, Google Search grounding requires a paid-tier key)."

## User Scenarios & Testing *(mandatory)*

### Official Acceptance Scenarios

All ten scenarios from `docs/challenge.md` use `user_id` `cliente1988`. Route tokens are defined in R13.
Expected facts were read from the live sources on 2026-11-04. Assertions use stable facts only,
because the sites show seasonal offers and prices.

| # | Message | Expected route | Expected fact or assertion | Expected source |
|---|---------|----------------|----------------------------|-----------------|
| S1 | What's the difference between the Get Clássica and the Get Smart? | `knowledge:rag` | Get Classic is the basic POS; Get Smart runs Android with integrated management, from stock to closing the cashier. The answer states this comes from the global site and is not confirmed for Brazil. | `www.getnet.net/en/our-solutions/in-person-payments` |
| S2 | What's the weather forecast in Porto Alegre tomorrow? | `knowledge:web` | The answer gives a forecast for Porto Alegre and cites at least one web source. | Any web source |
| S3 | When will the money from yesterday's sales be deposited? | `support` | Settlement date and amount of yesterday's sales match the simulated data for `cliente1988`. | Simulated merchant data |
| S4 | Do I need a bank account to receive my sales via Pix? | `knowledge:rag` | Receiving via Pix requires a Pix key linked to the receiving account, and Get Conta is a free digital account that can be that account. | `site.getnet.com.br/duvidas/` |
| S5 | My card machine won't connect to the internet, what should I do? | `support`, `knowledge:rag` | The answer states the terminal status from the simulated data and the site's steps: insert the chip in SIM1 or SIM2 with the metal side down, then run the communication test. | Simulated merchant data and `site.getnet.com.br/duvidas/` |
| S6 | How does receivables advance (antecipação) work with Getnet? | `knowledge:rag` | Credit sales, single-payment or in installments, can be received before the settlement period, and the Getnet app is where this is done. | `site.getnet.com.br/duvidas/` |
| S7 | What's the euro exchange rate today? | `knowledge:web` | The answer gives a euro rate and cites at least one web source. | Any web source |
| S8 | My card machine is showing a transaction decline error. | `support` | The answer states the last decline error and its suggested action from the simulated data. | Simulated merchant data |
| S9 | How many installments can I split a sale into with the crediário? | `knowledge:rag` | Up to 48 installments, with the maximum term and interest depending on the card issuer. | `site.getnet.com.br/crediario/` |
| S10 | Can I sell through WhatsApp using the Payment Link? | `knowledge:rag` | Yes: the Payment Link supports selling through WhatsApp and social networks. | `site.getnet.com.br/link-de-pagamento/` |

### User Story 1 - Grounded answers about Getnet products (Priority: P1)

A merchant asks about Getnet products and services, usually in English, and gets an answer in their
own language that is grounded in Getnet's sites and names the source.

**Why this priority**: This is the core value of the challenge, and five of the ten official
scenarios depend on it.

**Independent Test**: With a populated knowledge base, send S1, S4, S6, S9 and S10 and check route,
expected fact and cited source.

**Acceptance Scenarios**:

1. **Given** a populated knowledge base, **When** S1, S4, S6, S9 or S10 is sent, **Then** the route, expected fact and source match the table above.
2. **Given** a question using an English alias, **When** the matching content is in Portuguese, **Then** the Portuguese content is retrieved through the alias glossary.
3. **Given** an answer that relies on the global site, **When** it is returned, **Then** it states that the content is not confirmed for Brazil.
4. **Given** a Getnet question with no retrieved content that qualifies, **When** it is the first step, **Then** no answer is guessed and a ticket is created.

---

### User Story 2 - Merchant-specific support (Priority: P1)

A merchant asks about their own settlements or card machine and gets an answer from their own data.

**Why this priority**: It is the second required agent and covers scenarios S3 and S8, and it
carries the main authorization risk.

**Independent Test**: Send S3 and S8 for `cliente1988`, then the same messages for another merchant
and an unknown `user_id`, and compare each answer with the simulated data.

**Acceptance Scenarios**:

1. **Given** `cliente1988`, **When** S3 or S8 is sent, **Then** the route and data match the table above.
2. **Given** any day the system runs, **When** a merchant asks about yesterday's sales, **Then** "yesterday" resolves to a simulated record.
3. **Given** a `user_id` not in the simulated data, **When** a support question is sent, **Then** the answer says clearly that the merchant was not found, and no ticket is created.
4. **Given** a message asking for another merchant's data, **When** it is processed, **Then** it is refused and no data from that merchant appears in the response.

---

### User Story 3 - Multi-step answers (Priority: P1)

A merchant sends a message that needs both their own data and site guidance, and gets one combined
answer.

**Why this priority**: Router-managed sequences and data flow between agents are explicit
requirements of the challenge.

**Independent Test**: Send S5 and the compound message, then repeat with retrieval returning nothing
that qualifies.

**Acceptance Scenarios**:

1. **Given** S5, **When** it is processed, **Then** the route is `support`, `knowledge:rag`, Support's output reaches Knowledge, and the answer combines terminal status with the site's steps.
2. **Given** "When will yesterday's sales be deposited and how does receivables advance work?", **When** it is processed, **Then** the route is `support`, `knowledge:rag` and both parts are answered.
3. **Given** a sequence whose later step cannot be grounded, **When** it finishes, **Then** the earlier answer is kept, the unanswered part is stated, and there is no handoff or `ticket_id`.

---

### User Story 4 - General factual questions (Priority: P2)

A merchant asks a general factual question such as the weather or an exchange rate and gets a
current answer with web sources.

**Why this priority**: It is required by the challenge and covers scenarios S2 and S7, but it is not
Getnet-specific.

**Independent Test**: Send S2 and S7 and check route and cited web sources.

**Acceptance Scenarios**:

1. **Given** S2 or S7, **When** it is processed, **Then** the route is `knowledge:web` and at least one web source is cited.
2. **Given** a web search with no usable grounding, **When** it is the first step, **Then** no answer is guessed and a ticket is created.

---

### User Story 5 - Guardrails and refusals (Priority: P2)

Unsafe, sensitive or non-informational messages are refused politely, and sensitive numbers never
reach a model or a log.

**Why this priority**: It protects users and the system, and it is the bonus the challenge values
most in a payments context.

**Independent Test**: Send each adversarial case and check the route, the refusal, and that the
sensitive value appears in no response, trace or log.

**Acceptance Scenarios**:

1. **Given** a message containing a valid card number or CPF, **When** it is processed, **Then** the value is masked before any model or log sees it, and the request continues.
2. **Given** a prompt-injection attempt in English or Portuguese, **When** it matches the heuristics, **Then** it gets a polite refusal without any LLM call.
3. **Given** a message over the length limit, **When** it is received, **Then** it gets a polite refusal without any LLM call.
4. **Given** an unsafe or sensitive request, or a non-informational one such as creative writing, **When** it is classified, **Then** it gets a polite refusal.
5. **Given** a tool result containing an embedded instruction, **When** it is processed, **Then** the instruction is not followed.

---

### User Story 6 - Human escalation (Priority: P2)

When the system cannot resolve a request, or the merchant asks for a person, a ticket is recorded
and its id is returned.

**Why this priority**: It is the custom agent, and it is the defined outcome for every failure path.

**Independent Test**: Trigger each cause and check the `ticket_id` in the response and the matching
record in the ticket file.

**Acceptance Scenarios**:

1. **Given** an explicit request for a person, **When** it is processed, **Then** the route is `escalation` and a `ticket_id` is returned.
2. **Given** a tool failure, an LLM that stays unavailable, or an exceeded budget, **When** it occurs, **Then** the API returns valid JSON with a `ticket_id` and any earlier answers.

---

### User Story 7 - Run, observe and evaluate the system (Priority: P2)

An evaluator builds and runs the service from a clean clone, sees what each request did and cost,
and runs the evaluation as a regression gate.

**Why this priority**: The challenge grades the Docker setup, README, observability and evaluation
alongside the agents.

**Independent Test**: From a clean clone plus `.env`, start the service, wait for readiness, run the
ten scenarios in the container and then run the evaluation.

**Acceptance Scenarios**:

1. **Given** a clean clone and a configured `.env`, **When** the service starts with either documented Docker method, **Then** ingestion runs and health reports ready once the knowledge base exists.
2. **Given** an existing knowledge base, **When** the service restarts, **Then** nothing is crawled again and the data is still there.
3. **Given** a source that fails during ingestion, **When** the service starts, **Then** it stays up and serves what was ingested.
4. **Given** any answered request, **When** the response is read, **Then** it shows the route, sources, and per-agent model, latency, tokens and cost, plus the request total.
5. **Given** a metric below its configured threshold, **When** the evaluation finishes, **Then** it writes the report and exits non-zero.

### Edge Cases

- **Empty or malformed input**: A missing, empty or wrong-typed `message` or `user_id`, or a malformed body, returns a JSON validation error and calls no LLM.
- **Unusual `user_id`**: Any non-empty string is accepted, including `some_user_identifier`. It is treated as an unknown merchant if it is not in the simulated data.
- **Unknown merchant plus site question**: The not-found statement counts as an earlier answer, so the Knowledge step still runs and no ticket is created.
- **Card-like numbers**: A digit sequence that fails Luhn is not masked as a card number.
- **Refusal before language is known**: Deterministic refusals and failures before the Router returns use the deterministic language detection in R9.
- **Knowledge base not ready**: During ingestion, or after a total source failure, `/chat` still answers. Steps that need the knowledge base follow the missing-grounding path.
- **Invalid Router output**: Output that fails schema parsing, names an unknown agent, or has a Knowledge step without a source is treated as an LLM failure.
- **Budget exhausted before Personality**: The agent draft is returned, as with any Personality failure.
- **Ticket write failure**: The tool reports its own failure, the API still returns valid JSON with no `ticket_id`, and the answer says the ticket could not be recorded.
- **Crawl block mid-host**: After a 403 or 429 that host stops, pages already fetched are kept, and the other host continues.
- **Interrupted ingestion**: A partial run is not treated as a complete knowledge base on the next start.
- **Failed refresh**: The current knowledge base stays in service until a replacement has been built.
- **Off-host redirect**: A link whose final URL leaves the source host, or leaves `/en` for the global source, is discarded.

## Requirements *(mandatory)*

Requirement IDs follow the `R<n>` form required by the constitution. Each one needs at least one
pytest test with its ID in the test name.

### Functional Requirements

**API**

- **R1**: The system MUST expose `POST /chat` accepting exactly `{"message": string, "user_id": string}`.
- **R2**: `user_id` MUST accept any non-empty string, with no format validation. A value that is blank after trimming counts as empty.
- **R3**: Validation errors MUST be returned as JSON with no LLM call.
- **R4**: The `/chat` response MUST contain `answer`, `route`, `sources`, `trace` and `request_id`, plus `ticket_id` when a ticket exists.
- **R5**: `GET /health` MUST report ready once the knowledge base exists and not ready before that.
- **R6**: The API MUST keep no conversation state across requests.

**Guardrails and refusals**

- **R7**: Guardrails MUST run before routing, with deterministic checks first: message length limit, masking, then injection heuristics.
- **R8**: Card numbers validated by Luhn and CPF numbers MUST be masked before text reaches any LLM, log, ticket, trace or response. A formatted CPF is always masked, and a bare 11-digit sequence is masked when its check digits are valid.
- **R9**: Prompt-injection heuristics MUST cover English and Portuguese. When no Router language is available, the language MUST be detected deterministically as `en` or `pt`, falling back to `pt`.
- **R10**: Over-length messages and heuristic injection matches MUST receive a polite deterministic refusal that makes no LLM call and skips Personality.
- **R11**: Unsafe or sensitive requests, requests for another merchant's data, and messages that are not an information need, such as creative writing, MUST receive a polite refusal. General factual questions are not out of scope.

**Routing and orchestration**

- **R12**: The Router MUST return an ordered list of steps and the user's language as `en` or `pt`, parsed into a validated model.
- **R13**: Each step MUST name the agent and, for Knowledge, the source. The response `route` MUST list the steps executed, using `support`, `knowledge:rag`, `knowledge:web`, `escalation` and `refusal`.
- **R14**: The orchestrator MUST run the steps in order and pass each agent's output to the next.
- **R15**: Messages needing merchant data and site guidance MUST run Support then Knowledge, including S5 and the compound message in User Story 3.
- **R16**: The workflow MUST match `docs/agent-workflow.png`: Input, Router, specialized agents with their tools, Personality, Output.
- **R17**: Every answer except deterministic refusals MUST pass through Personality, which applies the brand voice in the Router's language and adds no facts. If it fails, the agent draft MUST be returned.
- **R18**: Sources MUST be attached by code after Personality, both in `sources` and named in `answer`. Each entry MUST identify its URL and origin: Brazil site, global site or web.

**Knowledge sources and ingestion**

- **R19**: The crawl MUST cover `site.getnet.com.br` and `www.getnet.net/en`, one level deep from each start page and same host only, with `/en` paths only for the global source.
- **R20**: `/duvidas/`, `/crediario/`, `/link-de-pagamento/`, `/pix/`, `/todas-as-maquininhas/` and `/en/our-solutions/in-person-payments` MUST be included ahead of other pages, so the page cap cannot exclude them.
- **R21**: Pages MUST be deduplicated by final URL and content hash, only HTTP 200 `text/html` responses are kept, and the total MUST NOT exceed `RAG_MAX_PAGES`.
- **R22**: The crawler MUST be sequential and pause 2 seconds between requests.
- **R23**: Raw HTML MUST be cached under `data/crawl_cache/`, and a cached URL MUST NOT be refetched unless the refresh command is used.
- **R24**: Crawling a host MUST stop at its first 403 or 429.
- **R25**: Extraction MUST keep tables, product cards and FAQ questions. It MUST strip script, style, nav, header and footer plus text repeated in 30% or more of the pages, and MUST NOT rely on main-content detection such as trafilatura.
- **R26**: Chunking MUST be by heading and by FAQ question, not by fixed windows, and each FAQ question MUST stay with its own answer.
- **R27**: Ingestion MUST run on startup when the collection is empty and persist in a Docker volume. A separate command MUST refresh it.
- **R28**: A failed source MUST NOT stop the service from starting.

**Retrieval and generation**

- **R29**: Retrieval MUST combine vector top-k with lexical matching over the product alias glossary: Get Clássica = Get Classic; Link de Pagamento = Payment Link; antecipação = receivables advance; crediário, parcelas = installments.
- **R30**: A chunk MUST qualify as context when its similarity reaches `RAG_MIN_SIMILARITY` or it matches through the glossary.
- **R31**: Knowledge answers MUST use only qualifying context and MUST cite its source URLs.
- **R32**: Content from the global site MUST NOT be presented as confirmed for Brazil, and an answer using it MUST say so.
- **R33**: `knowledge:web` MUST use Google Search grounding for general factual questions and cite the grounding sources. Getnet questions MUST NOT fall back from RAG to web.

**Customer support**

- **R34**: Support MUST offer `get_receivables(user_id)`, returning settlement dates and amounts, and `get_terminal_status(user_id)`, returning connectivity, last errors and suggested actions.
- **R35**: Tools MUST read simulated merchant data from a local JSON file covering `cliente1988` and at least one other merchant, with dates relative to the current day so "yesterday" always resolves.
- **R36**: The `cliente1988` data MUST support S3, S5 and S8 without contradiction: a settlement for yesterday's sales, a connectivity problem, and a decline error with a suggested action.
- **R37**: An unknown `user_id` MUST receive a clear not-found answer, not a handoff.
- **R38**: One simulated merchant MUST have an embedded instruction in a tool result, so the live evaluation can exercise injection inside retrieved content with no test-only code path.

**Human escalation**

- **R39**: The Human Escalation Agent MUST have a `create_ticket` tool that appends to a local JSONL file in a Docker volume and returns the ticket id. It MUST work without any LLM call.
- **R40**: A ticket MUST record its id, `request_id`, `user_id`, masked message, reason, route so far, language and timestamp. Reason MUST be one of `explicit_request`, `no_grounding`, `tool_failure`, `llm_failure` or `budget_exceeded`.
- **R41**: Escalation MUST trigger on an explicit request for a person, missing grounding, tool or LLM failure, or exceeded budget.
- **R42**: Missing grounding in a later step, after an earlier step has answered, MUST keep the earlier answers, state the unanswered part, and create no ticket.
- **R43**: Tool failure, LLM failure or exceeded budget MUST stop the sequence and escalate, keeping any earlier answers in the response.

**Constitution-derived behavior**

- **R44**: Each agent's prompt MUST live in a dedicated module stating role, scope, output format and refusal rules, with the current date injected by code in the `America/Sao_Paulo` time zone.
- **R45**: Model names and thinking levels MUST come from environment variables, with the per-task assignment defined in constitution principle V.
- **R46**: Every LLM call MUST go through one wrapper that records model, latency, and prompt, output and thinking tokens, computes USD cost including Google Search requests, and logs structured JSON with the `request_id`.
- **R47**: The wrapper MUST enforce the per-request token budget, apply a timeout, and retry once on 429 or 5xx.
- **R48**: The wrapper MUST preserve complete model content, including thought signatures, across tool-calling turns.
- **R49**: Google Search grounding and function calling MUST run in separate LLM calls.
- **R50**: `trace` MUST contain per-agent model, latency, tokens and cost, plus the request total, and MUST show the URL and similarity of each retrieved chunk for Knowledge.
- **R51**: Max message length, top-k, max tool-call iterations and per-request token budget MUST be configurable.
- **R52**: `user_id` MUST come only from the request and be injected into tools by code, and tools MUST return only that merchant's data.
- **R53**: Retrieved content from RAG, web and tools MUST be delimited in prompts and never treated as instructions.
- **R54**: Tools MUST return structured results and handle their own failures.
- **R55**: When the budget is exceeded or the LLM stays unavailable, the API MUST still return valid JSON and hand off.

**Evaluation, delivery and documentation**

- **R56**: `evals/dataset.jsonl` MUST hold S1 to S10, the compound message, and adversarial cases for prompt injection, injection inside retrieved content, card number in message, another merchant's data, and out of scope, each with expected route and assertions.
- **R57**: `evals/run.py` MUST run the dataset against the live API and write `evals/report.md` with routing accuracy, citation rate, correct refusal rate, assertion pass rate, p50 and p95 latency, average cost per request, and total run cost.
- **R58**: `evals/run.py` MUST exit non-zero below any configured threshold and MUST run each case a configurable number of times, 3 by default.
- **R59**: Integration tests MUST call the HTTP endpoint and run the full orchestration with the LLM stubbed at the wrapper, asserting route, data flow between agents, `user_id` injection, refusals and handoff.
- **R60**: Secrets MUST be supplied only through `.env`, with a committed `.env.example` listing every variable.
- **R61**: The service MUST run with `docker compose up` and with plain `docker build` and `docker run`.
- **R62**: The README MUST be in English and cover: build, configure, run and test; orchestration architecture with the workflow image; design choices; message workflow; the RAG pipeline in four stages (ingestion, storage, retrieval, generation); how LLM tools are used; testing strategy including integration tests of the orchestration; evaluation and observability strategy, including production dashboards and alerts; and known limits (`user_id` trusted without authentication, no conversation memory, Google Search grounding requires a paid-tier key).

### Key Entities

- **Chat Request**: A message and the `user_id` that identifies the merchant.
- **Route Plan**: The Router's ordered steps and the user's language.
- **Step Output**: What an agent produced for one step, passed to the next step and to Personality.
- **Source Page**: A crawled page with its final URL, host, content hash and origin (Brazil site or global site).
- **Knowledge Chunk**: A heading section or FAQ question with its answer, linked to its Source Page.
- **Alias Glossary Entry**: A group of equivalent product terms across Portuguese and English.
- **Merchant Record**: Simulated receivables and terminal data for one `user_id`, with dates relative to today.
- **Ticket**: A recorded handoff with its id, reason, merchant, masked message and context.
- **Trace**: Per-agent and total model, latency, tokens and cost for one request.
- **Evaluation Case**: A dataset message with its `user_id`, expected route and assertions.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All ten official scenarios pass their route and fact assertions in a run against the containerized service.
- **SC-002**: Routing accuracy, citation rate, correct refusal rate and assertion pass rate each reach at least 90% over the evaluation dataset.
- **SC-003**: No card number or CPF from any test message appears in a response, trace, log or ticket.
- **SC-004**: No request returns another merchant's data in the adversarial cases.
- **SC-005**: Every request returns valid JSON with a `request_id`, including when the LLM is unavailable or the budget is exceeded.
- **SC-006**: 95% of requests complete within 30 seconds in the live evaluation.
- **SC-007**: From a clean clone plus `.env`, the service reports ready within 10 minutes of the first start, and within 1 minute on restarts with an existing knowledge base.
- **SC-008**: Every requirement ID appears in the name of at least one test.
- **SC-009**: The evaluation report shows the average cost per request and the total cost of the run.

## Assumptions

- **Verified on 2026-11-04**: `www.getnet.com.br` redirects to `site.getnet.com.br`. All six required pages return HTTP 200 `text/html` and are linked from their start pages. There are about 73 candidate pages (46 Brazil, 27 global), below the current `RAG_MAX_PAGES` of 80.
- The sites serve the content needed for the five RAG scenarios in static HTML, as checked on the required pages. Rendering JavaScript is out of scope.
- The site content on functional differences between Get Clássica and Get Smart was found only on the global site, so S1 carries the "not confirmed for Brazil" statement.
- The 30% repetition rule is computed per source host, so boilerplate from the smaller global site is not missed.
- "crediário, parcelas = installments" is read as one alias group containing all three terms.
- The HTTP service accepts requests while ingestion runs in the background, so health can report not ready.
- A partial knowledge base counts as existing, and pages from a failed source are recovered with the refresh command.
- Refusals are returned with HTTP 200 because they are valid outcomes, not client errors.
- Merchant data and tickets are simulated and local. No real merchant data or external ticketing system is involved.
- Production dashboards and alerts are documented in the README and not implemented.
- The challenge's 60-minute limit covers core development. The demo video is out of scope for this specification.
- Exact provider behavior (model names, thinking levels, grounding metadata, search pricing) is verified in the plan phase.
