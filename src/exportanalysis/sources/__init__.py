"""Fuentes de datos. Cada modulo expone una interfaz y documenta su estado.

Solo fuentes locales o de red bajo demanda explicita:
- `trademap_excel`: Excel de Trade Map (datos de mercado, offline).
- `sunat`: scraper de SUNAT/Aduanet (hoy devuelve vacio; no se usa en el flujo).
- `manual_tariffs`: aranceles cargados a mano en CSV.

No hay cliente de UN Comtrade ni de WITS: el proyecto corre 100% offline con
los Excel locales.
"""

from . import manual_tariffs, sunat, trademap_excel

__all__ = ["manual_tariffs", "sunat", "trademap_excel"]
