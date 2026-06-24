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
    "Follow these rules to avoid common failures:\n"
    "1. Qualify every column with its table alias (e.g. m.model_uuid), especially "
    "when the query JOINs — a bare column shared by two tables errors as ambiguous.\n"
    "2. Many flag/category columns are varchar, NOT boolean. Never compare them to "
    "TRUE/FALSE. Use the exact string value from the column's `values:` hint in the "
    "schema context (e.g. is_cancer_model = 'cancer').\n"
    "3. For category columns, use the values/examples and language hints in the "
    "schema context. When a column lists its `values` (a closed set), the filter "
    "MUST be one of those exact strings — map the question's term (a Chinese name, "
    "an English synonym, or a finer subtype like NSCLC/SCLC) to the closest listed "
    "value (e.g. any lung subtype → 'Lung Carcinoma'); never invent a descriptive "
    "value that is not in the list. Only for open text columns with no listed "
    "values do you fall back to ILIKE '%token%' on a token you expect to appear in "
    "the stored value.\n"
    "4. When you use an aggregate (COUNT/AVG/SUM/MAX/MIN), every non-aggregated "
    "column in the SELECT must appear in GROUP BY.\n"
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
    "rows. Be concise and factual. Reply in the same language as the user's "
    "question. If there are no rows, say plainly that no matching data was found. "
    "When you state how many results there are, use EXACTLY the authoritative row "
    "count given to you — never recount the preview rows, estimate, or merge/"
    "de-duplicate variants on your own; the preview may show only a sample. "
    "Do NOT enumerate a long list item by item: when there are many rows or a "
    "column holds a long list, give that authoritative count and a few "
    "representative examples, and note that the full result is shown in the table "
    "below — never reproduce hundreds of values in prose."
)


def route_messages(question: str, domains: list[Domain]) -> list[dict[str, str]]:
    listing = "\n".join(f"- {d.name}: {d.label}" for d in domains)
    system = (
        "You are a domain router for a mouse tumor-model database agent. The "
        "in-scope domains are:\n"
        f"{listing}\n\n"
        "Route by the kind of measurement the answer hinges on, NOT by incidental "
        "wording: a gene's expression LEVEL (高/低表达, 表达量) → expression; a gene's "
        "mutation/variant → mutation; drug efficacy (TGI, 给药, 生长曲线) → efficacy; "
        "model-building/immunophenotyping/PK data → modeling. Model attributes such "
        "as model type (CDX/PDX), cancer type and model name live on the shared model "
        "spine and are available in EVERY domain, so never route on them — e.g. "
        "'HER2-high-expression CDX models' is an expression question, not modeling. "
        "If the question is answerable from exactly one domain, reply with that "
        "domain's name verbatim (e.g. 'efficacy'). Otherwise reply "
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
        "You extract only biological gene names or symbols mentioned in the user's "
        "question for a gene-expression database (e.g. TP53, EGFR, Trp53, KRAS). "
        "List each gene mention exactly as the user wrote it, comma-separated. "
        "Do NOT extract cell-line or tumor-model identifiers — names like CT26, "
        "MDA-MB-468, MC38, A549, or anything starting with PBMC or ending in "
        "-IVIS / -PDX / -ORT are model names, not genes; never list them. "
        "If no gene is mentioned, reply with the single word NONE. Reply with "
        "nothing else."
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


def answer_messages(
    question: str,
    sql: str,
    rows_preview: str,
    rowcount: int | None = None,
    truncated: bool = False,
) -> list[dict[str, str]]:
    count_line = ""
    if rowcount is not None:
        if truncated:
            count_line = (
                f"\n\nAuthoritative total rows = {rowcount} (capped by LIMIT). Report it "
                f"as a lower bound ('at least {rowcount}'). The rows below are only a "
                f"preview sample."
            )
        else:
            count_line = (
                f"\n\nAuthoritative total rows = {rowcount}. Use this exact number "
                f"verbatim when stating how many results there are; do not recount or "
                f"de-duplicate. The rows below may be a preview sample, not the full set."
            )
    user = f"Question: {question}\n\nSQL run:\n{sql}{count_line}\n\nResult rows:\n{rows_preview}"
    return [
        {"role": "system", "content": _ANSWER_SYSTEM},
        {"role": "user", "content": user},
    ]
