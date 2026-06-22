# Few-Shot Example Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retrieve similar past (question → raw SQL) pairs from the observability log via a local vector index and inject them as few-shot examples into the SQL-generation prompt.

**Architecture:** A new pure-ish `examples/` package: `model.Example`, `store.ExampleStore` (loads a local `.npz` index, pure cosine `search`), `build.build_index` (+ CLI), a separate `EmbeddingClient` seam (`LiteLLMEmbeddingClient`), and a `retriever` factory. A new `retrieve_examples` graph node sits `assemble_context → retrieve_examples → generate_sql`; examples flow into `sql_messages`. Fail-soft throughout; off by default (no index path → no-op).

**Tech Stack:** Python, numpy (already present via scipy; declared explicitly), litellm embeddings (`qwen-embedding`), LangGraph, pytest, ruff, uv.

**Reference spec:** `docs/superpowers/specs/2026-06-22-example-retrieval-design.md`

---

## File Structure

**Create:**
- `src/db_agent/examples/__init__.py` — exports.
- `src/db_agent/examples/model.py` — `Example` frozen dataclass.
- `src/db_agent/examples/store.py` — `ExampleStore` (load + cosine `search`).
- `src/db_agent/examples/build.py` — `build_index(...)` + `__main__` CLI.
- `src/db_agent/examples/retriever.py` — `make_retriever`, `default_retriever`, `_no_examples`.
- `src/db_agent/llm/embedding.py` — `EmbeddingClient` Protocol + `LiteLLMEmbeddingClient`.
- `tests/test_examples_store.py`, `tests/test_examples_build.py`,
  `tests/test_examples_retriever.py`, `tests/test_llm_embedding.py`.

**Modify:**
- `pyproject.toml` — declare `numpy`.
- `src/db_agent/config.py` — `example_index_path`, `example_top_k`, `model_embed`.
- `src/db_agent/llm/prompts.py` — `sql_messages(..., examples=None)`.
- `src/db_agent/llm/agent_llm.py` — `generate_sql(..., examples=None)`.
- `src/db_agent/graph/state.py` — `examples` state field, `Deps.retrieve_examples`.
- `src/db_agent/graph/nodes.py` — `retrieve_examples_node`, `generate_sql_node` passes examples.
- `src/db_agent/graph/build.py` — wire node + `run_agent(retrieve_examples=...)`.
- `src/db_agent/api/app.py` — build the real retriever when an index path is set.
- `tests/test_llm_prompts.py`, `tests/test_graph_nodes.py`, `tests/test_graph_chain.py`,
  `tests/test_graph_state.py` (if it asserts state shape).

---

## Task 1: numpy dep + EmbeddingClient seam + config

**Files:**
- Modify: `pyproject.toml`, `src/db_agent/config.py`
- Create: `src/db_agent/llm/embedding.py`, `tests/test_llm_embedding.py`

- [ ] **Step 1: Declare numpy in `pyproject.toml`**

In the `dependencies = [` array add (numpy is already installed transitively via scipy;
this just makes the direct import explicit):

```toml
    "numpy>=1.26",
```

- [ ] **Step 2: Add config fields**

In `src/db_agent/config.py`, after the `model_sql` field (before the closing of the
class), add:

```python
    model_embed: str = Field(  # question embedding for example retrieval
        default="qwen-embedding",
        validation_alias=AliasChoices("DBAGENT_MODEL_EMBED", "MODEL_EMBED"),
    )

    # --- few-shot example retrieval (off until an index path is set) ---
    example_index_path: Path | None = None
    example_top_k: int = 3
```

- [ ] **Step 3: Write the failing embedding-client test**

