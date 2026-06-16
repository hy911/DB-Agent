"""Pure prompt builders. Each returns a list of chat messages; no I/O, no state."""

from __future__ import annotations

_ROUTE_SYSTEM = (
    "You are a domain router for a mouse tumor-model database agent. The only "
    "in-scope domain is 'efficacy' (drug efficacy studies: tumor volume, TGI, "
    "survival). If the question is answerable from efficacy data, reply with "
    "exactly the word 'efficacy'. Otherwise reply 'clarify: <one short question "
    "asking the user to clarify, or stating it is out of scope>'. Reply with "
    "nothing else."
)

_SQL_SYSTEM = (
    "You write exactly one read-only PostgreSQL SELECT for the efficacy domain. "
    "Use only the tables and columns in the provided schema context. Do not write "
    "INSERT/UPDATE/DELETE/DDL. Return only the SQL, with no prose and no code "
    "fences."
)

_ANSWER_SYSTEM = (
    "You answer the user's question in natural language using the SQL result "
    "rows. Be concise and factual. If there are no rows, say plainly that no "
    "matching data was found."
)


def route_messages(question: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": _ROUTE_SYSTEM},
        {"role": "user", "content": question},
    ]


def sql_messages(
    question: str, context: str, prior_error: str | None = None
) -> list[dict[str, str]]:
    user = f"Schema context:\n{context}\n\nQuestion: {question}"
    if prior_error is not None:
        user += f"\n\nPrevious attempt failed with this database error; fix the SQL:\n{prior_error}"
    return [
        {"role": "system", "content": _SQL_SYSTEM},
        {"role": "user", "content": user},
    ]


def answer_messages(question: str, sql: str, rows_preview: str) -> list[dict[str, str]]:
    user = f"Question: {question}\n\nSQL run:\n{sql}\n\nResult rows:\n{rows_preview}"
    return [
        {"role": "system", "content": _ANSWER_SYSTEM},
        {"role": "user", "content": user},
    ]
