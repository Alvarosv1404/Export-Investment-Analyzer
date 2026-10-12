"""Generador de Dossier Ejecutivo en formato Excel (.xlsx).

Construye un libro de cálculo profesional de múltiples hojas que sintetiza
la evidencia de mercado de Trade Map / SUNAT y el modelo de inversión.
"""

from __future__ import annotations

import io
from typing import Any

import pandas as pd


def generate_excel_dossier(analysis: dict[str, Any]) -> io.BytesIO:
    """Genera un archivo Excel en memoria con el reporte ejecutivo del producto."""
    output = io.BytesIO()

    product = analysis.get("product") or {}
    market = analysis.get("market") or {}
    investment = analysis.get("investment") or {}
    summary = investment.get("summary") or {}
    inputs = investment.get("inputs") or {}
    monte_carlo = investment.get("monte_carlo")
    import_demand = analysis.get("import_demand") or {}
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        # 1. Hoja: Resumen Ejecutivo
        summary_rows = [
            {"Métrica / Variable": "Producto", "Valor": product.get("name"), "Unidad / Detalle": f"HS-6: {product.get('hs6')}"},
            {"Métrica / Variable": "Sector / Industria", "Valor": product.get("industry") or "No especificado", "Unidad / Detalle": ""},
            {"Métrica / Variable": "Partida SUNAT", "Valor": product.get("nandina") or "N/D", "Unidad / Detalle": "10 dígitos"},
            {"Métrica / Variable": "Último Año Analizado", "Valor": market.get("latest_year"), "Unidad / Detalle": "Trade Map / SUNAT"},
            {"Métrica / Variable": "Exportaciones Totales Perú", "Valor": market.get("latest_fob_usd"), "Unidad / Detalle": "USD FOB"},
            {"Métrica / Variable": "Precio FOB Promedio", "Valor": (analysis.get("pricing") or {}).get("price_usd_per_kg"), "Unidad / Detalle": "USD / kg"},
            {"Métrica / Variable": "Índice HHI Destinos", "Valor": market.get("hhi"), "Unidad / Detalle": market.get("hhi_category") or ""},
            {"Métrica / Variable": "Concentración Top 5 Destinos", "Valor": f"{market['top5_concentration'] * 100:.1f}%" if market.get("top5_concentration") is not None else "N/D", "Unidad / Detalle": ""},
            {"Métrica / Variable": "---", "Valor": "---", "Unidad / Detalle": "---"},
        ]
        if summary:
            summary_rows.extend(
                [
                    {"Métrica / Variable": "Volumen del primer año", "Valor": inputs.get("year1_volume_kg"), "Unidad / Detalle": "kg"},
                    {"Métrica / Variable": "Crecimiento anual de volumen", "Valor": inputs.get("annual_volume_growth_pct"), "Unidad / Detalle": "%"},
                    {"Métrica / Variable": "Costo variable total (compra + proceso)", "Valor": inputs.get("variable_cost_usd_per_kg"), "Unidad / Detalle": "USD/kg"},
                    {"Métrica / Variable": "Costos fijos anuales", "Valor": inputs.get("opex_fixed_usd_year"), "Unidad / Detalle": "USD/año"},
                    {"Métrica / Variable": "Inversión inicial (CAPEX)", "Valor": inputs.get("capex_usd"), "Unidad / Detalle": "USD"},
                    {"Métrica / Variable": "Tasa de descuento", "Valor": f"{inputs['discount_rate'] * 100:.1f}%", "Unidad / Detalle": ""},
                    {"Métrica / Variable": "Valor actual neto (VAN)", "Valor": summary.get("npv_usd"), "Unidad / Detalle": "USD"},
                    {"Métrica / Variable": "Tasa interna de retorno (TIR)", "Valor": f"{summary.get('irr_pct')}%" if summary.get("irr_pct") is not None else "N/D", "Unidad / Detalle": ""},
                    {"Métrica / Variable": "Periodo de recupero (payback)", "Valor": summary.get("payback_years"), "Unidad / Detalle": "años"},
                    {"Métrica / Variable": "Veredicto financiero", "Valor": (summary.get("verdict") or {}).get("label"), "Unidad / Detalle": (summary.get("verdict") or {}).get("detail")},
                ]
            )
        else:
            missing = analysis.get("assumptions_missing") or []
            summary_rows.append(
                {"Métrica / Variable": "Evaluación financiera", "Valor": "Pendiente", "Unidad / Detalle": f"Completar: {', '.join(missing)}"}
            )
        if summary and monte_carlo:
            mc_assumptions = monte_carlo["assumptions"]
            summary_rows.extend(
                [
                    {"Métrica / Variable": "Volatilidad del precio FOB", "Valor": mc_assumptions["price_volatility_pct"], "Unidad / Detalle": "% ingresado por el usuario"},
                    {"Métrica / Variable": "Volatilidad del costo variable total", "Valor": mc_assumptions["variable_cost_volatility_pct"], "Unidad / Detalle": "% ingresado por el usuario"},
                    {"Métrica / Variable": "Volatilidad del volumen", "Valor": mc_assumptions["volume_volatility_pct"], "Unidad / Detalle": "% ingresado por el usuario"},
                    {"Métrica / Variable": "Simulaciones Monte Carlo", "Valor": monte_carlo["n_simulations"], "Unidad / Detalle": "variaciones independientes"},
                    {"Métrica / Variable": "Probabilidad simulada de VAN negativo", "Valor": monte_carlo["prob_loss_pct"], "Unidad / Detalle": "% (no es pronóstico)"},
                    {"Métrica / Variable": "VAN simulado P10", "Valor": monte_carlo["npv_p10_usd"], "Unidad / Detalle": "USD"},
                    {"Métrica / Variable": "VAN simulado P90", "Valor": monte_carlo["npv_p90_usd"], "Unidad / Detalle": "USD"},
                ]
            )
        elif summary and investment.get("monte_carlo_missing"):
            summary_rows.append(
                {
                    "Métrica / Variable": "Monte Carlo",
                    "Valor": "Pendiente",
                    "Unidad / Detalle": (
                        "Completar volatilidades: "
                        + ", ".join(investment["monte_carlo_missing"])
                    ),
                }
            )
        df_summary = pd.DataFrame(summary_rows)
        df_summary.to_excel(writer, sheet_name="Resumen Ejecutivo", index=False)

        # 2. Hoja: Estado de Resultados (P&L)
        pnl = investment.get("pnl") or []
        if pnl:
            df_pnl = pd.DataFrame(pnl)
            df_pnl.to_excel(writer, sheet_name="Estado de Resultados", index=False)

        # 4. Hoja: Destinos de Exportación
        destinations = analysis.get("destinations") or []
        if destinations:
            df_dest = pd.DataFrame(destinations)
            df_dest.to_excel(writer, sheet_name="Destinos y Mercados", index=False)

        # 5. Hoja: Competidores Mundiales
        comp = analysis.get("competitors") or {}
        comp_rankings = comp.get("rankings") or []
        if comp_rankings:
            df_comp = pd.DataFrame(comp_rankings)
            df_comp.to_excel(writer, sheet_name="Competencia Mundial", index=False)

        demand_destinations = import_demand.get("destinations") or []
        if demand_destinations:
            pd.DataFrame(demand_destinations).to_excel(
                writer,
                sheet_name="Demanda Importadora",
                index=False,
            )

    output.seek(0)
    return output
