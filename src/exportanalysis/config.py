"""Carga de configuracion declarativa desde config/*.yaml.

Regla de diseno: agregar un producto o cambiar un supuesto NO debe requerir
tocar codigo. Todo entra por aqui.
"""

from __future__ import annotations

import functools
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator


def project_root() -> Path:
    """Raiz del proyecto: sube desde este archivo hasta encontrar config/."""
    env = os.getenv("PROJECT_ROOT")
    if env:
        return Path(env).resolve()
    # src/exportanalysis/config.py -> subir 3 niveles
    return Path(__file__).resolve().parents[2]


CONFIG_DIR = project_root() / "config"
DATA_DIR = project_root() / "data"

# Supuestos numericos sin los cuales el modelo de inversion no puede correr.
REQUIRED_ASSUMPTIONS = (
    "capacity_kg_year",
    "capex_usd",
    "variable_cost_usd_per_kg",
    "purchase_cost_usd_per_kg",
    "opex_fixed_usd_year",
    "working_capital_usd",
)

# Carpetas de data que NO son productos (agregados, cache y crudos).
RESERVED_DATA_DIRS = {"raw", "interim", "processed"}

# Sectores sugeridos para `Product.industry`. NO es una lista cerrada: agregar
# uno nuevo es tan simple como escribir el sector que corresponda en
# products.yaml. Vive aqui, y no en el yaml, para que el siguiente programador
# vea de un vistazo que taxonomia se usa y pueda extenderla o agrupar/filtrar
# por industria sin adivinar los valores existentes.
INDUSTRIES = (
    "Agricola",  # productos del agro sin transformar: frescos, secos, en grano
    "Agroindustria",  # derivados del agro: aceites, conservas, extractos
    "Pesquero",  # pesca y acuicultura
    "Minero",  # minerales en bruto y concentrados
    "Metales",  # metales refinados y manufacturas
    "Textil",  # fibras, hilados y confecciones
    "Quimico",  # quimicos, farmacos, colorantes
    "Hidrocarburos",  # petroleo, gas y derivados
    "Servicios",  # exportaciones de servicios
)

# Mapa para normalizar el nombre de una carpeta de industria a su forma canonica
# ("agricola" -> "Agricola"). Las industrias fuera de la lista se respetan tal cual.
_INDUSTRY_BY_FOLD = {name.lower(): name for name in INDUSTRIES}


class Presentation(BaseModel):
    """Una presentacion comercial del mismo producto (grano, fresco, congelado...).

    Un producto se exporta en varias partidas: el cacao como grano (180100),
    pasta (180310) o manteca (180400). Modelarlas como lista permite comparar
    las presentaciones del mismo fruto sin crear productos separados.
    """

    hs6: str = Field(pattern=r"^\d{6}$")
    label: str = ""
    nandina: str | None = Field(default=None, pattern=r"^\d{10}$")


class Product(BaseModel):
    """Un producto a analizar. Se agrega editando config/products.yaml."""

    slug: str
    name: str
    hs6: str = Field(pattern=r"^\d{6}$")
    nandina: str | None = Field(default=None, pattern=r"^\d{10}$")
    unit: str = "kg"
    # Sector del producto (ver INDUSTRIES). Opcional: un producto descubierto en
    # data/ no lo trae hasta que se cura en products.yaml. Sirve para agrupar y
    # ensenar de que sector es cada producto, no para validar.
    industry: str | None = None
    # Escape hatch opcional. Por defecto va vacio y los competidores se derivan de
    # la data (los mayores exportadores del Excel). Solo se llena si se quiere
    # imponer un conjunto propio de paises (codigos M49).
    competitors: list[int] = Field(default_factory=list)
    # Presentaciones opcionales. Si se omite, el producto tiene una sola (su hs6).
    presentations: list[Presentation] = Field(default_factory=list)

    @model_validator(mode="after")
    def _sync_presentations(self) -> Product:
        """Mantiene `hs6` y `presentations` consistentes.

        `hs6` sigue siendo la presentacion principal (el pipeline lo usa tal
        cual). La lista debe empezar por ella para que no haya dos verdades.
        """
        if not self.presentations:
            object.__setattr__(
                self,
                "presentations",
                [Presentation(hs6=self.hs6, label=self.name, nandina=self.nandina)],
            )
        elif self.presentations[0].hs6 != self.hs6:
            raise ValueError(
                f"En '{self.slug}', hs6={self.hs6} debe coincidir con "
                f"presentations[0].hs6={self.presentations[0].hs6}."
            )
        return self