```python
# tests/test_llm_embedding.py
from __future__ import annotations

import sys
import types

from db_agent.config import Settings
from db_agent.llm.embedding import EmbeddingClient, LiteLLMEmbeddingClient


def _install_fake_litellm(monkeypatch, capture):
    fake = types.ModuleType("litellm")

    def embedding(**kwargs):
        capture.update(kwargs)
        data = [{"embedding": [0.1, 0.2, 0.3]} for _ in kwargs["input"]]
        return types.SimpleNamespace(data=data)

    fake.embedding = embedding
    monkeypatch.setitem(sys.modules, "litellm", fake)


def test_embedding_client_satisfies_protocol():
    assert isinstance(LiteLLMEmbeddingClient(Settings(_env_file=None)), EmbeddingClient)


def test_embed_passes_model_and_returns_vectors(monkeypatch):
    capture: dict = {}
    _install_fake_litellm(monkeypatch, capture)
    client = LiteLLMEmbeddingClient(Settings(_env_file=None))
    out = client.embed(["a", "b"])
    assert out == [[0.1, 0.2, 0.3], [0.1, 0.2, 0.3]]
    assert capture["model"] == "openai/qwen-embedding"
    assert capture["input"] == ["a", "b"]
```

- [ ] **Step 4: Run it to verify it fails**

Run: `uv run pytest tests/test_llm_embedding.py -q`
Expected: FAIL (module `db_agent.llm.embedding` does not exist).

- [ ] **Step 5: Implement the embedding seam**

```python
# src/db_agent/llm/embedding.py
"""Embedding client seam, separate from LLMClient so existing fakes are untouched.

`LiteLLMEmbeddingClient` calls the gateway's embedding endpoint; litellm is imported
lazily so importing this module never touches the network.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from db_agent.config import Settings


@runtime_checkable
class EmbeddingClient(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class LiteLLMEmbeddingClient:
    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.litellm_base_url
        self._api_key = settings.litellm_api_key
        self._model = settings.model_embed

    def embed(self, texts: list[str]) -> list[list[float]]:
        import litellm

        resp = litellm.embedding(
            model=f"openai/{self._model}",
            api_base=self._base_url,
            api_key=self._api_key,
            input=texts,
        )
        return [list(item["embedding"]) for item in resp.data]
```

- [ ] **Step 6: Run tests + verify they pass**

Run: `uv run pytest tests/test_llm_embedding.py -q`
Expected: 2 passed.

- [ ] **Step 7: Sync + commit**

```bash
uv sync --extra dev
git add pyproject.toml uv.lock src/db_agent/config.py src/db_agent/llm/embedding.py tests/test_llm_embedding.py
git commit -m "example retrieval T1: numpy dep + EmbeddingClient seam + config"
```

---

## Task 2: Example model + ExampleStore (load + cosine search)

**Files:**
- Create: `src/db_agent/examples/__init__.py`, `src/db_agent/examples/model.py`,
  `src/db_agent/examples/store.py`
- Test: `tests/test_examples_store.py`

- [ ] **Step 1: Write `model.py`**

```python
# src/db_agent/examples/model.py
"""The retrieved few-shot example: a past question and the raw SQL that answered it."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Example:
    question: str
    sql: str
    domain: str
```

- [ ] **Step 2: Write the failing store tests**

```python
# tests/test_examples_store.py
from __future__ import annotations

import numpy as np

from db_agent.examples.build import save_index
from db_agent.examples.model import Example
from db_agent.examples.store import ExampleStore


def _make_index(tmp_path):
    examples = [
        Example("how many models for BD?", "SELECT count(*) FROM model_efficacy_info", "efficacy"),
        Example("list drugs", "SELECT drug_name FROM model_efficacy_info", "efficacy"),
        Example("TP53 expression?", "SELECT log2tpm FROM model_ccle_expression_data", "expression"),
    ]
    vectors = np.array([[1.0, 0.0], [0.9, 0.1], [0.0, 1.0]], dtype=np.float32)
    path = tmp_path / "idx.npz"
    save_index(path, vectors, examples)
    return path


def test_search_returns_nearest_in_domain(tmp_path):
    store = ExampleStore(_make_index(tmp_path))
    hits = store.search([1.0, 0.0], domain="efficacy", k=2)
    assert [h.question for h in hits] == [
        "how many models for BD?",
        "list drugs",
    ]
    assert all(h.domain == "efficacy" for h in hits)


def test_search_filters_by_domain(tmp_path):
    store = ExampleStore(_make_index(tmp_path))
    hits = store.search([0.0, 1.0], domain="expression", k=5)
    assert len(hits) == 1
    assert hits[0].domain == "expression"


def test_missing_file_is_empty_store(tmp_path):
    store = ExampleStore(tmp_path / "nope.npz")
    assert store.search([1.0, 0.0], domain="efficacy", k=3) == []


def test_none_path_is_empty_store():
    store = ExampleStore(None)
    assert store.search([1.0, 0.0], domain="efficacy", k=3) == []
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/test_examples_store.py -q`
Expected: FAIL (`db_agent.examples.store` / `build.save_index` missing).

