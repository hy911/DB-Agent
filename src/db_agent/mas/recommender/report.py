"""Render a recommendation as a self-contained HTML report, optionally a PDF.

HTML is always available (jinja2, a core dep). PDF is OPTIONAL: WeasyPrint has heavy
native deps (GTK/Pango/Cairo) that are painful on Windows, so it is lazy-imported
and `render_pdf` returns None when it is unavailable — callers degrade to the HTML
(which the browser can print to PDF). Install with the `report` extra to enable it.
"""

from __future__ import annotations

from jinja2 import Environment, select_autoescape

from db_agent.mas.recommender.model import Recommendation

_env = Environment(autoescape=select_autoescape(["html", "xml"]))

_TEMPLATE = _env.from_string(
    """<!DOCTYPE html>
<html lang="zh">
<head><meta charset="utf-8"><title>模型推荐报告</title>
<style>
  body { font-family: system-ui, "Segoe UI", Arial, sans-serif; color: #1a1a1a; margin: 32px; }
  h1 { font-size: 22px; margin-bottom: 4px; }
  .meta { color: #666; font-size: 13px; margin-bottom: 20px; }
  .summary { background: #f6f8fa; border-left: 4px solid #2563eb; padding: 12px 16px;
             border-radius: 4px; margin-bottom: 24px; white-space: pre-wrap; }
  table { border-collapse: collapse; width: 100%; font-size: 13px; }
  th, td { border: 1px solid #d0d7de; padding: 6px 10px; text-align: left; vertical-align: top; }
  th { background: #f0f3f6; }
  .score { font-weight: 600; color: #2563eb; }
  .ev { color: #444; font-size: 12px; }
  .notes { color: #9a6700; font-size: 12px; margin-top: 16px; }
  .empty { color: #666; font-style: italic; }
</style></head>
<body>
  <h1>小鼠肿瘤模型推荐报告</h1>
  <div class="meta">需求：{{ rec.question }}</div>
  <div class="summary">{{ rec.summary }}</div>
  {% if rec.models %}
  <table>
    <thead><tr>
      <th>#</th><th>模型</th><th>类型</th><th>瘤种</th><th>匹配度</th>
      <th>命中条件</th><th>药效证据</th>
    </tr></thead>
    <tbody>
    {% for m in rec.models %}
      <tr>
        <td>{{ loop.index }}</td>
        <td>{{ m.model_id or m.model_name or m.model_uuid }}</td>
        <td>{{ m.model_type or '-' }}</td>
        <td>{{ m.cancer_type or '-' }}</td>
        <td class="score">{{ m.score }}</td>
        <td>{{ m.matched | join('；') or '-' }}</td>
        <td class="ev">
          {%- if m.evidence -%}
            {%- for e in m.evidence[:5] -%}
              {{ e.drug_name }} (TGI={{ e.tgi_tv }}){% if not loop.last %}；{% endif %}
            {%- endfor -%}
            {%- if m.evidence | length > 5 %} …共 {{ m.evidence | length }} 条{% endif -%}
          {%- else -%}无{%- endif -%}
        </td>
      </tr>
    {% endfor %}
    </tbody>
  </table>
  {% else %}
  <p class="empty">未找到符合条件的候选模型。</p>
  {% endif %}
  {% if rec.notes %}<div class="notes">说明：{{ rec.notes | join('；') }}</div>{% endif %}
</body>
</html>"""
)


def render_html(rec: Recommendation) -> str:
    return _TEMPLATE.render(rec=rec)


def render_pdf(html: str) -> bytes | None:
    """PDF bytes if WeasyPrint is installed, else None (caller falls back to HTML)."""
    try:
        from weasyprint import HTML  # lazy: optional heavy native dependency
    except Exception:
        return None
    return HTML(string=html).write_pdf()
