from __future__ import annotations

from tests._rec_helpers import FULL_CRITERIA, FULL_GENE_MAP, RecLLM, RecReplica, rec_resolver

from db_agent.config import Settings
from db_agent.graph.state import Deps
from db_agent.mas.recommender import run_recommendation
from db_agent.semantic import load_semantic_layer

SETTINGS = Settings(_env_file=None)
LAYER = load_semantic_layer(SETTINGS.semantic_layer_path)


def _deps(llm, replica, resolver):
    return Deps(llm=llm, replica=replica, layer=LAYER, settings=SETTINGS, resolve_gene=resolver)


async def test_pipeline_ranks_and_attaches_evidence():
    deps = _deps(RecLLM(FULL_CRITERIA), RecReplica(), rec_resolver(FULL_GENE_MAP))
    rec = await run_recommendation("推荐 KRAS 突变 HER2 高表达的 PDX 肺癌模型", deps=deps)
    assert rec.summary == "推荐 m1。"
    assert [m.model_id for m in rec.models] == ["A1", "A3", "A2"]  # by descending score
    top = rec.models[0]
    assert top.score == 4  # KRAS mutation + HER2 high + Lung Carcinoma + PDX
    assert top.evidence and top.evidence[0]["drug_name"] == "DrugX"


async def test_pipeline_no_criteria_returns_note():
    rec = await run_recommendation("你好", deps=_deps(RecLLM("{}"), RecReplica(), rec_resolver({})))
    assert rec.models == ()
    assert "no_criteria" in rec.notes
    assert "筛选条件" in rec.summary  # zh-localized guidance


async def test_pipeline_unresolved_gene_is_noted_and_empty():
    deps = _deps(RecLLM('{"mutated_genes": ["NOTAGENE"]}'), RecReplica(), rec_resolver({}))
    rec = await run_recommendation("推荐 NOTAGENE 突变模型", deps=deps)
    assert rec.models == ()  # nothing resolved → no candidates
    assert any("NOTAGENE" in n for n in rec.notes)


async def test_pipeline_attribute_only_brief_seeds_from_attributes():
    # cancer_type + model_type only (no gene): candidates come from the attribute seed
    deps = _deps(
        RecLLM('{"cancer_type": "Lung Carcinoma", "model_type": "PDX"}'),
        RecReplica(),
        rec_resolver({}),
    )
    rec = await run_recommendation("推荐肺癌 PDX 模型", deps=deps)
    assert {m.model_id for m in rec.models} == {"A1", "A3"}  # the two Lung/PDX models
    assert all(m.score == 2 for m in rec.models)  # matched both attribute signals
