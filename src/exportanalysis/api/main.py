"""API HTTP: expone el analisis como JSON y sirve el frontend compilado.

Se eligio FastAPI sobre Streamlit por el requisito de publicar: esto es una app
ASGI normal, corre en Docker, Render, Railway, Fly.io o un VPS sin adaptaciones.
El frontend es una SPA (Vite): `npm run build` genera `dist/` y FastAPI lo sirve
desde el mismo origen, asi que en produccion no hay CORS. Sin build no hay UI,
solo API.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from ..config import load_catalog
from ..pipeline import comparison, screener
from ..pipeline.analyze import analyze_product
from .dossier import generate_excel_dossier

SRC_DIR = Path(__file__).resolve().parent.parent.parent.parent
DIST_DIR = SRC_DIR / "dist"

app = FastAPI(
    title="Export Investment Analyzer",
    description="Datos publicos de comercio (Trade Map, SUNAT) + modelo de inversion.",
    version="0.1.0",
)

# El build de Vite emite dist/assets/. Si no existe (aun no corriste
# `npm run build`), la API igual arranca: solo la raiz devuelve 503.
ASSETS_DIR = DIST_DIR / "assets"
if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def _json_safe(value):
    """Convierte NaN e Infinity a None para que el JSON sea valido.

    NaN aparece de forma natural en un analisis de comercio: el crecimiento
    interanual del primer anio no tiene ano previo contra el cual calcularlo,
    y dividir por cero produce NaN en lugar de un error. El JSON no admite NaN
    (no es null, no es un numero: es un valor invalido) y `JSONResponse` lanza
    excepcion al encontrarlo. La decision correcta es devolver null, que el
    frontend sabe dibujar como "n/d", y no inventar un cero.
    """
    import math

    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


@app.get("/api/products")
def list_products() -> dict:
    """Catalogo de productos configurados."""
    catalog = load_catalog()
    return {
        "reporter": catalog.defaults.reporter,
        "products": [
            {
                "slug": p.slug,
                "name": p.name,
                "hs6": p.hs6,
                "nandina": p.nandina,
                "industry": p.industry,
                "presentations": [pres.model_dump() for pres in p.presentations],
            }
            for p in catalog.products
        ],
    }


class AnalysisAssumptions:
    """Supuestos opcionales del modelo de inversion.

    FastAPI los declara una sola vez como dependencia y los inyecta en cada
    endpoint, de modo que los parametros de query (y su validacion) no se
    copien en /api/analysis y /api/analysis/{slug}/export/excel.
    """

    def __init__(
        self,
        target_share: float | None = Query(default=None, ge=0.0, le=1.0),
        price_usd_per_kg: float | None = Query(default=None, gt=0.0),
        capacity_kg_year: float | None = Query(default=None, gt=0.0),
        year1_volume_kg: float | None = Query(default=None, gt=0.0),
        annual_volume_growth_pct: float | None = Query(default=None, ge=-100.0, le=1000.0),
        purchase_cost_usd_per_kg: float | None = Query(default=None, ge=0.0),
        variable_cost_usd_per_kg: float | None = Query(default=None, ge=0.0),
        capex_usd: float | None = Query(default=None, ge=0.0),
        opex_fixed_usd_year: float | None = Query(default=None, ge=0.0),
        working_capital_usd: float | None = Query(default=None, ge=0.0),
        discount_rate: float | None = Query(default=None, ge=0.0, le=1.0),
        price_volatility_pct: float | None = Query(default=15.0, ge=0.0, le=100.0),
        purchase_cost_volatility_pct: float | None = Query(default=15.0, ge=0.0, le=100.0),
        volume_volatility_pct: float | None = Query(default=20.0, ge=0.0, le=100.0),
        projection_method: str = Query(
            default="moving_average",
            pattern="^(moving_average|linear|quadratic|cagr)$",
        ),
    ) -> None:
        self.target_share = target_share
        self.price_usd_per_kg = price_usd_per_kg
        self.capacity_kg_year = capacity_kg_year
        self.year1_volume_kg = year1_volume_kg
        self.annual_volume_growth_pct = annual_volume_growth_pct
        self.purchase_cost_usd_per_kg = purchase_cost_usd_per_kg
        self.variable_cost_usd_per_kg = variable_cost_usd_per_kg
        self.capex_usd = capex_usd
        self.opex_fixed_usd_year = opex_fixed_usd_year
        self.working_capital_usd = working_capital_usd
        self.discount_rate = discount_rate
        self.price_volatility_pct = price_volatility_pct
        self.purchase_cost_volatility_pct = purchase_cost_volatility_pct
        self.volume_volatility_pct = volume_volatility_pct
        self.projection_method = projection_method

    def as_kwargs(self) -> dict:
        """Devuelve los supuestos en el formato que espera `analyze_product`."""
        return {
            "target_share": self.target_share,
            "price_usd_per_kg": self.price_usd_per_kg,
            "capacity_kg_year": self.capacity_kg_year,
            "year1_volume_kg": self.year1_volume_kg,
            "annual_volume_growth_pct": self.annual_volume_growth_pct,
            "purchase_cost_usd_per_kg": self.purchase_cost_usd_per_kg,
            "variable_cost_usd_per_kg": self.variable_cost_usd_per_kg,
            "capex_usd": self.capex_usd,
            "opex_fixed_usd_year": self.opex_fixed_usd_year,
            "working_capital_usd": self.working_capital_usd,
            "discount_rate": self.discount_rate,
            "price_volatility_pct": self.price_volatility_pct,
            "purchase_cost_volatility_pct": self.purchase_cost_volatility_pct,
            "volume_volatility_pct": self.volume_volatility_pct,
            "projection_method": self.projection_method,
        }


# Anotacion reutilizable para inyectar los supuestos en cada endpoint.
AnalysisAssumptionsDep = Annotated[AnalysisAssumptions, Depends()]


@app.get("/api/analysis/{slug}")
def analysis(
    slug: str,
    assumptions: AnalysisAssumptionsDep,
) -> JSONResponse:
    """Análisis de mercado y evaluación financiera con supuestos ingresados."""
    try:
        result = analyze_product(slug, **assumptions.as_kwargs())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        # Config incompleta: es un error del operador, no del cliente.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return JSONResponse(content=_json_safe(result))


@app.get("/api/analysis/{slug}/export/excel")
def export_excel(
    slug: str,
    assumptions: AnalysisAssumptionsDep,
) -> Response:
    """Descarga el Dossier Ejecutivo completo en formato Excel (.xlsx)."""
    try:
        result = analyze_product(slug, **assumptions.as_kwargs())
        stream = generate_excel_dossier(result)
        filename = f"dossier_exportacion_{slug}.xlsx"
        return Response(
            content=stream.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/")
def index() -> Response:
    """Sirve el frontend compilado (dist/index.html).

    El frontend es una SPA: pide los datos a /api/analysis/... y el navegador ve
    un solo origen, sin CORS. Requiere `npm run build` (ver README). Sin build la
    API sigue viva; solo la raiz avisa que falta el frontend.
    """
    index_html = DIST_DIR / "index.html"
    if not index_html.exists():
        raise HTTPException(
            status_code=503,
            detail="Falta el build del frontend. Corre `npm run build`.",
        )
    return FileResponse(index_html)


@app.get("/api/comparison")
def compare_products(slugs: str = Query(default="", description="slugs separados por coma")) -> JSONResponse:
    try:
        items = [x.strip() for x in slugs.split(",") if x.strip()]
        if not items:
            items = comparison.all_product_slugs()
        res = comparison.compare_products(items)
        return JSONResponse(content=_json_safe(res))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/ranking")
def ranking(slugs: str = Query(default="", description="slugs separados por coma; vacio = catalogo completo")) -> JSONResponse:
    """Screener: ranking de productos por puntaje ponderado (config/scoring.yaml)."""
    try:
        items = [x.strip() for x in slugs.split(",") if x.strip()] or None
        return JSONResponse(content=_json_safe(screener.screen_products(items)))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
