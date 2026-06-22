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
