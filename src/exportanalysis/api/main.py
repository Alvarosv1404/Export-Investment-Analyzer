"""API HTTP: expone el analisis como JSON y como HTML.

Se eligio FastAPI sobre Streamlit por el requisito de publicar: esto es una app
ASGI normal, corre en Docker, Render, Railway, Fly.io o un VPS sin adaptaciones.
El frontend es Jinja2 + Chart.js servido desde el mismo proceso, asi que no hay
build step ni node_modules que mantener.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..config import load_catalog
from ..pipeline import comparison, screener
from ..pipeline.analyze import analyze_product
from .dossier import generate_excel_dossier

log = logging.getLogger(__name__)

SRC_DIR = Path(__file__).resolve().parent.parent.parent.parent
DIST_DIR = SRC_DIR / "dist"
# Fallback para cuando se corre sin `npm run build`: sirve los templates de
# Jinja del repo. El build de Vite tiene prioridad cuando existe.
LEGACY_TEMPLATES = Path(__file__).resolve().parent.parent / "web" / "templates"
LEGACY_STATIC = Path(__file__).resolve().parent.parent / "web" / "static"

app = FastAPI(
    title="Export Investment Analyzer",
    description="Datos publicos de comercio (Trade Map, SUNAT) + modelo de inversion.",
    version="0.1.0",
)

if DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")
else:
    app.mount("/static", StaticFiles(directory=LEGACY_STATIC), name="static")

templates = Jinja2Templates(directory=LEGACY_TEMPLATES)


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
    copien en /api/analysis, /api/analysis/{slug}/export/excel y /.
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


@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    assumptions: AnalysisAssumptionsDep,
    slug: str | None = None,
):
    """Sirve el frontend.

    Hay dos modos, y se eligen solos:

    - Si existe dist/ (o sea, corriste `npm run build`), se sirve el build de
      Vite. El JS pide los datos a /api/analysis/... y el navegador ve un solo
      origen, sin CORS.
    - Si no existe, se cae al HTML de Jinja, que renderiza todo en el servidor.
      Sirve para que la API sea util sola, sin Node instalado.

    El render del lado del servidor se mantiene ademas porque la pagina tiene
    que poder imprimirse aunque el JS este deshabilitado. FORCE_SSR=1 lo fuerza.
    """
    index_html = DIST_DIR / "index.html"
    if index_html.exists() and not os.getenv("FORCE_SSR"):
        return FileResponse(index_html)

    catalog = load_catalog()
    products = catalog.products
    selected_slug = slug or (products[0].slug if products else None)

    analysis_result = None
    error = None
    if selected_slug:
        try:
            analysis_result = analyze_product(selected_slug, **assumptions.as_kwargs())
        except (KeyError, ValueError) as exc:
            error = str(exc)
            log.warning("No se pudo analizar %s: %s", selected_slug, exc)

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "products": products,
            "selected": selected_slug,
            # tojson() tampoco acepta NaN, asi que el HTML usa el mismo filtro.
            "result": _json_safe(analysis_result) if analysis_result else None,
            "error": error,
            "target_share": assumptions.target_share,
            "price_usd_per_kg": assumptions.price_usd_per_kg,
        },
    )


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


@app.get("/simple", response_class=HTMLResponse, include_in_schema=False)
@app.get("/explorar", response_class=HTMLResponse)
def explore(request: Request, hs6: str = "081040", year: int | None = None):
    """Destinos y serie anual de exportaciones para un HS6, desde los Excel.

    `/simple` se conserva como alias historico de `/explorar`.
    """
    import pandas as pd

    from ..pipeline import excel_analysis

    ts = excel_analysis.peru_exports_ts(hs6)
    if ts.empty:
        return templates.TemplateResponse(
            request,
            "simple.html",
            {
                "hs6": hs6,
                "year": year,
                "top": [],
                "labels": [],
                "values": [],
                "trend_labels": [],
                "trend_vals": [],
                "error": "Sin datos de comercio para este HS6.",
            },
        )

    # Año pedido (2024 por defecto); si no existe, se usa el mas reciente.
    requested = year if year is not None else 2024
    if requested not in set(ts["year"]):
        requested = int(ts["year"].max())

    snapshot = ts[ts["year"] == requested].copy()
    total = snapshot["fob_usd"].sum() if not snapshot.empty else 0
    if not snapshot.empty:
        snapshot = snapshot.assign(share=snapshot["fob_usd"] / total if total else 0.0)
        snapshot = snapshot.sort_values("fob_usd", ascending=False).head(20)
    snapshot_safe = snapshot.where(pd.notna(snapshot), None)

    trend = ts.groupby("year", dropna=True)["fob_usd"].sum().sort_index()
    trend_safe = trend.where(pd.notna(trend), None)

    return templates.TemplateResponse(
        request,
        "simple.html",
        {
            "hs6": hs6,
            "year": requested,
            "top": snapshot_safe.to_dict("records"),
            "labels": [v for v in snapshot_safe["partnerLabel"].tolist()],
            "values": [v for v in snapshot_safe["fob_usd"].tolist()],
            "trend_labels": [str(x) for x in trend_safe.index.tolist()],
            "trend_vals": [v for v in trend_safe.tolist()],
        },
    )
