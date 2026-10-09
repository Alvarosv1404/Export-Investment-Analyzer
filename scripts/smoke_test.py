"""Prueba end-to-end del pipeline con datos reales. Ejecutar:

    python scripts/smoke_test.py
"""

from __future__ import annotations

import logging
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from exportanalysis.config import load_catalog  # noqa: E402
from exportanalysis.pipeline.analyze import analyze_product  # noqa: E402


def money(value: float) -> str:
    return f"{value:,.0f}"


def run(slug: str = "cafe_verde") -> None:
    result = analyze_product(slug)
    product = result["product"]
    market = result["market"]

    print("=" * 78)
    print(f"{product['name']}  |  HS6 {product['hs6']}  |  NANDINA {product.get('nandina')}")
    print("=" * 78)

    if not market.get("available"):
        print(f"  SIN DATA: {market.get('message')}")
        return

    print("\n[1] MERCADO  (fuente: UN Comtrade, dato publicado)")
    print(f"  Ultimo anio con data : {market['latest_year']}")
    print(f"  Exportaciones FOB   : USD {money(market['latest_fob_usd'])}")
    print(f"  Volumen             : {money(market['latest_volume_kg'])} kg")
    print(f"  Precio unitario     : USD {market['latest_unit_value_usd']:.3f}/kg")
    print(f"  CAGR valor 5 anos   : {market['cagr_value'] * 100:.1f}%")
    print(f"  CAGR volumen        : {market['cagr_volume'] * 100:.1f}%")
    print(f"  CAGR precio         : {market['cagr_unit_value'] * 100:+.1f}%")
    print(f"  Concentracion top 5 : {market['top5_concentration'] * 100:.1f}% de las exportaciones")
    print("  Principales destinos :")
    for row in market["top_destinations"][:5]:
        print(f"     {row['partner_name']:<18} USD {money(row['fob_usd']):>14}")

    comp = result["competitors"]
    print("\n[2] COMPETENCIA  (fuente: UN Comtrade, dato publicado)")
    if comp.get("available"):
        share = comp["origin_share"]
        print(
            f"  Peru en {comp['origin_rank']} de {comp['origin_countries']} exportadores "
            f"con data en {comp['latest_year']}"
        )
        print(
            f"  Participacion de mercado: {share * 100:.1f}%" if share is not None
            else "  Participacion de mercado: n/d"
        )
        print(f"  Tendencia del share    : {comp['share_trend']}")
        if comp.get("coverage_warning"):
            print(f"  AVISO DE COBERTURA     : {comp['coverage_warning']}")
        for row in comp["rankings"][:5]:
            marker = " <-- Peru" if row["is_origin_country"] else ""
            print(
                f"     #{row['rank']} {row['country']:<22} USD {money(row['value_usd']):>14}"
                f"  {row['share'] * 100:5.1f}%{marker}"
            )
    else:
        print(f"  {comp.get('message')}")

    headroom = result["headroom"]
    print("\n[3] ESPACIO DISPONIBLE")
    if headroom.get("available"):
        print(f"  TAM (ano {headroom['latest_year']})       : USD {money(headroom['market_value_usd'])}")
        print(f"  Share actual de Peru   : {headroom['current_share'] * 100:.1f}%")
        if headroom.get("coverage_warning"):
            print(f"  AVISO DE COBERTURA     : {headroom['coverage_warning']}")
        print("  Escalera de headroom:")
        for row in headroom["ladder"]:
            kg = f"{row['headroom_kg']:>14,.0f} kg" if row.get("headroom_kg") else ""
            flag = " " if row["requires_above_current"] else "  (ya superado)"
            print(
                f"     objetivo {row['target_share'] * 100:5.1f}%  ->  "
                f"USD {money(row['headroom_usd']):>14}{kg}{flag}"
            )
        print(f"  {headroom['note']}")

    implied = result["implied_volume"]
    print("\n[4] VOLUMEN QUE EL MERCADO SOSTIENE")
    if implied.get("available"):
        print(f"  Facturacion implicita  : USD {money(implied['implied_revenue_usd'])}")
        print(f"  Volumen implicito      : {implied['implied_volume_kg']:,.0f} kg/ano")
        print(f"  Capacidad instalada    : {implied['installed_capacity_kg']:,.0f} kg/ano")
        print(f"  Cuello de botella      : {implied['binds']}")
        print(f"  {implied['message']}")
    else:
        print(f"  {implied.get('message')}")

    unit = result["unit_economics"]
    print("\n[5] ECONOMIA UNITARIA  (data de mercado vs tus costos)")
    print(f"  Precio FOB de mercado  : USD {unit['fob_price_usd_per_kg']:.3f}/kg   <- dato Comtrade")
    print(f"  Costo de compra        : USD {unit['purchase_cost_usd_per_kg']:.3f}/kg   <- supuesto tuyo")
    print(f"  Costo de procesamiento : USD {unit['processing_cost_usd_per_kg']:.3f}/kg   <- supuesto tuyo")
    print(f"  Comision + cumplimiento: USD {unit['commission_usd_per_kg'] + unit['compliance_usd_per_kg']:.3f}/kg   <- supuesto tuyo")
    print(f"  Costo variable total   : USD {unit['total_variable_cost_usd_per_kg']:.3f}/kg")
    print(f"  MARGEN BRUTO           : USD {unit['gross_margin_usd_per_kg']:.3f}/kg ({unit['gross_margin_pct'] * 100:.1f}%)")
    print(f"  Precio de equilibrio   : USD {unit['breakeven_fob_price_usd_per_kg']:.3f}/kg")
    for warning in unit["warnings"]:
        print(f"  *** {warning}")

    landed = result["landed_cost"]
    print("\n[6] COSTO PUESTO EN DESTINO  (arancel = supuesto cargado a mano)")
    if landed:
        print(f"  FOB                   : USD {landed['fob_usd_per_kg']:.3f}/kg")
        print(f"  Flete + seguro        : USD {landed['freight_usd_per_kg'] + landed['insurance_usd_per_kg']:.3f}/kg")
        print(f"  CIF                   : USD {landed['cif_usd_per_kg']:.3f}/kg")
        print(f"  Arancel aplicado      : {(landed['duty_pct'] or 0) * 100:.1f}%  ->  USD {landed['duty_usd_per_kg']:.3f}/kg")
        print(f"  Landed cost           : USD {landed['landed_usd_per_kg']:.3f}/kg")
        print(f"  Peso del arancel      : {landed['duty_share_of_landed'] * 100:.1f}% de la factura del importador")

    investment = result["investment"]
    summary = investment["summary"]
    print("\n[7] INVERSION  (todos estos numeros son SUPUESTOS, no data)")
    print(f"  Curva de ocupacion    : {investment['inputs']['utilization_ramp']}")
    print(f"  Origen de la curva    : {investment['ramp_source']['source']}")
    print(f"                         {investment['ramp_source']['reason']}")
    print(f"  VAN                   : USD {money(summary['npv_usd'])}")
    print(f"  TIR                   : {summary['irr_pct'] if summary['irr_pct'] is not None else 'no existe'}")
    print(f"  Payback               : {summary['payback_years'] if summary['payback_years'] is not None else 'no se recupera'}")
    print(f"  Veredicto             : {summary['verdict']['label']}")
    print(f"                         {summary['verdict']['detail']}")

    be = investment["breakeven"]
    if be.get("available"):
        print(f"  Precio FOB minimo     : USD {be['fob_price_floor_usd_per_kg']:.3f}/kg (para VAN = 0)")
        print(f"  Ocupacion minima      : {be['utilization_floor_pct']:.1f}% (para VAN = 0)")

    sensitivity = investment["sensitivity"]
    print("\n[8] SENSIBILIDAD (tornado: que variable manda mas)")
    print(f"  VAN base              : USD {money(sensitivity['base_npv_usd'])}")
    for row in sensitivity["tornado"]:
        print(f"     {row['variable']:<18} swing USD {money(row['swing_usd']):>14}")

    quality = result["data_quality"]
    print("\n[9] PROCEDENCIA DE LOS DATOS")
    print(f"  Mercado  : {quality['market_data_source']}")
    print(f"  Anios    : {quality['years_with_data']}")
    print(f"  Arancel  : {quality['tariff_source']}")
    print(f"  Supuestos: {quality['assumptions_source']}")
    print(f"  OJO      : {quality['warning']}")
    print()


if __name__ == "__main__":
    slugs = sys.argv[1:] or [load_catalog().products[0].slug]
    for slug in slugs:
        run(slug)
