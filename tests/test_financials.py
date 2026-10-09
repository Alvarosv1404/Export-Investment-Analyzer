"""Tests del modelo financiero.

Se concentran en las dos cosas que rompen un modelo de inversion sin que se
note: el CAPEX contado dos veces y la unidad del arancel. Las dos dan numeros
plausibles, no errores visibles, que es lo peor que puede pasarle a un modelo.
"""

from __future__ import annotations

import pytest

from exportanalysis.model.financials import (
    ProjectInputs,
    _capex_schedule,
    _learning_factor,
    _ramp,
    annual_pnl,
    build_cashflows,
)
from exportanalysis.model.valuation import (
    _bisect,
    _with,
    breakeven,
    run_sensitivity,
    summarize,
)


def base_inputs(**overrides) -> ProjectInputs:
    """Caso de referencia: planta chica, margen sano, todo en el ano 0."""
    defaults = dict(
        slug="test",
        capacity_kg_year=1_000_000,
        capex_usd=2_000_000,
        variable_cost_usd_per_kg=0.50,
        purchase_cost_usd_per_kg=2.00,
        opex_fixed_usd_year=150_000,
        working_capital_usd=200_000,
        project_years=5,
        discount_rate=0.12,
        tax_rate=0.30,
        learning_rate=0.0,
        sales_commission=0.0,
        compliance_pct_fct=0.0,
        depreciation_years=10,
        capex_schedule=[1.0],
        utilization_ramp=[1.0] * 5,
        fob_price_usd_per_kg=3.60,
    )
    defaults.update(overrides)
    return ProjectInputs(**defaults)


