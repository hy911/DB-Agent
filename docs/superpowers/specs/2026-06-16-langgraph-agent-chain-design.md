# Design: LangGraph agent chain (llm/ + graph/)

Date: 2026-06-16
Status: Approved (brainstorming) — ready for implementation plans
Scope: Phase 1 MVP, **efficacy domain only**. One end-to-end chain wiring the
existing `semantic/`, `sql/`, and `db/` layers together with a new `llm/`
(LiteLLM + prompts) and `graph/` (LangGraph) layer.

## Goal

Turn a natural-language question into a natural-language answer that also shows
the SQL it ran:

```
route / clarify → assemble_context → generate_sql (qwen-code)
  → guard (sql/ validate + inject + limit) → execute (read replica)
  → self-correct (≤3) → answer (qwen-main)
```

When intent is ambiguous or out of the efficacy scope, the chain **clarifies
rather than guesses** — it ends and returns a clarification question.

This work delivers a callable `run_agent(question, ...) -> AgentResult`. The
FastAPI endpoint that exposes it is a **separate, later** piece (out of scope).

## Confirmed decisions (brainstorming, 2026-06-16)

- **One spec, two implementation plans:** Plan A builds `llm/`; Plan B builds
  `graph/` (plus a small `sql/secure.py` bridge). Each is independently testable.
- **Stateless clarification:** the graph ends and returns
  `needs_clarification` + the question. No checkpointer; a user's follow-up is a
  fresh `run_agent` call with the extra context appended to the question.
- **LLM routing in the MVP:** a lightweight LLM route node classifies the
  question into `{efficacy, needs_clarification}`. Anything ambiguous or beyond
  efficacy → clarification.
- **Dependency injection** is the testability backbone: all external
  dependencies (LLM client, `ReadReplica`, semantic layer) are passed into
  `run_agent`. Offline tests inject fakes; nothing hits a real LLM or DB.

## Module decomposition

| Module | Responsibility | Offline-testable |
|---|---|---|
| `llm/client.py` | `LLMClient` Protocol (`complete(model, messages) -> str`) + `LiteLLMClient` (wraps `litellm` against the configured OpenAI-compatible gateway). | Yes (fake client) |
| `llm/prompts.py` | **Pure.** Build the `messages` list for route / sql-gen / answer (system prompt + schema context + prior error). | Yes |
| `llm/agent_llm.py` | `route(client, question) -> RouteResult`, `generate_sql(client, question, context, prior_error=None) -> str`, `answer(client, question, sql, result) -> str`. | Yes (fake client) |
| `sql/secure.py` (new) | **Pure bridge** `secure_query(sql, layer, domain) -> SecuredQuery(sql, needs_explain)`: runs parse → validate_structure → enforce_limit → inject_permissions and renders the secured SQL string, computing the `needs_explain` flag. Keeps graph nodes thin. | Yes |
| `graph/state.py` | `AgentState` dataclass: the data threaded through the graph. | Yes |
| `graph/nodes.py` | The node functions: route, assemble_context, generate_sql, guard, execute, answer. | Yes (fakes) |
| `graph/build.py` | `build_graph(deps)` wiring + conditional edges (self-correction, clarification); `run_agent(question, *, llm, replica, layer, settings) -> AgentResult`. | Yes |

`llm/__init__.py` and `graph/__init__.py` export the public surface.

## LLM layer

### Client protocol (injection seam)

```python
class LLMClient(Protocol):
    def complete(self, model: str, messages: list[dict[str, str]]) -> str: ...
```

- `LiteLLMClient(settings)` implements it by calling `litellm.completion` against
  the OpenAI-compatible gateway (`settings.litellm_base_url`,
  `settings.litellm_api_key`), returning the assistant message text. The exact
  model addressing for a LiteLLM proxy (e.g. `openai/<alias>` + `api_base`) is an
  implementation detail nailed down in Plan A and confirmed by live smoke test.
- Tests use a `FakeLLMClient` that returns scripted strings per call.

### Functions (`agent_llm.py`)

- `route(client, question) -> RouteResult` — calls `settings.model_fast`
  (`qwen-fast`, the domain-routing model); the model is
  prompted to answer strictly `efficacy` or `clarify: <question>`; the parser
  maps that to `RouteResult(domain="efficacy")` or
  `RouteResult(clarification="...")`. Unparseable / unexpected → clarification
  (fail safe: never guess a domain).
- `generate_sql(client, question, context, prior_error=None) -> str` — calls
  `settings.model_sql` (qwen-code); returns a single SQL string. On a retry,
  `prior_error` is included so the model can fix its previous SQL.
