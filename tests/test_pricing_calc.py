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
    """Todos los productos deben dar un precio FOB positivo y finito."""
    from exportanalysis.config import load_catalog
    from exportanalysis.pipeline import comparison

    for product in load_catalog().products:
        info = pricing.estimated_fob_price_usd_per_kg(product.hs6)
        assert "source" in info
        price = info.get("price_usd_per_kg")
        assert price is not None, f"{product.slug} sin precio calculable"
        assert price > 0

    # Un slug no es un hs6: no debe reventar, solo no encontrar archivo.
    for slug in comparison.all_product_slugs()[:3]:
        info = pricing.estimated_fob_price_usd_per_kg(slug)
        assert "source" in info