- [ ] **Step 4: Write `store.py`**

```python
# src/db_agent/examples/store.py
"""Local vector index of few-shot examples. Pure cosine search over in-memory arrays.

The index file is a .npz produced by build.save_index: a float32 `vectors` matrix
plus parallel object arrays `questions` / `sqls` / `domains`. A missing/unset path or
a corrupt file yields an empty store whose search returns [] (fail-soft).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from db_agent.examples.model import Example


class ExampleStore:
    def __init__(self, path: Path | None) -> None:
        self._vectors: np.ndarray | None = None
        self._examples: list[Example] = []
        if path is None or not Path(path).exists():
            return
        try:
            data = np.load(path, allow_pickle=True)
            vectors = np.asarray(data["vectors"], dtype=np.float32)
            questions = list(data["questions"])
            sqls = list(data["sqls"])
            domains = list(data["domains"])
        except Exception:
            return  # corrupt/unreadable -> empty store (fail-soft)
        if len(vectors) == len(questions) == len(sqls) == len(domains) and len(vectors) > 0:
            self._vectors = vectors
            self._examples = [
                Example(q, s, d) for q, s, d in zip(questions, sqls, domains, strict=True)
            ]

    def search(self, query_vec: list[float], domain: str, k: int) -> list[Example]:
        if self._vectors is None or k <= 0:
            return []
        idx = [i for i, ex in enumerate(self._examples) if ex.domain == domain]
        if not idx:
            return []
        mat = self._vectors[idx]
        q = np.asarray(query_vec, dtype=np.float32)
        sims = _cosine(mat, q)
        order = np.argsort(-sims)[:k]
        return [self._examples[idx[i]] for i in order]


def _cosine(mat: np.ndarray, q: np.ndarray) -> np.ndarray:
    mnorm = np.linalg.norm(mat, axis=1)
    qnorm = np.linalg.norm(q)
    denom = mnorm * qnorm
    denom[denom == 0] = 1e-12
    return (mat @ q) / denom
```

- [ ] **Step 5: Write `__init__.py`**

```python
# src/db_agent/examples/__init__.py
"""Few-shot example retrieval: local vector index built from the observability log."""

from __future__ import annotations

from db_agent.examples.model import Example
from db_agent.examples.store import ExampleStore

__all__ = ["Example", "ExampleStore"]
```

- [ ] **Step 6: Run tests (they also need `build.save_index` from Task 3)**

`save_index` is small and shared; define it now in `build.py` so Task 2 tests pass:

```python
# src/db_agent/examples/build.py  (initial — extended in Task 3)
"""Build a local example index from the observability JSONL log."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from db_agent.examples.model import Example


def save_index(path: Path, vectors: np.ndarray, examples: list[Example]) -> None:
    np.savez(
        path,
        vectors=np.asarray(vectors, dtype=np.float32),
        questions=np.array([e.question for e in examples], dtype=object),
        sqls=np.array([e.sql for e in examples], dtype=object),
        domains=np.array([e.domain for e in examples], dtype=object),
    )
```

Run: `uv run pytest tests/test_examples_store.py -q`
Expected: 4 passed.

- [ ] **Step 7: Commit**

```bash
git add src/db_agent/examples/__init__.py src/db_agent/examples/model.py src/db_agent/examples/store.py src/db_agent/examples/build.py tests/test_examples_store.py
git commit -m "example retrieval T2: Example model + cosine ExampleStore"
```

---

## Task 3: Index builder + CLI

**Files:**
- Modify: `src/db_agent/examples/build.py`
- Test: `tests/test_examples_build.py`

- [ ] **Step 1: Write the failing build tests**

