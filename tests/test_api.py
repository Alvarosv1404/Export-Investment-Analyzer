"""Tests de la API.

Se centran en el contrato, no en el formato: que los codigos HTTP sean los
correctos y que la respuesta sea JSON valido. Este ultimo punto importa mas de
lo que parece: un NaN en cualquier parte del payload hace que `JSONResponse`
lanze excepcion y el endpoint devuelva 500 sin explicar por que.
"""

from __future__ import annotations

import json
import math

import pytest

from exportanalysis.api.main import DIST_DIR, _json_safe, app

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def _assert_json_valid(payload) -> None:
    """Recorre el payload buscando valores que JSON no admite."""
    if isinstance(payload, float):
        assert math.isfinite(payload), f"NaN o Infinity en el payload: {payload}"
    elif isinstance(payload, dict):
        for value in payload.values():
            _assert_json_valid(value)
    elif isinstance(payload, list):
        for item in payload:
            _assert_json_valid(item)


class TestJsonSafe:
    def test_nan_a_null(self):
        assert _json_safe(float("nan")) is None
        assert _json_safe(float("inf")) is None
        assert _json_safe(float("-inf")) is None

    def test_finitos_intactos(self):
        assert _json_safe(1.5) == 1.5
        assert _json_safe(0.0) == 0.0
        assert _json_safe(None) is None
        assert _json_safe("texto") == "texto"
        assert _json_safe(True) is True

    def test_recorre_estructuras_anidadas(self):
        out = _json_safe(
            {"a": [float("nan"), {"b": float("inf")}], "c": {"d": 1.0}}
        )
        assert out == {"a": [None, {"b": None}], "c": {"d": 1.0}}

    def test_el_resultado_es_serializable(self):
        json.dumps(_json_safe({"x": float("nan")}))


