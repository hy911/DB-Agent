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
    "5. Gene names are already resolved to canonical symbols and given to you. "
    "Filter the omics table's gene_symbol column directly (e.g. "
    "med.gene_symbol = 'EGFR') — do NOT JOIN gene_info to translate them. If you "
    'ever do reference gene_info, its column is "Symbol" with a capital S and '
    'MUST be double-quoted (g."Symbol"); a bare g.Symbol is folded to lowercase '
    "by PostgreSQL and errors as 'column g.symbol does not exist'.\n"
    "6. Use ONLY tables that appear in the schema context. Never invent a table "
    "name (e.g. rnaseq_data, rnaseq_variant_data do not exist); a model's RNA-seq "
    "identifier is model_desc_info.rnaseq_id.\n"
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
    "Do NOT exclude or subset rows when stating that total: EVERY returned row "
    "counts, including control / vehicle / placebo rows — the SQL already returned "
    "exactly the rows that answer the question, so the headline total always equals "
    "the authoritative row count. You may describe sub-groups (e.g. how many are "
    "treatment vs control), but the stated total must be that exact number. "
    "Do NOT enumerate a long list item by item: when there are many rows or a "
    "column holds a long list, give that authoritative count and a few "
    "representative examples, and note that the full result is shown in the table "
    "below — never reproduce hundreds of values in prose. "
    "If the user asked for an image/picture (成像图/图片) but the rows are live-imaging "
    "NUMBERS (total_flux / avg_radiance), explain that the database stores in-vivo "
    "imaging measurements, not pictures, and report those numbers."
)


def intent_messages(question: str) -> list[dict[str, str]]:
    """MAS top-level intent router: pick which *worker* handles the request.

    This is ABOVE the domain router — it classifies the kind of task/audience, not
    the data domain. Three workers: `explore` (ad-hoc data query & analysis — the
    default), `recommend` (pick/recommend suitable mouse models for a target or
    indication), `vdr` (due-diligence factual Q&A: take rate, latency, model facts).
    """
    system = (
        "You classify a user's request for a mouse tumor-model database assistant "
        "into exactly ONE worker. Reply with a single lowercase word, nothing else.\n"
        "- recommend: the user wants you to PICK or RECOMMEND suitable mouse models "
        "for a drug target, mutation, expression profile or indication, to use for "
        "validation (e.g. '推荐适合 HER2 低表达的 ADC 验证模型', '帮我选几个 KRAS G12C "
        "突变的 PDX 模型做药效', 'which models fit an EGFR-mutant NSCLC program').\n"
        "- vdr: a due-diligence / business factual question about a model's "
        "characteristics or historical conclusions — take rate (成瘤率), latency "
        "(潜伏期), strain, past efficacy summary (e.g. 'CT26 的成瘤率是多少', "
        "'这个模型平均潜伏期多久', 'what was the historical efficacy of MC38').\n"
        "- explore: anything else — an ad-hoc data query, listing, count, "
        "aggregation, statistic or curve over expression / mutation / efficacy / "
        "modeling data (e.g. '查 EGFR 在所有 PDX 里的表达量', 'CT26 的阳性药数据', "
        "'画一下生存曲线'), AND greetings / capability / out-of-scope questions.\n"
        "When unsure, answer 'explore'. Reply with one of: recommend, vdr, explore."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]


def criteria_messages(
    question: str, cancer_types: list[str], model_types: list[str]
) -> list[dict[str, str]]:
    """Extract structured model-selection criteria from a recommendation brief.

    Output is strict JSON (parsed by Criteria.from_json, which tolerates noise).
    cancer_type / model_type must map to the provided closed enums or be null.
    """
    cancers = ", ".join(cancer_types)
    models = ", ".join(model_types)
    system = (
        "You extract structured selection criteria from a request to RECOMMEND mouse "
        "tumor models. Output ONLY a JSON object, no prose, with these keys:\n"
        '- "mutated_genes": list of gene symbols the model should carry a mutation in '
        "(keep the user's token as written, e.g. KRAS, HER2 — they are resolved later).\n"
        '- "expression": list of {"gene": <symbol>, "direction": "high"|"low"} for '
        "required expression levels.\n"
        f'- "cancer_type": ONE English histology mapped to the closest of [{cancers}], '
        "or null. Map any subtype/Chinese/synonym to the closest listed value "
        "(e.g. 非小细胞肺癌/NSCLC → 'Lung Carcinoma').\n"
        f'- "model_type": ONE of [{models}] or null.\n'
        "Use [] or null for anything the brief does not specify. "
        "Example — for '推荐 KRAS 突变且 HER2 低表达的 PDX 肺癌模型' output: "
        '{"mutated_genes": ["KRAS"], "expression": [{"gene": "HER2", "direction": "low"}], '
        '"cancer_type": "Lung Carcinoma", "model_type": "PDX"}. '
        "Output only the JSON object."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]


