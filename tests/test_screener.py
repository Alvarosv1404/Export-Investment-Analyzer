"""Tests del screener de productos (ranking offline)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from exportanalysis.config import load_catalog  # noqa: E402
from exportanalysis.pipeline import screener  # noqa: E402


def test_screener_corre_todo_el_catalogo():
    result = screener.screen_products()
    assert result["count"] == len(load_catalog().products)
    assert result["products"], "el screener no devolvio productos"


def test_screener_tiene_las_metricas_ponderadas():
    keys = {metric["key"] for metric in screener.screen_products()["metrics"]}
    assert {"market_size", "growth", "margin", "returns"} <= keys
    for metric in screener.screen_products()["metrics"]:
        assert "weight" in metric and "lower_is_better" in metric and "basis" in metric


def test_puntajes_en_rango_y_ranks_consistentes():
    products = screener.screen_products()["products"]
    for product in products:
        if product["score"] is not None:
            assert 0.0 <= product["score"] <= 100.0
        assert 0.0 <= product["score_confidence"] <= 100.0
        for score in product["scores"].values():
            assert score is None or 0.0 <= score <= 100.0

    ranked = [p for p in products if p["rank"] is not None]
    assert [p["rank"] for p in ranked] == list(range(1, len(ranked) + 1))
    scores = [p["score"] for p in ranked]
    assert scores == sorted(scores, reverse=True)


def test_screener_respeta_una_seleccion():
    result = screener.screen_products(["cafe_verde", "arandano"])
    assert result["count"] == 2
    assert {p["slug"] for p in result["products"]} == {"cafe_verde", "arandano"}


def test_producto_marcado_en_supuestos_vigila_readiness():
    product = next(p for p in screener.screen_products()["products"] if p["slug"] == "cafe_verde")
    readiness = product["readiness"]
    assert readiness["trademap_count"] == readiness["trademap_expected"]
    assert readiness["assumptions_present"] is True
    assert readiness["assumptions_verified"] is False  # siguen siendo ejemplos