class TestHealth:
    def test_health(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestProducts:
    def test_catalogo(self, client):
        response = client.get("/api/products")
        assert response.status_code == 200
        data = response.json()
        assert data["reporter"] == 604  # Peru en M49
        assert len(data["products"]) >= 1
        slugs = {p["slug"] for p in data["products"]}
        assert "cafe_verde" in slugs
        for product in data["products"]:
            assert len(product["hs6"]) == 6

    def test_sin_parametros_obligatorios(self, client):
        assert client.get("/api/products").status_code == 200


class TestAnalysis:
    def test_slug_inexistente_da_404(self, client):
        response = client.get("/api/analysis/no_existe")
        assert response.status_code == 404
        assert "detail" in response.json()

    def test_analisis_es_json_valido(self, client):
        """Regresion: un NaN en la serie-rompe la serializacion y da 500."""
        response = client.get("/api/analysis/cafe_verde")
        assert response.status_code == 200
        data = response.json()  # si el body no fuera JSON valido, falla aqui
        _assert_json_valid(data)

    def test_estructura_del_analisis(self, client):
        data = client.get("/api/analysis/cafe_verde").json()
        for key in (
            "slug",
            "product",
            "market",
            "competitors",
            "headroom",
            "unit_economics",
            "landed_cost",
            "investment",
            "data_quality",
        ):
            assert key in data, f"falta la clave {key}"

    def test_el_mercado_trae_anios_con_data(self, client):
        data = client.get("/api/analysis/cafe_verde").json()
        assert data["market"]["available"] is True
        assert len(data["market"]["series"]) >= 1
        assert data["market"]["latest_fob_usd"] > 0

    def test_primer_anio_sin_yoy_uses_null(self, client):
        """El primer ano no tiene ano previo: debe ser null, no NaN ni 0."""
        data = client.get("/api/analysis/cafe_verde").json()
        assert data["market"]["series"][0]["value_yoy"] is None

    def test_el_modelo_declara_el_origen_de_la_rampa(self, client):
        """Un ramp sin origen conocido es un supuesto invisible."""
        data = client.get("/api/analysis/cafe_verde").json()
        ramp_source = data["investment"]["ramp_source"]
        assert ramp_source["source"] in {"mercado", "config"}
        assert ramp_source["reason"]

    def test_target_share_explicito(self, client):
        data = client.get("/api/analysis/cafe_verde?target_share=0.12").json()
        assert data["investment"]["inputs"]["capture_share"] == 0.12

    def test_target_share_fuera_de_rango_da_422(self, client):
        assert client.get("/api/analysis/cafe_verde?target_share=1.5").status_code == 422
        assert client.get("/api/analysis/cafe_verde?target_share=-0.1").status_code == 422

    def test_precio_explicito_se_usa_y_se_marca(self, client):
        data = client.get("/api/analysis/cafe_verde?price_usd_per_kg=6.5").json()
        assert data["unit_economics"]["fob_price_usd_per_kg"] == 6.5
        assert data["data_quality"]["price_source"] == "ajustado por el usuario"

    def test_precio_por_defecto_es_calculado(self, client):
        data = client.get("/api/analysis/cafe_verde").json()
        assert data["data_quality"]["price_source"] == "calculado de históricos"
        assert data["unit_economics"]["fob_price_usd_per_kg"] > 0

    def test_precio_invalido_da_422(self, client):
        assert client.get("/api/analysis/cafe_verde?price_usd_per_kg=0").status_code == 422
        assert client.get("/api/analysis/cafe_verde?price_usd_per_kg=-1").status_code == 422

    def test_la_fuente_declarada_es_offline(self, client):
        data = client.get("/api/analysis/cafe_verde").json()
        assert data["data_quality"]["market_data_source"] == "Trade Map (Excel local)"


class TestComparison:
    def test_comparacion_es_json_valido(self, client):
        response = client.get("/api/comparison?slugs=cafe_verde,uva_fresca")
        assert response.status_code == 200
        data = response.json()
        _assert_json_valid(data)
        assert data["available_count"] >= 2

    def test_comparacion_sin_slugs_usa_todos(self, client):
        data = client.get("/api/comparison").json()
        assert data["available_count"] >= 1


class TestHtml:
    def test_raiz_renderiza(self, client):
        """Sirve el build de Vite si existe; si no, el HTML de Jinja."""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_build_de_vite_devuelve_el_shell(self, client):
        """Con dist/ presente, / devuelve el shell y los datos los pide el JS.

        El shell no lleva el nombre del producto: el estado vive en la URL y
        `frontend/js/main.js` lo lee para llamar a /api/analysis/...
        """
        if not (DIST_DIR / "index.html").exists():
            pytest.skip("sin build de Vite; corre `npm run build`")
        response = client.get("/?slug=cafe_verde")
        assert response.status_code == 200
        assert 'id="app"' in response.text
        assert "assets/index" in response.text

    def test_ssr_fallback_renderiza_el_producto(self, client, monkeypatch):
        """Con FORCE_SSR=1 el HTML llega completo desde el servidor."""
        monkeypatch.setenv("FORCE_SSR", "1")
        response = client.get("/?slug=cafe_verde")
        assert response.status_code == 200
        assert "Cafe" in response.text

    def test_ssr_fallback_toma_el_primer_producto(self, client, monkeypatch):
        monkeypatch.setenv("FORCE_SSR", "1")
        response = client.get("/")
        assert response.status_code == 200
        assert "Cafe" in response.text

    def test_ssr_fallback_avisa_si_el_producto_no_existe(self, client, monkeypatch):
        """Un slug malo no debe ser un 500: es un mensaje en la pagina."""
        monkeypatch.setenv("FORCE_SSR", "1")
        response = client.get("/?slug=no_existe")
        assert response.status_code == 200

    def test_sirve_alguna_hoja_de_estilos(self, client):
        """Con build hay /assets/index.css; sin build, /static/app.css."""
        built = client.get("/assets/index.css")
        legacy = client.get("/static/app.css")
        assert built.status_code == 200 or legacy.status_code == 200
