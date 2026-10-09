"""Carga de configuracion declarativa desde config/*.yaml.

Regla de diseno: agregar un producto o cambiar un supuesto NO debe requerir
tocar codigo. Todo entra por aqui.
"""

from __future__ import annotations

import functools
import os
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

    def for_product(self, slug: str) -> dict[str, Any]:
        """Supuestos efectivos de un producto: defaults + override del producto.

        Falla explicito si al producto le falta un supuesto numerico clave,
        en vez de propagar None y romper mas abajo con un error confuso.
        """
        base = self.defaults.model_dump()
        override = self.products.get(slug)
        if override:
            base.update({k: v for k, v in override.model_dump().items() if v is not None})

        missing = [
            k
            for k in (
                "capacity_kg_year",
                "capex_usd",
                "variable_cost_usd_per_kg",
                "purchase_cost_usd_per_kg",
                "opex_fixed_usd_year",
                "working_capital_usd",
            )
            if base.get(k) is None
        ]
        if missing:
            raise ValueError(
                f"Faltan supuestos para '{slug}': {', '.join(missing)}. "
                f"Agregalos en config/assumptions.yaml bajo products.{slug}."
            )
        return base


def _read_yaml(name: str) -> dict[str, Any]:
    path = CONFIG_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"No se encontro {path}")
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


@functools.lru_cache(maxsize=1)
def load_catalog() -> Catalog:
    return Catalog(**_read_yaml("products.yaml"))


@functools.lru_cache(maxsize=1)
def load_assumptions() -> Assumptions:
    return Assumptions(**_read_yaml("assumptions.yaml"))


@functools.lru_cache(maxsize=1)
def load_countries() -> dict[str, Country]:
    raw = _read_yaml("countries.yaml")
    return {name: Country(**data) for name, data in raw.items()}


def get_product(slug: str) -> Product:
    for product in load_catalog().products:
        if product.slug == slug:
            return product
    available = ", ".join(p.slug for p in load_catalog().products)
    raise KeyError(f"Producto '{slug}' no esta en products.yaml. Disponibles: {available}")


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
