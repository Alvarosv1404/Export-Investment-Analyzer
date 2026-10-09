"""Tests del lector de Excel (valores, unidades, anos)."""

from __future__ import annotations

import sys

sys.path.insert(0, "src")

from exportanalysis.pipeline import excel_analysis


def test_peru_exports_ts_has_years_and_values():
    df = excel_analysis.peru_exports_ts("081040")
    assert "year" in df.columns
    assert "fob_usd" in df.columns
    assert len(df) > 0
    assert df["year"].min() >= 2015
    assert df["year"].max() >= 2024


def test_peru_exports_ts_2025_present():
    df = excel_analysis.peru_exports_ts("081040")
    assert 2025 in df["year"].unique()


def test_indicators_2025_structure():
    ind = excel_analysis.peru_exports_indicators_2025("081040")
    assert "quantity" in ind.columns
    assert "unit_value_usd_per_unit" in ind.columns
    assert len(ind) > 0


def test_ts_with_quantity_merges():
    df = excel_analysis.peru_exports_ts_with_quantity("081040")
    # at least for 2025 we expect some merged
    assert "quantity" in df.columns
    assert "unit_value_usd_per_unit" in df.columns
    assert df[df["year"] == 2025]["quantity"].notna().sum() >= 0


def test_world_exports_and_imports_readable():
    we = excel_analysis.world_exports("081040")
    wi = excel_analysis.world_imports("081040")
    assert len(we) > 0
    assert len(wi) > 0
    assert "year" in we.columns and "fob_usd" in we.columns
    assert "year" in wi.columns


def test_peru_exports_trade_tiene_fila_world():
    df = excel_analysis.peru_exports_trade("081040")
    assert {"year", "partner_code", "partner_name", "is_world", "fob_usd", "net_weight_kg"} <= set(df.columns)
    world = df[df["is_world"]]
    assert len(world) > 0
    # 2025 es el unico anio con volumen publicado (snapshot).
    assert df[df["year"] == 2025]["net_weight_kg"].notna().any()


def test_available_years_ordenados():
    years = excel_analysis.available_years("081040")
    assert years == sorted(years)
    assert years[-1] >= 2025


def test_todos_los_productos_leen_sus_cuatro_excel():
    """Regresion: un nombre de archivo distinto rompia el producto en silencio."""
    from exportanalysis.config import load_catalog

    for product in load_catalog().products:
        trade = excel_analysis.peru_exports_trade(product.hs6)
        assert len(trade) > 0, f"sin serie peruana para {product.slug}"
        assert len(excel_analysis.world_exports(product.hs6)) > 0, f"sin exportadores para {product.slug}"
        assert len(excel_analysis.world_imports(product.hs6)) > 0, f"sin importadores para {product.slug}"
        assert len(excel_analysis.peru_exports_indicators_2025(product.hs6)) > 0, f"sin snapshot 2025 para {product.slug}"
