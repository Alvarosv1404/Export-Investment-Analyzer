"""Tests para comparacion entre productos."""

from __future__ import annotations

import sys

sys.path.insert(0, "src")

from exportanalysis.pipeline import comparison


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
        # La CAGR es None si el primer ano es 0 (Peru no reporto ese ano), no un error.
        assert p["cagr_value"] is None or p["cagr_value"] > -1
