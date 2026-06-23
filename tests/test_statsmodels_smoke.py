from __future__ import annotations


def test_statsmodels_two_way_anova_runs():
    import pandas as pd
    import statsmodels.formula.api as smf
    from statsmodels.stats.anova import anova_lm

    df = pd.DataFrame(
        {
            "y": [1.0, 2.0, 1.5, 8.0, 9.0, 8.5, 2.0, 1.0, 9.5, 8.0, 1.0, 2.5],
            "a": ["x", "x", "x", "y", "y", "y", "x", "x", "y", "y", "x", "x"],
            "b": ["p", "p", "q", "p", "p", "q", "q", "p", "q", "p", "p", "q"],
        }
    )
    model = smf.ols("y ~ C(a) + C(b) + C(a):C(b)", data=df).fit()
    table = anova_lm(model, typ=2)
    assert "C(a)" in table.index
    assert float(table.loc["C(a)", "PR(>F)"]) < 0.05  # factor a clearly separates y