def recommend_summary_messages(question: str, table_preview: str) -> list[dict[str, str]]:
    """A persuasive-but-factual NL summary of the ranked recommendation table."""
    system = (
        "You are a scientific consultant recommending mouse tumor models to a client. "
        "Given the client's brief and a ranked table of candidate models (with how many "
        "of the requested criteria each matched and any historical efficacy evidence), "
        "write a concise, professional recommendation in the SAME language as the brief. "
        "Lead with the single best-matching model and say WHY (which criteria it met, and "
        "cite efficacy evidence if present). Mention the runner-up(s) briefly. Use ONLY "
        "the rows given — never invent models, scores, or drug results. If no model "
        "matched, say so plainly and suggest relaxing a criterion. Do not output a table; "
        "the table is shown separately."
    )
    user = f"Client brief: {question}\n\nRanked candidates:\n{table_preview}"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def vdr_answer_messages(question: str, cards: list[str]) -> list[dict[str, str]]:
    """Grounded answer for a due-diligence question, using ONLY de-sensitized cards."""
    rendered = "\n".join(cards)
    system = (
        "You answer due-diligence questions about mouse tumor models for a business-"
        "development context, using ONLY the provided de-sensitized fact cards. Cite the "
        "model_id(s) you relied on in square brackets, e.g. [CT26]. Use ONLY numbers and "
        "facts present in the cards — never invent or estimate. If the cards do not contain "
        "the answer (for example a metric like 成瘤率/take rate that is not shown), say "
        "plainly that the information is not available in the provided materials and suggest "
        "asking the data team. Reply in the SAME language as the question; be concise."
    )
    user = f"Question: {question}\n\nFact cards:\n{rendered}"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def route_messages(question: str, domains: list[Domain]) -> list[dict[str, str]]:
    listing = "\n".join(f"- {d.name}: {d.label}" for d in domains)
    system = (
        "You are a domain router for a mouse tumor-model database agent. The "
        "in-scope domains are:\n"
        f"{listing}\n\n"
        "Route by the kind of measurement the answer hinges on, NOT by incidental "
        "wording: a gene's expression LEVEL (高/低表达, 表达量) → expression; a gene's "
        "mutation/variant → mutation; drug efficacy (TGI, 给药, 生长曲线) → efficacy; "
        "model-building/immunophenotyping/PK data → modeling. When the question is "
        "ONLY about the models themselves — counting/listing models, their type "
        "(PDX/CDX), cancer type, name/ID, MSI, or an identifier/mapping like the "
        "RNA-seq id (rnaseq_id) — with NO expression/mutation/efficacy/modeling "
        "measurement involved, route to 'model' (e.g. '一共有多少个 PDX 模型', "
        "'MDA-MB-231 的 rnaseq_id 是多少', '有哪些瘤种'). But when a measurement IS "
        "involved, model attributes such as model type (CDX/PDX), cancer type and "
        "model name live on the shared model spine and are available in EVERY domain, "
        "so they don't pull routing toward 'model' — e.g. 'HER2-high-expression CDX "
        "models' is an expression question, not model and not modeling. "
        "Reply with the name(s) of EVERY in-scope domain the question could be "
        "answered from, comma-separated and verbatim (e.g. 'expression' or "
        "'mutation, expression'). If the question clearly fits one domain, give just "
        "that one; if it could reasonably mean several (e.g. 'CT26 的数据', 'Trp53 "
        "相关数据'), list them all — do NOT ask the user to choose. "
        "Start your reply with 'clarify: ' followed by a real, helpful sentence "
        "ONLY for a greeting, a meta question (what can you do), or a request no "
        "domain covers — never to ask which data type they want for a real data "
        "question. For a greeting/meta question, briefly say you can query efficacy, "
        "modeling, gene-expression or mutation data for mouse tumor models and invite "
        "a specific question (e.g. 'clarify: 您好！我可以帮您查询小鼠肿瘤模型的药效、建模、"
        "基因表达或突变数据，请问您想了解什么？'). For out-of-scope, say briefly it is "
        "out of scope. ALWAYS write the clarify sentence in the SAME language as the "
        "user's question (a Chinese question gets a Chinese sentence). Write a real, "
        "complete sentence — never echo this instruction's placeholder/label text "
        "verbatim (do NOT reply literally 'out-of-scope', 'out-of-scope note', 'what "
        "can you do', or 'clarify'). Reply with nothing else."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]