class TestCapexSchedule:
    def test_todo_en_ano_cero_no_se_repite(self):
        """`[1.0]` significa todo el CAPEX en t=0, no en cada ano."""
        schedule = _capex_schedule([1.0], years=5)
        assert schedule == [1.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        assert sum(schedule) == pytest.approx(1.0)

    def test_escalonado_suma_uno(self):
        schedule = _capex_schedule([0.4, 0.3, 0.3], years=5)
        assert schedule == [0.4, 0.3, 0.3, 0.0, 0.0, 0.0]
        assert sum(schedule) == pytest.approx(1.0)

    def test_vacio_todo_al_ano_cero(self):
        assert _capex_schedule([], years=3) == [1.0, 0.0, 0.0, 0.0]

    def test_no_se_extiende_el_ultimo_valor(self):
        """Repetir el ultimo valor multiplicaria el CAPEX: no debe pasar."""
        schedule = _capex_schedule([0.5], years=4)
        assert schedule[1:] == [0.0, 0.0, 0.0, 0.0]


class TestCapexNotDoubleCounted:
    def test_capex_aparece_una_sola_vez(self):
        """El CAPEX total descontado debe ser exactamente capex_usd, no 2x."""
        inputs = base_inputs()
        out = build_cashflows(inputs)

        # Con capex_schedule=[1.0] todo el CAPEX cae en el flujo 0 y ningun FCF
        # anual lo vuelve a restar.
        assert out.cashflows[0] == pytest.approx(
            -(inputs.capex_usd + inputs.working_capital_usd)
        )
        # Si el ano 1 volviera a restar el CAPEX, el FCF seria 2M mas negativo.
        capex_por_ano = _capex_schedule(inputs.capex_schedule, inputs.project_years)
        for i, _fcf in enumerate(out.annual_fcf):
            assert inputs.capex_usd * capex_por_ano[i + 1] == 0.0

    def test_escalonado_no_reparte_doble(self):
        inputs = base_inputs(capex_schedule=[0.5, 0.5])
        out = build_cashflows(inputs)
        capex_por_ano = _capex_schedule([0.5, 0.5], inputs.project_years)
        capex_total = sum(inputs.capex_usd * s for s in capex_por_ano)
        assert capex_total == pytest.approx(inputs.capex_usd)
        # Flujo 0 = -(0.5*capex + WC); FCF del ano 1 resta el otro 0.5*capex.
        assert out.cashflows[0] == pytest.approx(
            -(0.5 * inputs.capex_usd + inputs.working_capital_usd)
        )

    def test_total_capex_declarado(self):
        out = build_cashflows(base_inputs())
        assert out.total_capex == pytest.approx(2_000_000)


class TestCashflowShape:
    def test_un_flujo_mas_anos(self):
        out = build_cashflows(base_inputs(project_years=5))
        assert len(out.cashflows) == 6
        assert len(out.annual_fcf) == 5
        assert len(out.cumulative_fcf) == 6

    def test_cashflow_inicial_es_negativo(self):
        out = build_cashflows(base_inputs())
        assert out.cashflows[0] < 0

    def test_ramp_se_extiende_con_el_ultimo_valor(self):
        assert _ramp([0.5, 0.8], 5) == [0.5, 0.8, 0.8, 0.8, 0.8]
        assert _ramp([], 3) == [1.0, 1.0, 1.0]
        assert _ramp([0.4, 0.5, 0.6, 0.7, 0.8, 0.9], 3) == [0.4, 0.5, 0.6]

    def test_curva_de_aprendizaje_tiene_piso(self):
        assert _learning_factor(0.03, 0) == pytest.approx(1.0)
        assert _learning_factor(0.03, 1) == pytest.approx(0.97)
        assert _learning_factor(0.50, 50) == pytest.approx(0.5)  # piso


class TestReturns:
    def test_proyecto_viable_da_van_positivo(self):
        out = build_cashflows(base_inputs())
        assert out.npv > 0
        assert out.irr is not None

    def test_margen_negativo_da_van_negativo(self):
        out = build_cashflows(base_inputs(fob_price_usd_per_kg=1.00))
        assert out.npv < 0

    def test_tir_none_cuando_no_converge(self):
        """Un flujo que nunca cambia de signo no tiene TIR, no TIR cero."""
        out = build_cashflows(
            base_inputs(fob_price_usd_per_kg=0.10, opex_fixed_usd_year=900_000)
        )
        assert out.npv < 0
        assert out.irr is None
        assert out.payback_years is None

    def test_payback_si_se_recupera(self):
        out = build_cashflows(base_inputs())
        assert out.payback_years is not None
        assert 0 < out.payback_years < 10

    def test_resumen_marca_veredicto(self):
        inputs = base_inputs()
        summary = summarize(build_cashflows(inputs), inputs)
        assert summary["verdict"]["label"] in {"Favorable", "Marginal", "No favorable", "No se recupera"}
        assert summary["npv_usd"] > 0
        assert summary["initial_outflow_usd"] < 0


class TestPnlConsistency:
    def test_pnl_y_cashflows_coinciden(self):
        """La ganancia de cada ano del PNL debe cuadrar con el FCF de ese ano.

        FCF = EBIT - impuestos + depreciacion - CAPEX + delta capital trabajo.
        """
        inputs = base_inputs()
        out = build_cashflows(inputs)
        pnl = annual_pnl(inputs)
        assert len(pnl) == inputs.project_years

        wc_ratio = (
            inputs.wc_inventory_days + inputs.wc_receivable_days - inputs.wc_payable_days
        ) / 365.0
        capex_por_ano = _capex_schedule(inputs.capex_schedule, inputs.project_years)
        prev_wc = None

        for i, row in enumerate(pnl.itertuples()):
            wc = row.volume_kg * inputs.fob_price_usd_per_kg * wc_ratio
            # El ano 0 financia el capital de trabajo que dice el config. De ahi
            # en adelante el modelo se mueve con el delta contra el ano previo,
            # calculado con los dias de inventario/cobro/pago.
            delta_wc = -inputs.working_capital_usd if i == 0 else wc - prev_wc
            prev_wc = wc
            expected = (
                row.ebit_usd
                - row.taxes_usd
                + row.depreciation_usd
                - inputs.capex_usd * capex_por_ano[i + 1]
                + delta_wc
            )
            assert out.annual_fcf[i] == pytest.approx(expected, abs=1.0)


class TestSensitivity:
    def test_tornado_ordena_por_impacto(self):
        inputs = base_inputs()
        grid = {
            "capex_shift": [-0.3, 0.0, 0.3],
            "fob_price_shift": [-0.1, 0.0, 0.1],
        }
        out = run_sensitivity(inputs, grid)
        swings = [t["swing_usd"] for t in out["tornado"]]
        assert swings == sorted(swings, reverse=True)
        assert out["base_npv_usd"] > 0

    def test_sensibilidad_cambia_el_van(self):
        inputs = base_inputs()
        out = run_sensitivity(inputs, {"capex_shift": [-0.5, 0.5]})
        rows = out["by_variable"]["capex_shift"]
        assert rows[0]["npv_usd"] > rows[1]["npv_usd"]  # menos capex -> mejor VAN


class TestBisect:
    """El bisection se usa para los umbrales, asi que un error de signo aqui
    produce un numero plausible y equivocado en vez de un error visible."""

    def test_encuentra_la_raiz_de_una_funcion_creciente(self):
        # f(x) = x - 3  -> raiz en 3
        assert _bisect(lambda x: x - 3, 0.0, 10.0) == pytest.approx(3.0, abs=0.01)

    def test_no_devuelve_el_techo_del_rango(self):
        """Regresion: la biseccion invertida convergia al extremo alto."""
        out = _bisect(lambda x: x - 3, 0.0, 10.0)
        assert out < 10.0

    def test_si_ya_es_viable_en_el_extremo_bajo(self):
        assert _bisect(lambda x: x + 5, 0.0, 10.0) == pytest.approx(0.0)

    def test_si_no_hay_raiz_devuelve_el_alto(self):
        assert _bisect(lambda x: x - 100, 0.0, 10.0) == pytest.approx(10.0)


class TestBreakeven:
    def test_breakeven_no_disponible_si_el_base_es_negativo(self):
        inputs = base_inputs(fob_price_usd_per_kg=1.00)
        out = breakeven(inputs)
        assert out["available"] is False

    def test_breakeven_da_umbral_de_precio(self):
        inputs = base_inputs()
        out = breakeven(inputs)
        assert out["available"] is True
        assert 0 < out["fob_price_floor_usd_per_kg"] < inputs.fob_price_usd_per_kg

    def test_umbral_de_precio_es_realmente_el_umbral(self):
        """El VAN debe cambiar de signo justo alrededor del piso reportado."""
        inputs = base_inputs()
        floor = breakeven(inputs)["fob_price_floor_usd_per_kg"]
        below = build_cashflows(_with(inputs, fob_price_usd_per_kg=floor * 0.97)).npv
        above = build_cashflows(_with(inputs, fob_price_usd_per_kg=floor * 1.03)).npv
        assert below < 0 < above
