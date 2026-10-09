# Data organizada por producto

Cada carpeta corresponde a HS6 con nombre descriptivo: data/<HS6> <nombre>/

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

Para agregar un producto sin tocar codigo:
1. Crear carpeta data/<hs6> <nombre>/
2. Colocar los 4 archivos con nombres exactos
3. Anadir bloque en config/products.yaml con slug, name, hs6, unit, competitors, presentations
4. Opcional: anadir supuestos en config/assumptions.yaml (por slug)

El pipeline detecta archivos automaticamente por hs6 (busqueda recursiva en data/).