```python
# tests/test_examples_build.py
from __future__ import annotations

import json

from db_agent.examples.build import build_index, load_examples_from_jsonl
from db_agent.examples.store import ExampleStore


def _write_log(path):
    rows = [
        {"status": "answered", "domain": "efficacy", "question": "q1", "raw_sql": "SELECT 1"},
        {"status": "answered", "domain": "efficacy", "question": "q1", "raw_sql": "SELECT 1"},  # dup
        {"status": "error", "domain": "efficacy", "question": "qbad", "raw_sql": "SELECT x"},
        {"status": "answered", "domain": "expression", "question": "q2", "raw_sql": None},  # no sql
        {"status": "answered", "domain": "mutation", "question": "q3", "raw_sql": "SELECT 3"},
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


def test_load_examples_filters_and_dedups(tmp_path):
    log = tmp_path / "obs.jsonl"
    _write_log(log)
    examples = load_examples_from_jsonl(log)
    # only answered + non-empty question/raw_sql, deduped on (domain, raw_sql)
    assert [(e.domain, e.question) for e in examples] == [
        ("efficacy", "q1"),
        ("mutation", "q3"),
    ]


def test_build_index_roundtrips_through_store(tmp_path):
    log = tmp_path / "obs.jsonl"
    _write_log(log)
    out = tmp_path / "idx.npz"

    def fake_embed(texts):
        # 2-d vector: length encodes nothing, just deterministic per text
        return [[float(len(t)), 1.0] for t in texts]

    n = build_index(log, fake_embed, out)
    assert n == 2  # two examples embedded
    store = ExampleStore(out)
    hits = store.search([3.0, 1.0], domain="mutation", k=1)
    assert hits[0].question == "q3"


def test_build_index_empty_log_writes_nothing(tmp_path):
    log = tmp_path / "empty.jsonl"
    log.write_text("", encoding="utf-8")
    out = tmp_path / "idx.npz"

    n = build_index(log, lambda texts: [[0.0] for _ in texts], out)
    assert n == 0
    assert not out.exists()  # nothing to index -> no file
    assert ExampleStore(out).search([0.0], domain="efficacy", k=1) == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_examples_build.py -q`
Expected: FAIL (`build_index` / `load_examples_from_jsonl` missing).

- [ ] **Step 3: Extend `build.py`**

Replace `src/db_agent/examples/build.py` with (keeps `save_index` from Task 2):

```python
# src/db_agent/examples/build.py
"""Build a local example index from the observability JSONL log.

Offline (not on the request path): read the obs log, keep successful runs, dedup,
embed each question, and write a .npz the ExampleStore can load. The embed function
is injected so this is unit-testable without the gateway.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import numpy as np

from db_agent.examples.model import Example


def save_index(path: Path, vectors: np.ndarray, examples: list[Example]) -> None:
    np.savez(
        path,
        vectors=np.asarray(vectors, dtype=np.float32),
        questions=np.array([e.question for e in examples], dtype=object),
        sqls=np.array([e.sql for e in examples], dtype=object),
        domains=np.array([e.domain for e in examples], dtype=object),
    )


def load_examples_from_jsonl(jsonl_path: Path) -> list[Example]:
    examples: list[Example] = []
    seen: set[tuple[str, str]] = set()
    for line in Path(jsonl_path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        if rec.get("status") != "answered":
            continue
        question = (rec.get("question") or "").strip()
        sql = (rec.get("raw_sql") or "").strip()
        domain = (rec.get("domain") or "").strip()
        if not question or not sql or not domain:
            continue
        key = (domain, sql)
        if key in seen:
            continue
        seen.add(key)
        examples.append(Example(question, sql, domain))
    return examples


def build_index(
    jsonl_path: Path,
    embed: Callable[[list[str]], list[list[float]]],
    out_path: Path,
) -> int:
    examples = load_examples_from_jsonl(jsonl_path)
    if not examples:
        return 0
    vectors = np.asarray(embed([e.question for e in examples]), dtype=np.float32)
    save_index(out_path, vectors, examples)
    return len(examples)


def _main(argv: list[str] | None = None) -> int:
    import argparse

    from db_agent.config import get_settings
    from db_agent.llm.embedding import LiteLLMEmbeddingClient

    parser = argparse.ArgumentParser(description="Build the few-shot example index.")
    parser.add_argument("jsonl", type=Path, help="observability JSONL log path")
    parser.add_argument("out", type=Path, help="output .npz index path")
    args = parser.parse_args(argv)

    client = LiteLLMEmbeddingClient(get_settings())
    n = build_index(args.jsonl, client.embed, args.out)
    print(f"indexed {n} examples -> {args.out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
```

