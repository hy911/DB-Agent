from __future__ import annotations

from db_agent.mas.recommender.model import Criteria, RankedModel, Recommendation
from db_agent.mas.recommender.report import render_html, render_pdf


def _rec():
    m = RankedModel(
        model_uuid="u1",
        model_id="MID1",
        model_name="Name1",
        model_type="PDX",
        cancer_type="Lung Carcinoma",
        score=2,
        matched=("KRAS 突变", "瘤种 Lung Carcinoma"),
        evidence=({"drug_name": "DrugX", "tgi_tv": 85},),
    )
    return Recommendation(
        question="推荐肺癌模型",
        criteria=Criteria(mutated_genes=("KRAS",)),
        models=(m,),
        summary="推荐 MID1。",
        notes=("未能解析基因 ZZZ",),
    )


def test_render_html_contains_model_summary_and_notes():
    html = render_html(_rec())
    assert "MID1" in html
    assert "推荐 MID1" in html  # the summary
    assert "DrugX" in html  # efficacy evidence
    assert "未能解析基因 ZZZ" in html  # notes surfaced


def test_render_html_empty_models_shows_placeholder():
    rec = Recommendation("q", Criteria(), (), summary="无匹配")
    html = render_html(rec)
    assert "未找到符合条件" in html
    assert "无匹配" in html


def test_render_pdf_is_graceful_without_weasyprint():
    # WeasyPrint is an optional extra; absent → None, present → bytes. Either is fine.
    out = render_pdf("<html><body>hi</body></html>")
    assert out is None or isinstance(out, (bytes, bytearray))