class ProductDefaults(BaseModel):
    years: int = 5
    reporter: int = 604
    flow: str = "X"


class Catalog(BaseModel):
    defaults: ProductDefaults = Field(default_factory=ProductDefaults)
    products: list[Product]


class Country(BaseModel):
    code: int
    iso3: str
    name: str


class InvestmentAssumptions(BaseModel):
    """Supuestos del modelo. Campos con `None` = se toma del override del producto."""

    capacity_kg_year: float | None = None
    capex_usd: float | None = None
    variable_cost_usd_per_kg: float | None = None
    purchase_cost_usd_per_kg: float | None = None
    opex_fixed_usd_year: float | None = None
    working_capital_usd: float | None = None
    # Los supuestos del catalogo arrancan como ejemplos (False). Marcarlos True
    # solo cuando los reemplazaste por cotizaciones reales: el screener usa esa
    # bandera para no presentar un ranking de ejemplo como una recomendacion.
    verified: bool = False


class ModelDefaults(BaseModel):
    project_years: int = 5
    discount_rate: float = 0.12
    tax_rate: float = 0.30
    learning_rate: float = 0.03
    sales_commission: float = 0.05
    freight_pct_fob: float = 0.05
    compliance_pct_fob: float = 0.02
    wc_inventory_days: int = 60
    wc_receivable_days: int = 45
    wc_payable_days: int = 30
    depreciation_years: int = 10
    capex_schedule: list[float] = Field(default_factory=lambda: [1.0])
    utilization_ramp: list[float] = Field(default_factory=lambda: [0.30, 0.55, 0.75, 0.90, 0.95])


class Assumptions(BaseModel):
    defaults: ModelDefaults
    products: dict[str, InvestmentAssumptions] = Field(default_factory=dict)
    sensitivity: dict[str, list[float]] = Field(default_factory=dict)
    fx: dict[str, float] = Field(default_factory=lambda: {"pen_per_usd": 3.75})

    def effective(self, slug: str) -> dict[str, Any]:
        """Supuestos efectivos: defaults + override del producto (sin validar)."""
        base = self.defaults.model_dump()
        override = self.products.get(slug)
        if override:
            base.update({k: v for k, v in override.model_dump().items() if v is not None})
        return base

    def missing_for(self, slug: str, overrides: dict[str, Any] | None = None) -> list[str]:
        """Supuestos numericos clave que le faltan a un producto (vacio = completo).

        Se expone para que el pipeline pueda degradar con un aviso en vez de
        reventar: un producto recien descubierto por su carpeta de data todavia
        no tiene supuestos, y eso no deberia impedir ver su analisis de mercado.
        """
        base = self.effective(slug)
        if overrides:
            base = {**base, **{k: v for k, v in overrides.items() if v is not None}}
        return [k for k in REQUIRED_ASSUMPTIONS if base.get(k) is None]

    def for_product(self, slug: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        """Supuestos efectivos de un producto: defaults + override del producto.

        Falla explicito si al producto le falta un supuesto numerico clave,
        en vez de propagar None y romper mas abajo con un error confuso.
        """
        base = self.effective(slug)
        if overrides:
            base = {**base, **{k: v for k, v in overrides.items() if v is not None}}
        missing = self.missing_for(slug, overrides)
        if missing:
            raise ValueError(
                f"Faltan supuestos para '{slug}': {', '.join(missing)}. "
                f"Agrégalos en config/assumptions.yaml bajo products.{slug}."
            )
        return base


class ScoringMetric(BaseModel):
    """Una dimension del ranking de productos, con su peso y su base."""

    label: str
    weight: float = 1.0
    lower_is_better: bool = False
    basis: str = "dato publicado"
    description: str = ""


class Scoring(BaseModel):
    """Configuracion del screener: que se mide y cuanto pesa cada cosa."""

    metrics: dict[str, ScoringMetric] = Field(default_factory=dict)


def _read_yaml(name: str) -> dict[str, Any]:
    path = CONFIG_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"No se encontró {path}")
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _slugify(text: str) -> str:
    """Nombre legible -> slug ASCII: 'Naranja fresca' -> 'naranja_fresca'."""
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", folded.strip().lower()).strip("_")
    return slug or "producto"