def multi_intro_messages(question: str, sections: list[tuple[str, int]]) -> list[dict[str, str]]:
    """A one-sentence intro for a multi-domain fan-out: how many categories were
    found, inviting the user to pick which to view below."""
    listing = "; ".join(f"{label}: {n}" for label, n in sections)
    system = (
        "The user's question spans several data categories, so the agent queried all "
        "of them. Write ONE short sentence (no bullet lists) in the SAME language as "
        "the user's question: state how many data categories were found, give each "
        "category with its row count using the exact numbers provided (do not recount "
        "or invent), and invite the user to pick which to view in the sections below. "
        "Reply with that sentence only."
    )
    user = f"Question: {question}\n\nCategories found (label: row count): {listing}"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
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
        "NEVER just filter or drop rows: a plain `SELECT * FROM result WHERE …` that "
        "only excludes rows (e.g. removing vehicle / control rows, or keeping one "
        "drug/model) is NOT post-processing — the row filtering already happened in the "
        "main SQL, and dropping rows here would contradict the result the user sees. If "
        "the user just wants to see the data, reply NONE. "
        "Otherwise reply with exactly one SELECT over `result` that AGGREGATES or "
        "RESHAPES (GROUP BY / pivot / correlation / quantiles), using only the `result` "
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
    count_prefixed: bool = False,
) -> list[dict[str, str]]:
    count_line = ""
    if count_prefixed and rowcount is not None:
        # The system already prepended an authoritative "N records" line, so the LLM
        # must NOT state its own total (it tends to undercount a multi-row list to the
        # number of distinct drugs/models). Free it to describe instead.
        count_line = (
            f"\n\nA line stating the total ({rowcount} records) has ALREADY been shown to "
            f"the user. Do NOT state any record count or total yourself — only describe the "
            f"rows: notable drugs / values and patterns, with a few representative examples. "
            f"If you mention how many distinct drugs / models there are, label it as '…种', "
            f"never as the record total."
        )
    elif rowcount is not None:
        if truncated:
            count_line = (
                f"\n\nAuthoritative total rows = {rowcount} (capped by LIMIT). Report it "
                f"as a lower bound ('at least {rowcount}'). The rows below are only a "
                f"preview sample."
            )
        else:
            count_line = (
                f"\n\nIMPORTANT — the SQL returned exactly {rowcount} result rows; each row "
                f"is one record, and these {rowcount} records ARE the complete answer. When "
                f"you state how many records / 条 / results there are, you MUST say {rowcount}. "
                f"This is NOT the same as the number of distinct drugs or models: do not "
                f"collapse the {rowcount} records down to a count of unique drug names, and "
                f"do not drop vehicle / control / 对照 rows — the question's wording (e.g. "
                f"'阳性药数据') never licenses that. You MAY separately note how many distinct "
                f"drugs there are as a '…种药物' figure, but the record total stays {rowcount}. "
                f"The rows below are only a preview sample of the {rowcount}."
            )
    user = f"Question: {question}\n\nSQL run:\n{sql}{count_line}\n\nResult rows:\n{rows_preview}"
    return [
        {"role": "system", "content": _ANSWER_SYSTEM},
        {"role": "user", "content": user},
    ]