- [ ] **Step 4: Run tests + verify they pass**

Run: `uv run pytest tests/test_examples_build.py tests/test_examples_store.py -q`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/db_agent/examples/build.py tests/test_examples_build.py
git commit -m "example retrieval T3: index builder + CLI"
```

---

## Task 4: Prompt injection + generate_sql passthrough

**Files:**
- Modify: `src/db_agent/llm/prompts.py`, `src/db_agent/llm/agent_llm.py`
- Test: `tests/test_llm_prompts.py`

- [ ] **Step 1: Write the failing prompt test**

Append to `tests/test_llm_prompts.py`:

```python
def test_sql_messages_include_examples_block():
    from db_agent.examples.model import Example
    from db_agent.llm.prompts import sql_messages

    examples = [Example("how many models?", "SELECT count(*) FROM model_efficacy_info", "efficacy")]
    msgs = sql_messages("list drugs", "ctx", examples=examples)
    joined = " ".join(m["content"] for m in msgs)
    assert "how many models?" in joined
    assert "SELECT count(*) FROM model_efficacy_info" in joined


def test_sql_messages_no_examples_block_when_empty():
    from db_agent.llm.prompts import sql_messages

    msgs = sql_messages("list drugs", "ctx", examples=[])
    joined = " ".join(m["content"] for m in msgs)
    assert "similar past questions" not in joined.lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_llm_prompts.py -q`
Expected: the 2 new tests FAIL (sql_messages has no `examples` param).

- [ ] **Step 3: Edit `sql_messages`**

In `src/db_agent/llm/prompts.py`, replace the `sql_messages` function. Keep the
`Example` import under `TYPE_CHECKING` to avoid a runtime import cycle:

```python
def sql_messages(
    question: str,
    context: str,
    prior_error: str | None = None,
    examples: list[Example] | None = None,
) -> list[dict[str, str]]:
    user = f"Schema context:\n{context}\n\nQuestion: {question}"
    if examples:
        shots = "\n".join(f"Q: {e.question}\nSQL: {e.sql}" for e in examples)
        user += (
            "\n\nHere are similar past questions and the SQL that answered them "
            "(reference only — adapt to the current question and schema):\n" + shots
        )
    if prior_error is not None:
        user += f"\n\nPrevious attempt failed with this database error; fix the SQL:\n{prior_error}"
    return [
        {"role": "system", "content": _SQL_SYSTEM},
        {"role": "user", "content": user},
    ]
```

And add the type-only import at the top of the `TYPE_CHECKING` block:

```python
if TYPE_CHECKING:
    from db_agent.examples.model import Example
    from db_agent.semantic.model import Domain
```

(If the file's existing `TYPE_CHECKING` block only imports `Domain`, add the `Example`
line alongside it.)

- [ ] **Step 4: Edit `generate_sql` to forward examples**

In `src/db_agent/llm/agent_llm.py`, replace `generate_sql`:

```python
def generate_sql(
    client: LLMClient,
    settings: Settings,
    question: str,
    context: str,
    prior_error: str | None = None,
    examples: list[Example] | None = None,
) -> str:
    text = client.complete(
        settings.model_sql, prompts.sql_messages(question, context, prior_error, examples)
    )
    return _strip_fences(text).strip()
```

Add a type-only import near the other imports in `agent_llm.py`:

```python
if TYPE_CHECKING:
    from db_agent.examples.model import Example
    from db_agent.semantic.model import Domain
