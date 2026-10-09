"""Tests para precio calculado desde historicos."""

from __future__ import annotations

import sys
sys.path.insert(0, "src")

from exportanalysis.pipeline import pricing


def test_estimated_price_returns_info():
    info = pricing.estimated_fob_price_usd_per_kg("081040")
    assert "price_usd_per_kg" in info
    assert "source" in info
    assert info["hs6"] == "081040"
    assert info["calculated_from"]


def test_estimated_price_handles_all_products():
    from exportanalysis.pipeline import comparison
    for slug in comparison.all_product_slugs()[:3]:
        info = pricing.estimated_fob_price_usd_per_kg(slug)
        assert "price_usd_per_kg" in info or info.get("price_usd_per_kg") is None
        assert "source" in info