_HS6_RE = re.compile(r"(\d{6})")
_NANDINA_FILE_RE = re.compile(r"^(\d{10})\.xlsx$", re.IGNORECASE)


def _folder_hs6(folder: Path) -> str | None:
    """HS6 de una carpeta de data: primero el prefijo del nombre, luego los archivos."""
    match = _HS6_RE.match(folder.name.strip())
    if match:
        return match.group(1)
    counts: dict[str, int] = {}
    for file in folder.glob("*.xlsx"):
        for token in _HS6_RE.findall(file.stem):
            counts[token] = counts.get(token, 0) + 1
    if not counts:
        return None
    return max(counts, key=lambda key: counts[key])


def _folder_name(folder: Path, hs6: str) -> str:
    """Nombre del producto: el nombre de la carpeta sin el prefijo HS6."""
    name = re.sub(rf"^{hs6}[^0-9a-zA-Z]*", "", folder.name.strip()).strip(" -_")
    name = name or f"Producto {hs6}"
    return name[:1].upper() + name[1:] if name.islower() else name


def _folder_nandina(folder: Path, hs6: str) -> str | None:
    """Partida SUNAT (10 digitos) si hay un Excel con ese nombre en la carpeta."""
    candidates = [
        match.group(1)
        for file in folder.glob("*.xlsx")
        if (match := _NANDINA_FILE_RE.match(file.name))
    ]
    if not candidates:
        return None
    exact = [code for code in candidates if code.startswith(hs6)]
    return (exact or candidates)[0]


def _is_ignored(folder: Path) -> bool:
    """Carpetas que nunca son productos: reservadas (raw, interim, processed) u ocultas."""
    return folder.name.startswith((".", "_")) or folder.name in RESERVED_DATA_DIRS


def _canonical_industry(name: str) -> str:
    """Nombre de carpeta -> industria canonica de INDUSTRIES, o tal cual.

    Asi `data/agricola/` y `data/Agricola/` agrupan igual, y una carpeta de un
    rubro nuevo ('Bebidas') se respeta sin tocar codigo.
    """
    cleaned = name.strip()
    return _INDUSTRY_BY_FOLD.get(cleaned.lower(), cleaned)


def _product_from_folder(folder: Path, industry: str | None) -> Product | None:
    """Producto a partir de una carpeta de data; None si no parece serlo."""
    if not any(folder.glob("*.xlsx")):
        return None
    hs6 = _folder_hs6(folder)
    if not hs6:
        return None
    name = _folder_name(folder, hs6)
    return Product(
        slug=_slugify(name),
        name=name,
        hs6=hs6,
        nandina=_folder_nandina(folder, hs6),
        industry=industry,
    )


def _product_folders(root: Path):
    """Recorre data/ y emite (carpeta, industria) por cada producto.

    Estructura soportada:

      data/<hs6> <nombre>/               -> producto, sin industria declarada
      data/<industria>/<hs6> <nombre>/   -> producto de esa industria

    La regla es simple para quien solo deja data: una carpeta con Excel es un
    producto; una carpeta sin Excel es una carpeta de industria y se bajan sus
    subcarpetas. Las carpetas reservadas (raw, interim, processed) y las ocultas
    se ignoran en todos los niveles.
    """
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or _is_ignored(entry):
            continue
        if any(entry.glob("*.xlsx")):
            yield entry, None
            continue
        industry = _canonical_industry(entry.name)
        for sub in sorted(entry.iterdir()):
            if sub.is_dir() and not _is_ignored(sub):
                yield sub, industry