```

(The file already has a `TYPE_CHECKING` block importing `Domain`; add the `Example`
line to it.)

- [ ] **Step 5: Run tests + verify they pass**

Run: `uv run pytest tests/test_llm_prompts.py tests/test_llm_agent.py -q`
Expected: all pass (existing + 2 new).

- [ ] **Step 6: Commit**

```bash
git add src/db_agent/llm/prompts.py src/db_agent/llm/agent_llm.py tests/test_llm_prompts.py
git commit -m "example retrieval T4: inject examples into sql_messages"
```

---

## Task 5: Retriever factory + graph wiring

**Files:**
- Create: `src/db_agent/examples/retriever.py`, `tests/test_examples_retriever.py`
- Modify: `src/db_agent/graph/state.py`, `src/db_agent/graph/nodes.py`,
  `src/db_agent/graph/build.py`, `src/db_agent/api/app.py`
- Test: `tests/test_graph_nodes.py`, `tests/test_graph_chain.py`

- [ ] **Step 1: Write the retriever + its failing test**

```python
# tests/test_examples_retriever.py
from __future__ import annotations

from db_agent.config import Settings
from db_agent.examples.model import Example
from db_agent.examples.retriever import _no_examples, default_retriever, make_retriever


class _Store:
    def __init__(self, hits):
        self._hits = hits
        self.seen = None

    def search(self, vec, domain, k):
        self.seen = (vec, domain, k)
        return self._hits


class _Embed:
    def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]


def test_no_examples_returns_empty():
    assert _no_examples("efficacy", "q") == []


def test_make_retriever_embeds_and_searches():
    hit = Example("past q", "SELECT 1", "efficacy")
    store = _Store([hit])
    retrieve = make_retriever(store, _Embed(), k=3)
    out = retrieve("efficacy", "current q")
    assert out == [hit]
    assert store.seen == ([1.0, 0.0], "efficacy", 3)


def test_make_retriever_fail_soft_on_embed_error():
    class _Boom:
        def embed(self, texts):
            raise RuntimeError("gateway down")

    retrieve = make_retriever(_Store([Example("x", "y", "efficacy")]), _Boom(), k=3)
    assert retrieve("efficacy", "q") == []  # degrades to no examples


def test_default_retriever_no_index_is_noop():
    # no example_index_path -> the no-op retriever
    assert default_retriever(Settings(_env_file=None)) is _no_examples
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_examples_retriever.py -q`
Expected: FAIL (`db_agent.examples.retriever` missing).

- [ ] **Step 3: Write `retriever.py`**

```python
# src/db_agent/examples/retriever.py
"""Build the request-time retriever closure: embed the question, cosine-search the
store, fail-soft to no examples. `default_retriever` returns a no-op unless an index
path is configured, keeping retrieval off by default."""

from __future__ import annotations

from collections.abc import Callable

from db_agent.config import Settings
from db_agent.examples.model import Example
from db_agent.examples.store import ExampleStore
from db_agent.llm.embedding import EmbeddingClient

Retriever = Callable[[str, str], list[Example]]


def _no_examples(domain: str, question: str) -> list[Example]:
    return []


def make_retriever(store: ExampleStore, embed: EmbeddingClient, k: int) -> Retriever:
    def retrieve(domain: str, question: str) -> list[Example]:
        try:
            vec = embed.embed([question])[0]
            return store.search(vec, domain, k)
        except Exception:
            return []  # fail-soft: retrieval is additive, never break a good run

    return retrieve


def default_retriever(settings: Settings) -> Retriever:
    if settings.example_index_path is None:
        return _no_examples
    from db_agent.llm.embedding import LiteLLMEmbeddingClient

    store = ExampleStore(settings.example_index_path)
    return make_retriever(store, LiteLLMEmbeddingClient(settings), settings.example_top_k)
```

- [ ] **Step 4: Run + verify pass**

Run: `uv run pytest tests/test_examples_retriever.py -q`
Expected: 4 passed.

- [ ] **Step 5: Extend `graph/state.py`**

In `src/db_agent/graph/state.py`:

Add imports near the other `db_agent` imports:

```python
from db_agent.examples.model import Example
from db_agent.examples.retriever import Retriever, _no_examples
```

In `AgentState`, after `resolved_genes: dict[str, str]`:

```python
    examples: list[Example]
```

In `initial_state`, after `resolved_genes={},`:

```python
        examples=[],
