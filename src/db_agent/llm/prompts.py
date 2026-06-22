"""Pure prompt builders. Each returns a list of chat messages; no I/O, no state."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from db_agent.examples.model import Example
    from db_agent.semantic.model import Domain

_SQL_SYSTEM = (
    "You write exactly one read-only PostgreSQL SELECT for a mouse tumor-model "
    "database. "
    "Use only the tables and columns in the provided schema context. Do not write "
    "INSERT/UPDATE/DELETE/DDL. "
    "Plain descriptive aggregation (COUNT/AVG/SUM/GROUP BY) is fine for descriptive "
    "questions. But do NOT compute inferential statistics or test statistics "
    "(t / F / chi-square / p-values) or implement a statistical test in SQL. When the "
    "question asks whether a difference is significant, for a p-value, or for a named "
    "test (t-test / ANOVA / survival), instead return the raw per-row data that test "
    "needs (e.g. the group column and the value column, or duration + event + group) "
    "and let the system run the test. "
    "Return only the SQL, with no prose and no code fences."
)

_ANSWER_SYSTEM = (
    "You answer the user's question in natural language using the SQL result "
    "rows. Be concise and factual. If there are no rows, say plainly that no "
    "matching data was found."
)


def route_messages(question: str, domains: list[Domain]) -> list[dict[str, str]]:
    listing = "\n".join(f"- {d.name}: {d.label}" for d in domains)
    system = (
        "You are a domain router for a mouse tumor-model database agent. The "
        "in-scope domains are:\n"
        f"{listing}\n\n"
        "If the question is answerable from exactly one of these domains, reply "
        "with that domain's name verbatim (e.g. 'efficacy'). Otherwise reply "
        "'clarify: <one short question asking the user to clarify, or stating it "
        "is out of scope>'. Reply with nothing else."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]


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


def extract_genes_messages(question: str) -> list[dict[str, str]]:
    system = (
        "You extract gene names or symbols mentioned in the user's question for a "
        "gene-expression database. List each gene mention exactly as the user "
        "wrote it, comma-separated. If no gene is mentioned, reply with the single "
        "word NONE. Reply with nothing else."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]


def analysis_messages(question: str, columns: list[str], rows_preview: str) -> list[dict[str, str]]:
    system = (
        "You decide whether answering the user's question needs post-processing of "
        "an already-fetched result set, and if so write ONE DuckDB SQL SELECT to do "
        "it. The result set is a single in-memory table named `result` with the "
        "given columns. This step is for DESCRIPTIVE post-processing only — "
        "aggregation / reshaping / pivot / correlation / quantiles. Do NOT compute "
        "inferential statistics or test statistics here (t / F / chi-square / "
        "p-values, ANOVA, regression, survival): if the question needs a statistical "
        "test, reply with the single word NONE and let the dedicated stats step run "
        "it. If the rows already answer the question as-is, also reply NONE. "
        "Otherwise reply with exactly one SELECT over `result` (descriptive "
        "aggregation / pivot / correlation / quantiles), using only the `result` "
        "table and no file or external functions. Reply with the SQL or NONE and "
        "nothing else."
    )
    user = (
        f"Question: {question}\n\n"
        f"result columns: {', '.join(columns)}\n\n"
        f"Sample rows:\n{rows_preview}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def stat_messages(
    question: str, columns: list[str], rows_preview: str, catalog: str
) -> list[dict[str, str]]:
    system = (
        "You decide whether answering the question needs a statistical test over an "
        "already-fetched result table named `result`. If so, pick ONE test from the "
        "catalog and map its parameters to the table's columns. Available tests:\n"
        f"{catalog}\n\n"
        "If the question asks whether a difference is significant, for a p-value, or "
        "for a named test, AND the table has the columns that test needs, you SHOULD "
        "emit the request rather than declining. Reply with exactly one JSON object: "
        '{"function": <name>, "params": {<param>: <column-name-or-scalar>, ...}}. '
        "Map column-typed params to column names from the table; use only those "
        "columns. If no statistical test is needed, reply with the single word NONE. "
        "Reply with the JSON object or NONE and nothing else."
    )
    user = (
        f"Question: {question}\n\n"
        f"result columns: {', '.join(columns)}\n\n"
        f"Sample rows:\n{rows_preview}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def stat_answer_messages(
    question: str, sql: str, analysis_sql: str | None, stat_summary: str
) -> list[dict[str, str]]:
    system = (
        "You answer the user's question in natural language using a statistical test "
        "result. State the test used, the key statistic and p-value, the per-group "
        "figures, and clearly convey the caveats about assumptions. Be concise and "
        "factual; do not overstate significance."
    )
    reshape = f"\n\nReshape SQL:\n{analysis_sql}" if analysis_sql else ""
    user = (
        f"Question: {question}\n\nSQL run:\n{sql}{reshape}\n\n"
        f"Statistical test result:\n{stat_summary}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def answer_messages(question: str, sql: str, rows_preview: str) -> list[dict[str, str]]:
    user = f"Question: {question}\n\nSQL run:\n{sql}\n\nResult rows:\n{rows_preview}"
    return [
        {"role": "system", "content": _ANSWER_SYSTEM},
        {"role": "user", "content": user},
    ]
