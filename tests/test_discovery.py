"""Tests del autodescubrimiento de productos desde data/.

La promesa: dejar la data de un producto en `data/<hs6> <nombre>/` debe bastar
para que aparezca en el catalogo, sin tocar products.yaml ni el codigo. Estos
tests fijan ese contrato con carpetas temporales, sin depender de la data real.
"""

from __future__ import annotations

import pytest

from exportanalysis import config


def _write_xlsx(folder, name: str) -> None:
    """Un .xlsx vacio alcanza: el descubrimiento solo mira el nombre."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(b"placeholder")


class TestSlugify:
    def test_quita_tildes_y_normaliza(self):
        assert config._slugify("Naranja fresca") == "naranja_fresca"
        assert config._slugify("Cítricos") == "citricos"
        assert config._slugify("Ají páprika") == "aji_paprika"

    def test_colapsa_separadores(self):
        assert config._slugify("Uva   de -- mesa") == "uva_de_mesa"

    def test_vacio_cae_a_producto(self):
        assert config._slugify("---") == "producto"


class TestFolderHs6:
    def test_prefijo_del_nombre(self, tmp_path):
        folder = tmp_path / "080510 naranja fresca"
        folder.mkdir()
        assert config._folder_hs6(folder) == "080510"

    def test_deriva_de_los_archivos_si_no_hay_prefijo(self, tmp_path):
        folder = tmp_path / "naranja fresca"
        _write_xlsx(folder, "exporting-economies_080510.xlsx")
        _write_xlsx(folder, "perus-exports-080510.xlsx")
        assert config._folder_hs6(folder) == "080510"

    def test_sin_hs6_devuelve_none(self, tmp_path):
        folder = tmp_path / "sin codigo"
        _write_xlsx(folder, "datos.xlsx")
        assert config._folder_hs6(folder) is None


class TestFolderName:
    def test_quita_el_prefijo_hs6(self, tmp_path):
        folder = tmp_path / "080510 naranja fresca"
        folder.mkdir()
        assert config._folder_name(folder, "080510") == "Naranja fresca"

    def test_capitaliza_si_esta_todo_en_minusculas(self, tmp_path):
        folder = tmp_path / "080510 quinua"
        folder.mkdir()
        assert config._folder_name(folder, "080510") == "Quinua"

    def test_respeta_mayusculas_existentes(self, tmp_path):
        folder = tmp_path / "080510 Naranja Fresca"
        folder.mkdir()
        assert config._folder_name(folder, "080510") == "Naranja Fresca"

    def test_sin_nombre_usa_el_hs6(self, tmp_path):
        folder = tmp_path / "080510"
        folder.mkdir()
        assert config._folder_name(folder, "080510") == "Producto 080510"


class TestFolderNandina:
    def test_toma_el_excel_de_10_digitos(self, tmp_path):
        folder = tmp_path / "080510 naranja fresca"
        _write_xlsx(folder, "0805100000.xlsx")
        _write_xlsx(folder, "exporting-economies_080510.xlsx")
        assert config._folder_nandina(folder, "080510") == "0805100000"

    def test_prefiere_la_que_empieza_con_el_hs6(self, tmp_path):
        folder = tmp_path / "080510 naranja fresca"
        _write_xlsx(folder, "0805290000.xlsx")
        _write_xlsx(folder, "0805100000.xlsx")
        assert config._folder_nandina(folder, "080510") == "0805100000"

    def test_sin_excel_de_10_digitos_devuelve_none(self, tmp_path):
        folder = tmp_path / "080510 naranja fresca"
        _write_xlsx(folder, "exporting-economies_080510.xlsx")
        assert config._folder_nandina(folder, "080510") is None


class TestDiscoverProducts:
    def test_detecta_producto_completo(self, tmp_path):
        _write_xlsx(tmp_path / "080510 naranja fresca", "0805100000.xlsx")
        products = config._discover_products(base=tmp_path)
        assert len(products) == 1
        product = products[0]
        assert product.slug == "naranja_fresca"
        assert product.hs6 == "080510"
        assert product.nandina == "0805100000"
        assert product.name == "Naranja fresca"

    def test_salta_carpetas_reservadas_y_ocultas(self, tmp_path):
        _write_xlsx(tmp_path / "raw", "exporting-economies_080510.xlsx")
        _write_xlsx(tmp_path / ".cache", "exporting-economies_080510.xlsx")
        _write_xlsx(tmp_path / "080510 naranja fresca", "0805100000.xlsx")
        products = config._discover_products(base=tmp_path)
        assert [p.slug for p in products] == ["naranja_fresca"]

    def test_salta_carpeta_sin_excel(self, tmp_path):
        folder = tmp_path / "080510 naranja fresca"
        folder.mkdir()
        (folder / "notas.txt").write_text("sin data", encoding="utf-8")
        assert config._discover_products(base=tmp_path) == []

    def test_sin_carpeta_data_no_falla(self, tmp_path):
        assert config._discover_products(base=tmp_path / "no_existe") == []

    def test_slugs_repetidos_reciben_sufijo(self, tmp_path):
        _write_xlsx(tmp_path / "080510 naranja fresca", "0805100000.xlsx")
        _write_xlsx(tmp_path / "080520 naranja-fresca", "0805200000.xlsx")
        slugs = [p.slug for p in config._discover_products(base=tmp_path)]
        assert slugs == ["naranja_fresca", "naranja_fresca_2"]


class TestIndustryFolders:
    def test_la_industria_sale_de_la_carpeta_contenedora(self, tmp_path):
        _write_xlsx(tmp_path / "Agricola" / "080510 naranja fresca", "0805100000.xlsx")
        products = config._discover_products(base=tmp_path)
        assert len(products) == 1
        assert products[0].industry == "Agricola"

    def test_normaliza_mayusculas_del_nombre_de_industria(self, tmp_path):
        _write_xlsx(tmp_path / "pesquero" / "030743 pota calamar", "0307430000.xlsx")
        products = config._discover_products(base=tmp_path)
        assert products[0].industry == "Pesquero"

    def test_respeta_industrias_fuera_de_la_taxonomia(self, tmp_path):
        _write_xlsx(tmp_path / "Bebidas" / "220210 gaseosa", "2202100000.xlsx")
        products = config._discover_products(base=tmp_path)
        assert products[0].industry == "Bebidas"

    def test_producto_suelto_en_la_raiz_no_tiene_industria(self, tmp_path):
        _write_xlsx(tmp_path / "080510 naranja fresca", "0805100000.xlsx")
        assert config._discover_products(base=tmp_path)[0].industry is None

    def test_mezcla_de_raiz_y_carpetas_de_industria(self, tmp_path):
        _write_xlsx(tmp_path / "080510 naranja fresca", "0805100000.xlsx")
        _write_xlsx(tmp_path / "Agricola" / "081040 arandano", "0810400000.xlsx")
        industries = {p.slug: p.industry for p in config._discover_products(base=tmp_path)}
        assert industries == {"naranja_fresca": None, "arandano": "Agricola"}

    def test_carpeta_de_industria_reservada_se_ignora(self, tmp_path):
        _write_xlsx(tmp_path / "raw" / "080510 naranja fresca", "0805100000.xlsx")
        assert config._discover_products(base=tmp_path) == []


class TestCatalogMerge:
    @pytest.fixture
    def fake_discovery(self, monkeypatch):
        """Inyecta un producto descubierto y limpia la cache antes y despues."""
        extra = config.Product(
            slug="naranja_fresca", name="Naranja fresca", hs6="080510", nandina="0805100000"
        )
        monkeypatch.setattr(config, "_discover_products", lambda base=None: [extra])
        config.load_catalog.cache_clear()
        try:
            yield extra
        finally:
            monkeypatch.undo()
            config.load_catalog.cache_clear()

    def test_agrega_lo_descubierto(self, fake_discovery):
        catalog = config.load_catalog()
        slugs = {p.slug for p in catalog.products}
        assert "naranja_fresca" in slugs
        assert "cafe_verde" in slugs  # lo curado sigue

    def test_products_yaml_manda_sobre_lo_descubierto(self, monkeypatch):
        curado = config.Product(slug="cafe_verde", name="Cafe curado", hs6="090111")
        duplicado = config.Product(slug="cafe_duplicado", name="Cafe otro", hs6="090111")
        monkeypatch.setattr(config, "_read_yaml", lambda name: {"products": [curado.model_dump()]})
        monkeypatch.setattr(config, "_discover_products", lambda base=None: [duplicado])
        config.load_catalog.cache_clear()
        try:
            slugs = {p.slug for p in config.load_catalog().products}
        finally:
            monkeypatch.undo()
            config.load_catalog.cache_clear()
        assert "cafe_verde" in slugs
        assert "cafe_duplicado" not in slugs


class TestIndustry:
    def test_producto_descubierto_no_tiene_industria(self, tmp_path):
        _write_xlsx(tmp_path / "080510 naranja fresca", "0805100000.xlsx")
        product = config._discover_products(base=tmp_path)[0]
        assert product.industry is None

    def test_catalogo_curado_declara_industria(self):
        products = {p.slug: p for p in config.load_catalog().products}
        assert products["cafe_verde"].industry == "Agricola"
        assert products["pota_calamar"].industry == "Pesquero"

    def test_toda_industria_declarada_esta_en_la_taxonomia(self):
        for product in config.load_catalog().products:
            if product.industry:
                assert product.industry in config.INDUSTRIES, product.slug


class TestAssumptions:
    def test_missing_for_producto_nuevo_lista_los_clave(self):
        missing = config.load_assumptions().missing_for("producto_que_no_existe")
        assert set(missing) == set(config.REQUIRED_ASSUMPTIONS)

    def test_missing_for_producto_completo_es_vacio(self):
        assert config.load_assumptions().missing_for("cafe_verde") == []

    def test_for_producto_incompleto_falla_explicito(self):
        with pytest.raises(ValueError, match="Faltan supuestos"):
            config.load_assumptions().for_product("producto_que_no_existe")

    def test_for_producto_acepta_supuestos_completos_ingresados_por_usuario(self):
        assumptions = config.load_assumptions()
        overrides = {key: 1.0 for key in config.REQUIRED_ASSUMPTIONS}

        assert assumptions.for_product("producto_que_no_existe", overrides) == {
            **assumptions.effective("producto_que_no_existe"),
            **overrides,
        }