```

In `Deps`, after the `run_stat` field:

```python
    retrieve_examples: Retriever = _no_examples
```

- [ ] **Step 6: Add the node + pass examples into generate_sql in `graph/nodes.py`**

In `src/db_agent/graph/nodes.py`, add the node (after `assemble_context_node`):

```python
def retrieve_examples_node(state: AgentState, deps: Deps) -> dict:
    return {"examples": deps.retrieve_examples(state["domain"], state["question"])}
```

Replace `generate_sql_node` to forward examples:

```python
def generate_sql_node(state: AgentState, deps: Deps) -> dict:
    sql = llm_generate_sql(
        deps.llm,
        deps.settings,
        state["question"],
        state["context"],
        state["last_error"],
        state["examples"],
    )
    return {"sql": sql, "attempts": state["attempts"] + 1}
```

- [ ] **Step 7: Wire the node in `graph/build.py`**

In `src/db_agent/graph/build.py`:

Add imports:

```python
from db_agent.examples.model import Example
from db_agent.examples.retriever import Retriever
```

Register the node (after the `assemble_context` node line):

```python
    g.add_node("retrieve_examples", partial(nodes.retrieve_examples_node, deps=deps))
```

Replace `g.add_edge("assemble_context", "generate_sql")` with:

```python
    g.add_edge("assemble_context", "retrieve_examples")
    g.add_edge("retrieve_examples", "generate_sql")
```

Add a `retrieve_examples` override to `run_agent` (after the `run_stat` param):

```python
    retrieve_examples: Retriever | None = None,
```

and thread it in (after the `run_stat` block):

```python
    if retrieve_examples is not None:
        deps_kwargs["retrieve_examples"] = retrieve_examples
```

- [ ] **Step 8: Build the real retriever in `api/app.py`**

In `src/db_agent/api/app.py`, in the `deps is None` branch of the lifespan, set the
retriever from settings. Add the import at the top:

```python
from db_agent.examples.retriever import default_retriever
```

and in the `Deps(...)` construction add the field:

```python
            app.state.deps = Deps(
                llm=LiteLLMClient(s),
                replica=replica,
                layer=load_semantic_layer(s.semantic_layer_path),
                settings=s,
                retrieve_examples=default_retriever(s),
            )
```

- [ ] **Step 9: Node + chain tests**

Append to `tests/test_graph_nodes.py` (import `retrieve_examples_node` in the existing
`from db_agent.graph.nodes import (...)` block first):

```python
def test_retrieve_examples_node_injects():
    from db_agent.examples.model import Example

    hit = Example("past q", "SELECT 1", "efficacy")
    deps = _deps()
    object.__setattr__(deps, "retrieve_examples", lambda domain, q: [hit])
    s = initial_state("q")
    s["domain"] = "efficacy"
    out = retrieve_examples_node(s, deps)
    assert out["examples"] == [hit]


def test_retrieve_examples_node_default_is_empty():
    deps = _deps()  # default Deps.retrieve_examples is the no-op
    s = initial_state("q")
    s["domain"] = "efficacy"
    assert retrieve_examples_node(s, deps) == {"examples": []}


def test_generate_sql_forwards_examples():
    from db_agent.examples.model import Example

    captured = {}

    class _LLM2:
        def complete(self, model, messages):
            captured["joined"] = " ".join(m["content"] for m in messages)
            return "SELECT 1"

    deps = _deps(llm=_LLM2())
    object.__setattr__(deps, "retrieve_examples", lambda d, q: [])
    s = initial_state("q")
    s["context"] = "ctx"
    s["examples"] = [Example("past q", "SELECT 42", "efficacy")]
    generate_sql_node(s, deps)
    assert "SELECT 42" in captured["joined"]  # example reached the prompt
