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
    metrics = screener.screen_products()["metrics"]
    keys = {metric["key"] for metric in metrics}
    assert keys == {"market_size", "growth", "concentration", "volatility"}
    for metric in metrics:
        assert "weight" in metric and "lower_is_better" in metric and "basis" in metric
        assert metric["basis"] == "dato publicado"


def test_puntajes_en_rango_y_ranks_consistentes():
    products = screener.screen_products()["products"]
    for product in products:
        if product["score"] is not None:
            assert 0.0 <= product["score"] <= 100.0
            assert product["score_confidence"] == 100.0
        assert 0.0 <= product["score_confidence"] <= 100.0
        assert all(value is not None for value in product["values"].values())
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


def test_readiness_solo_muestra_disponibilidad_de_fuentes():
    product = next(p for p in screener.screen_products()["products"] if p["slug"] == "cafe_verde")
    readiness = product["readiness"]
    assert readiness["trademap_count"] == readiness["trademap_expected"]
    assert readiness["sunat"] is True
    assert "assumptions_present" not in readiness
    assert "assumptions_verified" not in readiness


def test_metricas_de_ranking_se_calculan_sin_supuestos_financieros():
    values = screener._extract(
        {
            "market": {
                "latest_fob_usd": 90.0,
                "top5_concentration": 0.6,
                "series": [
                    {"year": 2016, "fob_usd": 0.0},
                    {"year": 2017, "fob_usd": 100.0},
                    {"year": 2018, "fob_usd": 120.0},
                    {"year": 2019, "fob_usd": 90.0},
                ],
            }
        }
    )
    assert values["market_size"] == 90.0
    assert values["growth"] == (90.0 / 100.0) ** 0.5 - 1  # Base is the first positive year.
    assert values["concentration"] == 0.6
    assert values["volatility"] is not None
