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

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..config import load_catalog
from ..pipeline.analyze import analyze_product

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
                "presentations": [pres.model_dump() for pres in p.presentations],
            }
            for p in catalog.products
        ],
    }


@app.get("/api/analysis/{slug}")
def analysis(slug: str, target_share: float | None = Query(default=None, ge=0.0, le=1.0)) -> JSONResponse:
    """Analisis completo de un producto.

    target_share: participacion de mercado objetivo. Opcional; si se omite se
    deriva como "share actual + 2 pp".
    """
    try:
        result = analyze_product(slug, target_share=target_share)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        # Config incompleta: es un error del operador, no del cliente.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return JSONResponse(content=_json_safe(result))


@app.get("/", response_class=HTMLResponse)
def index(request: Request, slug: str | None = None, target_share: float | None = None):
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
            analysis_result = analyze_product(selected_slug, target_share=target_share)
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
            "target_share": target_share,
        },
    )
@app.get("/simple", response_class=HTMLResponse)
def simple(request: Request, hs6: str = "081040"):
    from ..pipeline import excel_analysis
    ts = excel_analysis.peru_exports_ts(hs6)
    y2024 = ts[ts['year'] == 2024].copy()
    total = y2024['fob_usd'].sum()
    y2024['share'] = y2024['fob_usd'] / total if total else 0
    y2024 = y2024.sort_values('fob_usd', ascending=False).head(15)
    labels = y2024['partnerLabel'].tolist()
    values = y2024['fob_usd'].tolist()
    return templates.TemplateResponse(
        request,
        "simple.html",
        {
            "hs6": hs6,
            "top": y2024.to_dict('records'),
            "labels": labels,
            "values": values,
        },
    )
@app.get("/explorar", response_class=HTMLResponse)
def explorar(request: Request, hs6: str = "081040"):
    from ..pipeline import excel_analysis
    ts = excel_analysis.peru_exports_ts(hs6)
    y2024 = ts[ts['year'] == 2024].copy()
    total = y2024['fob_usd'].sum()
    y2024['share'] = y2024['fob_usd'] / total if total else 0
    y2024 = y2024.sort_values('fob_usd', ascending=False).head(20)
    labels = y2024['partnerLabel'].tolist()
    values = y2024['fob_usd'].tolist()
    # trend total
    trend = ts.groupby('year')['fob_usd'].sum().sort_index()
    trend_labels = [str(x) for x in trend.index.tolist()]
    trend_vals = trend.tolist()
    return templates.TemplateResponse(
        request,
        "simple.html",
        {
            "hs6": hs6,
            "top": y2024.to_dict('records'),
            "labels": labels,
            "values": values,
            "trend_labels": trend_labels,
            "trend_vals": trend_vals,
        },
    )