```

The `generate_sql_node` tests already in the file pass `s["examples"]`; the existing
`test_generate_sql_increments_attempts` sets up `initial_state` which now includes
`examples=[]`, so it still works unchanged.

Append a chain test to `tests/test_graph_chain.py`:

```python
def test_examples_injected_end_to_end():
    from db_agent.examples.model import Example

    llm = _LLM(
        {
            "qwen-fast": ["efficacy"],
            "qwen-code": ["SELECT drug_name FROM model_efficacy_info", "NONE", "NONE"],
            "qwen-main": ["Found 1 drug."],
        }
    )
    hit = Example("how many?", "SELECT count(*) FROM model_efficacy_info", "efficacy")
    res = run_agent(
        "list drugs for BD",
        llm=llm,
        replica=_Replica([_qr()]),
        layer=LAYER,
        settings=SETTINGS,
        retrieve_examples=lambda domain, q: [hit],
    )
    assert res.status == "answered"
```

- [ ] **Step 10: Run the graph tests**

Run: `uv run pytest tests/test_graph_nodes.py tests/test_graph_chain.py tests/test_graph_state.py -q`
Expected: all pass. If `test_graph_state.py` asserts the exact `AgentState`/`initial_state`
keys, add `examples` to its expectations.

- [ ] **Step 11: Commit**

```bash
git add src/db_agent/examples/retriever.py src/db_agent/graph/state.py src/db_agent/graph/nodes.py src/db_agent/graph/build.py src/db_agent/api/app.py tests/test_examples_retriever.py tests/test_graph_nodes.py tests/test_graph_chain.py
git commit -m "example retrieval T5: retriever factory + retrieve_examples node wired"
```

---

## Task 6: Full suite + ruff + live e2e + docs

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Full offline suite**

Run: `uv run pytest -q`
Expected: all pass, 9 deselected. (Chain/api/observability answered-paths are
unaffected: the default retriever is the no-op, so no extra LLM call is scripted.)

- [ ] **Step 2: Lint + format**

Run: `uv run ruff check src tests && uv run ruff format src tests`
Expected: clean; commit any reformatting.

- [ ] **Step 3: Live e2e (best-effort, gateway healthy)**

Build a tiny index from a sample obs log and verify retrieval injects a relevant
example, using real `qwen-embedding`:

```bash
# 1. point at (or create) a JSONL log with a few answered runs, then:
uv run python -m db_agent.examples.build <path/to/obs.jsonl> ./_example_index.npz
# 2. set DBAGENT_EXAMPLE_INDEX_PATH=./_example_index.npz in the environment / .env
# 3. run a question similar to a logged one through run_agent (real deps) and confirm
#    the generated SQL prompt carried a past example and the answer is correct.
```

Report the retrieved example(s) + generated SQL. If the obs log is empty, generate a
few runs first (the JsonlObserver writes them when `DBAGENT_OBSERVABILITY_LOG_PATH` is
set). Clean up `_example_index.npz` after. Best-effort; does not block.

- [ ] **Step 4: Update CLAUDE.md**

In `CLAUDE.md`, move pgvector/example-retrieval out of "Still deferred" into the built
list with a one-paragraph summary: local `.npz` vector index built offline from the
obs log by `python -m db_agent.examples.build`; `retrieve_examples` node embeds the
question via `qwen-embedding`, cosine top-k over same-domain examples (using `raw_sql`,
never secured SQL), injected into `sql_messages`; off by default
(`example_index_path=None`), fail-soft. Add `examples/` to the Layout block and the
`model_embed` / `example_index_path` / `example_top_k` settings note. Add `retrieve_examples`
to the graph flow line (`assemble → retrieve_examples → generate_sql`).

- [ ] **Step 5: Commit + push**

```bash
git add CLAUDE.md
git commit -m "example retrieval T6: docs + suite green"
git push origin main
```

---

## Notes for the implementer

- **Off by default:** `example_index_path=None` → `default_retriever` returns the
  no-op → zero behavior change and zero extra gateway calls until an index is built
  and the path is set. All existing tests rely on this.
- **`raw_sql`, not secured `sql`:** the builder reads `raw_sql` so examples never teach
  the model to write permission filters (deterministic, not the model's job).
- **Fail-soft everywhere:** missing/corrupt index, embed failure, empty domain subset
  → no examples, generation proceeds as today.
- **numpy** is already installed via scipy; Task 1 just declares it as a direct dep.
- `from __future__ import annotations` headers on every new module; ruff stays `py311`.