- `answer(client, question, sql, result) -> str` — calls `settings.model_route`
  (`qwen-main`, the general-reasoning model — note the existing field name is
  `model_route`); renders
  the `QueryResult` rows into a natural-language answer (and explicitly says "no
  matching rows" when empty).

### Prompts (`prompts.py`, pure)

Pure builders returning `list[dict[str,str]]`. The sql-gen prompt embeds the
assembled schema context and (on retry) the prior error. No secrets, no I/O.

## Graph layer

### State

```python
@dataclass
class AgentState:
    question: str
    domain: str | None = None
    context: str | None = None          # assembled schema text for sql-gen
    sql: str | None = None              # last generated (raw) SQL
    secured_sql: str | None = None      # after sql/secure
    needs_explain: bool = False
    attempts: int = 0
    last_error: str | None = None       # retryable error fed back to generate_sql
    result: QueryResult | None = None
    answer: str | None = None
    clarification: str | None = None
    status: str = "running"             # running | answered | clarify | error
    error: str | None = None            # fatal error message
```

### Nodes and data flow

```
route ──clarify──▶ END (status=clarify, clarification set)
  │ efficacy
assemble_context   (semantic_layer: efficacy tables + spine only)
  ▼
generate_sql ◀───────────────────────┐  self-correct: prior_error in prompt
  ▼                                    │
guard = sql.secure_query ──retryable GuardError (parse) ──┤ attempts < max
  │ secured_sql, needs_explain          │
  ▼                                     │
execute = ReadReplica.execute ──retryable GuardError (bad_column…) ──┘
  │ QueryResult            └─ fatal GuardError ──▶ END (status=error)
  ▼
answer ──▶ END (status=answered, answer + sql shown)
```

- **Self-correction:** a `GuardError` with `retryable=True` raised by either
  `guard` or `execute` routes back to `generate_sql` with `attempts += 1` and
  `last_error` set. A `retryable` error after `attempts == max_sql_retries` (3)
  becomes a fatal error end. A `retryable=False` GuardError ends immediately as
  an error.
- **Routing back** is a LangGraph conditional edge keyed on the state set by the
  guard/execute nodes (they catch `GuardError`, record category/retryable into
  state, and the edge decides retry vs. error vs. continue).

### Public entry point

```python
@dataclass
class AgentResult:
    status: str                 # answered | clarify | error
    answer: str | None
    sql: str | None             # the secured SQL that ran (when answered)
    clarification: str | None
    error: str | None
    result: QueryResult | None  # raw rows, for callers that want them

def run_agent(
    question: str,
    *,
    llm: LLMClient,
    replica: ReadReplica,
    layer: SemanticLayer,
    settings: Settings,
) -> AgentResult: ...
```

The real `LLMClient`, `ReadReplica`, and `SemanticLayer` are assembled by the
caller (later, the API layer). `run_agent` builds the graph with those
dependencies and invokes it.

## Error handling

- Reuses the existing `GuardError.retryable` contract — no new error types.
- LLM transport failures (network/timeout/5xx from the gateway) → fatal error end
  (do not retry the same step in a loop).
- `answer` must produce a sensible NL response even for zero rows.

## Testing (offline — no LLM, no DB)

- `llm/`: pure prompt builders asserted directly; `agent_llm` functions driven by
  a `FakeLLMClient` (scripted outputs) — assert routing/parse behavior, retry
  prompt includes the prior error.
- `graph/`: full-graph runs with `FakeLLMClient` + a `FakeReplica`
  (returns a preset `QueryResult` or raises a chosen `GuardError`):
  1. Happy path → `status == "answered"`, answer + sql present.
  2. First attempt raises a retryable bad-column GuardError → self-correct →
     second attempt succeeds (`attempts == 1`).
  3. Three consecutive retryable errors → `status == "error"` (budget exhausted).
  4. Route returns clarify → `status == "clarify"`, no SQL generated, DB never
     called.
  5. Fatal GuardError (e.g. big_table_scan) → `status == "error"`, no retry.
- `sql/secure.py`: pure test — a valid efficacy SQL is parsed, permission-filtered
  (`for_bd = 'yes'` present), LIMIT enforced, and `needs_explain` computed.

## Configuration note (for live runs, not the offline suite)

`llm/` reads the gateway settings from `Settings` (`DBAGENT_`-prefixed). The
user's deployed gateway uses different env names (`LITELLM_BASE_URL`,
`LITELLM_MASTER_KEY`, `MODEL_MAIN/FAST/CODE`). Plan A resolves this one of two
ways (decided at implementation): map them into `DBAGENT_`-prefixed vars in
`.env`, or add `AliasChoices` to `config.py` so it also accepts the deployed
names. Credentials stay in the gitignored `.env`. Base URL:
`https://llm-dev.yiconmed.com/v1`.

## Out of scope (deferred)

FastAPI endpoint, observability logging (item #8 — the state already carries the
question/context/sql/result/error tuple a future logger can consume), real
`resolve_gene`, the non-efficacy domains, and multi-turn (stateful) clarification.

## Open questions

None. All decisions are resolved above.
