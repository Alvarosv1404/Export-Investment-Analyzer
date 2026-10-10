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


def test_sunat_price_usado_cuando_existe_el_excel():
    """La pota tiene su Excel SUNAT: el precio debe ser FOB / peso neto (~USD/kg)."""
    info = pricing.sunat_fob_price_usd_per_kg("0307430000")
    assert info.get("price_usd_per_kg") is not None
    assert 0.5 < info["price_usd_per_kg"] < 10
    assert info["calculated_from"] == ["0307430000.xlsx"]
    assert info["last_year"] == 2025


def test_sunat_price_sin_nandina_devuelve_vacio():
    info = pricing.sunat_fob_price_usd_per_kg(None)
    assert info["price_usd_per_kg"] is None
    assert info["calculated_from"] == []
