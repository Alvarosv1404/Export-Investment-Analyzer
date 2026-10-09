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