def _unique_slug(slug: str, seen: set[str]) -> str:
    """Slug unico dentro del catalogo: agrega sufijo _2, _3... si se repite."""
    if slug not in seen:
        seen.add(slug)
        return slug
    suffix = 2
    while f"{slug}_{suffix}" in seen:
        suffix += 1
    unique = f"{slug}_{suffix}"
    seen.add(unique)
    return unique


def _discover_products(base: Path | None = None) -> list[Product]:
    """Productos inferidos de las carpetas de data/.

    Cada carpeta con al menos un Excel es un producto: el HS6 sale del nombre o
    de los archivos, la partida SUNAT del Excel de 10 digitos y la industria del
    nombre de la carpeta que la contiene. Es lo que permite sumar un producto
    nuevo sin tocar products.yaml: basta con dejar su data en su carpeta.
    """
    root = base or DATA_DIR
    if not root.exists():
        return []

    products: list[Product] = []
    seen_slugs: set[str] = set()
    for folder, industry in _product_folders(root):
        product = _product_from_folder(folder, industry)
        if product is None:
            continue
        slug = _unique_slug(product.slug, seen_slugs)
        if slug != product.slug:
            product = product.model_copy(update={"slug": slug})
        products.append(product)
    return products


@functools.lru_cache(maxsize=1)
def load_catalog() -> Catalog:
    """Catalogo efectivo: products.yaml + productos descubiertos en data/.

    products.yaml sigue mandando: si un HS6 ya esta declarado ahi, se conserva
    su metadata curada (nombre, presentaciones, industry, nandina). Lo que
    aparece en data/ y no esta en el yaml se agrega solo, con lo minimo.
    """
    catalog = Catalog(**_read_yaml("products.yaml"))
    known_hs6 = {product.hs6 for product in catalog.products}
    known_slugs = {product.slug for product in catalog.products}

    for product in _discover_products():
        if product.hs6 in known_hs6 or product.slug in known_slugs:
            continue
        catalog.products.append(product)
        known_hs6.add(product.hs6)
        known_slugs.add(product.slug)
    return catalog


@functools.lru_cache(maxsize=1)
def load_assumptions() -> Assumptions:
    return Assumptions(**_read_yaml("assumptions.yaml"))


@functools.lru_cache(maxsize=1)
def load_countries() -> dict[str, Country]:
    raw = _read_yaml("countries.yaml")
    return {name: Country(**data) for name, data in raw.items()}


@functools.lru_cache(maxsize=1)
def load_scoring() -> Scoring:
    """Pesos del screener. Si falta config/scoring.yaml, corre sin ponderar."""
    path = CONFIG_DIR / "scoring.yaml"
    if not path.exists():
        return Scoring()
    return Scoring(**_read_yaml("scoring.yaml"))


def get_product(slug: str) -> Product:
    for product in load_catalog().products:
        if product.slug == slug:
            return product
    available = ", ".join(p.slug for p in load_catalog().products)
    raise KeyError(
        f"Producto '{slug}' no esta en el catalogo (products.yaml o data/). Disponibles: {available}"
    )


def country_name(code: int) -> str:
    """Nombre de un pais por su codigo M49, con fallback a countries.yaml."""
    for country in load_countries().values():
        if country.code == code:
            return country.name
    return f"codigo {code}"


def nandina_to_hs6(nandina: str) -> str:
    """Los primeros 6 digitos de una partida NANDINA de 10."""
    if len(nandina) != 10 or not nandina.isdigit():
        raise ValueError(f"Partida NANDINA invalida: {nandina!r}. Se esperan 10 digitos.")
    return nandina[:6]
