"""Tests para comparacion entre productos."""

from __future__ import annotations

import sys

import pandas as pd
import pytest

sys.path.insert(0, "src")

from exportanalysis.pipeline import comparison


def test_series_incluye_cagr_y_variacion_anual_desde_2016(monkeypatch):
    monkeypatch.setattr(
        comparison.excel_analysis,
        "peru_exports_ts",
        lambda _hs6: pd.DataFrame(
            {
                "year": [2016, 2018, 2025],
                "partnerCd": [842, 842, 842],
                "partnerLabel": ["Estados Unidos"] * 3,
                "fob_usd": [100.0, 121.0, 200.0],
            }
        ),
    )

    def no_quantity(_hs6):
        raise FileNotFoundError("snapshot de cantidades no disponible")

    monkeypatch.setattr(
        comparison.excel_analysis, "peru_exports_ts_with_quantity", no_quantity
    )

    product = comparison._series_product("cafe_verde")
    years = product["series"]

    assert [row["year"] for row in years] == list(range(2016, 2026))
    assert years[0]["fob_usd"] == 100.0
    assert years[1]["fob_usd"] is None
    assert years[1]["value_yoy"] is None
    assert years[2]["value_yoy"] is None
    assert years[2]["cagr_from_2016"] == pytest.approx(0.1)
    assert years[-1]["cagr_from_2016"] == pytest.approx(2 ** (1 / 9) - 1)
    assert product["cagr_value"] == pytest.approx(2 ** (1 / 9) - 1)


def test_compare_products_basic():
    res = comparison.compare_products(["cafe_verde", "arandano", "uva_fresca"])
    assert "products" in res
    assert res["available_count"] >= 2
    for p in res["products"]:
        assert "slug" in p
        assert "available" in p
        if p["available"]:
            assert "cagr_value" in p
            assert "cagr_volume" in p
            assert "cagr_unit_value" in p
            assert "volatility_value" in p
            assert "concentration_top5" in p


def test_compare_products_handles_missing():
    res = comparison.compare_products(["no_existe", "arandano"])
    assert res["available_count"] >= 1


def test_all_slugs():
    slugs = comparison.all_product_slugs()
    assert len(slugs) >= 1
    assert "cafe_verde" in slugs


def test_compara_todos_los_productos():
    """Todos los productos del catalogo deben tener serie comparable."""
    slugs = comparison.all_product_slugs()
    res = comparison.compare_products(slugs)
    assert res["available_count"] == len(slugs)
    for p in res["products"]:
        assert p["available"], f"{p['slug']} no comparable"
        assert p["years"]
        assert len(p["series"]) == len(p["years"])
        assert p["years"] == list(range(2016, 2026))
        # La CAGR es None si el primer ano es 0 (Peru no reporto ese ano), no un error.
        assert p["cagr_value"] is None or p["cagr_value"] > -1
