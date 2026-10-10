# Data organizada por producto e industria

El catalogo se arma solo a partir de estas carpetas: no hace falta tocar codigo
para sumar un producto. Hay dos formas de dejar la data, y se pueden mezclar.

## 1. Organizada por industria (recomendada)

```
data/
  Agricola/
    080510 naranja fresca/
    081040 arandano fresco/
    ...
  Agroindustria/
    151110 aceite palma crudo/
    ...
  Pesquero/
    030743 pota calamar congelado/
    ...
```

- La carpeta de industria es solo para agrupar y para que se entienda el rubro:
  su nombre se usa como `industry` del producto (ver `INDUSTRIES` en
  `src/exportanalysis/config.py`).
- Una carpeta con Excel es un producto; una carpeta sin Excel es una carpeta de
  industria y se revisan sus subcarpetas.
- Las carpetas reservadas (`raw`, `interim`, `processed`) y las que empiezan
  con `.` o `_` se ignoran.

## 2. Producto suelto en la raiz

Tambien puedes dejar la carpeta del producto directamente en `data/`:

```
data/080510 naranja fresca/
```

En ese caso el producto aparece igual, pero sin industria declarada.

## Nombre de la carpeta del producto

`data/<industria>/<HS6> <nombre>/` — el HS6 (6 digitos) al inicio del nombre
fija la partida del producto. Si no esta en el nombre, se deduce del nombre de
los archivos.

## Archivos requeridos (Trade Map)

Por producto se esperan 4 archivos Excel (nombres exactos):

1. exporting-economies_<hs6>.xlsx - Exportadores mundiales
2. importing-economies_<hs6>.xlsx - Importadores mundiales  
3. perus-exports-to-world-by-importer_<hs6>.xlsx - Exportaciones peruanas por socio destino (serie historica, valores USD Thousand)
4. perus-exports-to-world-in-2025-by-importer_<hs6>.xlsx - Indicadores Peru 2025 por socio (Value kUSD, Quantity, Unit Value)

## Fuentes

- Trade Map (ITC) - datos publicos de comercio internacional
- Datos cargados localmente desde Excel (sin APIs ni claves)

## Unidades y lectura

- Los valores de los Excel vienen en **USD Thousand** y se convierten a USD.
- El snapshot 2025 trae `Quantity` en toneladas (`Quantity Unit` = Tons); el
  pipeline la normaliza a kilos. El volumen solo existe en 2025: en los demas
  anos queda vacio, no en cero.
- `reporterCd`/`partnerCd` son codigos M49; `partnerCd = 0` es el total "World".
- La busqueda de archivos ignora cualquier carpeta `_cache`.

## Agregar nuevo producto

Lo minimo (sin tocar codigo):
1. Crear `data/<Industria>/<hs6> <nombre>/`
2. Colocar los 4 archivos con nombres exactos

Opcional, para enriquecer el producto en `config/products.yaml` (nombre cuidado,
competidores, presentaciones, `industry`) y en `config/assumptions.yaml`
(supuestos de inversion por slug). Sin supuestos, el producto igual muestra su
analisis de mercado, con un aviso de lo que falta.

El pipeline detecta los productos automaticamente (busqueda recursiva en data/).
