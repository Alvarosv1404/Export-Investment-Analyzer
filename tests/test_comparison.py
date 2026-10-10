"""Tests para comparacion entre productos."""

from __future__ import annotations

import sys

import pandas as pd
import pytest

sys.path.insert(0, "src")

from exportanalysis.pipeline import comparison


def test_series_incluye_cagr_y_variacion_anual_desde_base(monkeypatch):
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
    assert product["cagr_base_year"] == 2016
    assert years[2]["cagr_from_base"] == pytest.approx(0.1)
    assert years[-1]["cagr_from_base"] == pytest.approx(2 ** (1 / 9) - 1)
    assert product["cagr_value"] == pytest.approx(2 ** (1 / 9) - 1)


def test_cagr_usa_el_primer_anio_con_exportaciones_si_2016_es_cero(monkeypatch):
    """Como la pota: en 2016 vale 0, asi que la base se corre al primer ano real."""
    monkeypatch.setattr(
        comparison.excel_analysis,
        "peru_exports_ts",
        lambda _hs6: pd.DataFrame(
            {
                "year": [2016, 2017, 2018, 2025],
                "partnerCd": [842, 842, 842, 842],
                "partnerLabel": ["Estados Unidos"] * 4,
                "fob_usd": [0.0, 100.0, 121.0, 200.0],
            }
        ),
    )

    def no_quantity(_hs6):
        raise FileNotFoundError("snapshot de cantidades no disponible")

    monkeypatch.setattr(
        comparison.excel_analysis, "peru_exports_ts_with_quantity", no_quantity
    )

    product = comparison._series_product("producto_sin_2016")
    by_year = {row["year"]: row for row in product["series"]}

    assert product["cagr_base_year"] == 2017
    assert by_year[2016]["cagr_from_base"] is None
    assert by_year[2017]["cagr_from_base"] is None
    assert by_year[2018]["cagr_from_base"] == pytest.approx(0.21)
    assert by_year[2025]["cagr_from_base"] == pytest.approx(2 ** (1 / 8) - 1)
    assert product["cagr_value"] == pytest.approx(2 ** (1 / 8) - 1)


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


def test_comparacion_pota_trae_precio_por_kilo_sunat():
    """La pota tiene su Excel SUNAT: la serie incluye el precio FOB / peso neto por anio."""
    import pytest

    from exportanalysis.pipeline import excel_analysis

    summary = excel_analysis.sunat_annual_summary("0307430000")
    product = comparison._series_product("pota_calamar")
    assert product["sunat_available"] is True
    assert product["cagr_price"] is not None
    by_year = {row["year"]: row for row in product["series"]}
    p2025 = by_year[2025]["price_usd_per_kg"]
    sunat_2025 = summary[summary["year"] == 2025].iloc[0]
    assert p2025 == pytest.approx(sunat_2025["price_usd_per_kg"])
    assert 0.5 < p2025 < 10


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
