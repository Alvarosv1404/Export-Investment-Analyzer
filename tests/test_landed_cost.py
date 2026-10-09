"""Tests del costo puesto en destino y del arancel.

El riesgo aqui es de unidad, no de formula. `duty_pct` viene del CSV como
porcentaje (6.0 = 6%) y la fraccion (0.06) es interna. Confundirlas no lanza
ningun error: produce un arancel de 600% y un landed cost 7x mas alto, que
sigue pareciendo un numero valido. Estos tests fijan la convencion.
"""

from __future__ import annotations

import pytest

from exportanalysis.pipeline.landed_cost import (
    _duty_rate,
    landed_cost,
    price_positioning,
    tariff_sensitivity,
)

FOB = 4.619


class TestDutyUnit:
    def test_porcentaje_a_fraccion(self):
        assert _duty_rate(6.0) == pytest.approx(0.06)
        assert _duty_rate(0.0) == 0.0
        assert _duty_rate(None) == 0.0
        assert _duty_rate(100.0) == pytest.approx(1.0)

    def test_no_confunde_6_por_ciento_con_600_por_ciento(self):
        """Regresion: 6.0 se aplicaba como 6.0 (600%) sobre el CIF."""
        out = landed_cost(FOB, duty_pct=6.0)
        # 4.619 * 1.055 (flete 5% + seguro 0.5%) = CIF ~4.873
        assert out["cif_usd_per_kg"] == pytest.approx(4.873, abs=0.01)
        assert out["duty_usd_per_kg"] == pytest.approx(0.292, abs=0.01)
        assert out["landed_usd_per_kg"] == pytest.approx(5.165, abs=0.01)


class TestLandedCost:
    def test_sin_arancel(self):
        out = landed_cost(FOB, duty_pct=0.0)
        assert out["duty_usd_per_kg"] == 0.0
        assert out["landed_usd_per_kg"] == out["cif_usd_per_kg"]
        assert out["duty_share_of_landed"] == 0.0

    def test_arancel_nulo_se_trata_como_cero(self):
        out = landed_cost(FOB, duty_pct=None)
        assert out["duty_usd_per_kg"] == 0.0
        assert out["duty_rate"] == 0.0

    def test_el_arancel_va_sobre_el_cif_no_sobre_el_fob(self):
        """Base imponible de aduanas: si fuera sobre FOB daria 0.277, no 0.292."""
        out = landed_cost(FOB, freight_pct_fob=0.05, duty_pct=6.0)
        sobre_fob = FOB * 0.06
        sobre_cif = out["cif_usd_per_kg"] * 0.06
        # tolerance de 1e-3: los valores se redondean a 4 decimales.
        assert out["duty_usd_per_kg"] == pytest.approx(sobre_cif, abs=1e-3)
        assert out["duty_usd_per_kg"] > sobre_fob

    def test_cif_incluye_flete_y_seguro(self):
        out = landed_cost(FOB, freight_pct_fob=0.05, insurance_pct_fob=0.005)
        assert out["freight_usd_per_kg"] == pytest.approx(FOB * 0.05, abs=1e-3)
        assert out["insurance_usd_per_kg"] == pytest.approx(FOB * 0.005, abs=1e-3)
        assert out["cif_usd_per_kg"] == pytest.approx(FOB * 1.055, abs=1e-3)

    def test_un_arancel_alto_su_domina_el_costo(self):
        """Con 60% el arancel pesa mas que el flete: ahi si decide la inversion."""
        out = landed_cost(FOB, duty_pct=60.0)
        assert out["duty_usd_per_kg"] > out["freight_usd_per_kg"]
        assert out["duty_share_of_landed"] > 0.3

    def test_un_arancel_bajo_no_decide(self):
        """Con 6% el arancel es una fraccion del precio: no es la variable clave."""
        out = landed_cost(FOB, duty_pct=6.0)
        assert out["duty_share_of_landed"] < 0.10


class TestPricePositioning:
    def test_margen_del_importador_sobre_precio_de_venta(self):
        out = price_positioning(FOB, duty_pct=0.0, target_margin=0.20)
        # precio_venta = landed / (1 - 0.20)
        assert out["importer_price_usd_per_kg"] == pytest.approx(
            out["landed_usd_per_kg"] / 0.80, abs=1e-3
        )

    def test_margen_mayor_exige_mas_precio(self):
        bajo = price_positioning(FOB, target_margin=0.10)
        alto = price_positioning(FOB, target_margin=0.30)
        assert alto["importer_price_usd_per_kg"] > bajo["importer_price_usd_per_kg"]

    def test_arancel_alto_traslada_el_precio(self):
        sin = price_positioning(FOB, duty_pct=0.0)["importer_price_usd_per_kg"]
        con = price_positioning(FOB, duty_pct=40.0)["importer_price_usd_per_kg"]
        assert con > sin


class TestTariffSensitivity:
    def test_el_barrido_incluye_el_arancel_real(self):
        """Sin dato cargado, el anclaje es 0 y el barrido sube desde ahi."""
        out = tariff_sensitivity(FOB, "090111", 392)
        assert not out["is_real_tariff"].any()
        assert out["duty_pct"].min() == pytest.approx(0.0)
        assert out["duty_pct"].max() > 0

    def test_landed_crece_con_el_arancel(self):
        out = tariff_sensitivity(FOB, "090111", 392)
        assert out["landed_usd_per_kg"].is_monotonic_increasing

    def test_reporte_en_porcentaje(self):
        out = tariff_sensitivity(FOB, "090111", 392)
        assert out["duty_pct"].max() <= 100.0
