# Export Investment Analyzer

Motor de analisis para evaluar inversiones en exportacion: mercado, competencia
y viabilidad financiera (VAN/TIR) con datos publicos. La familia inicial de
productos es la agroexportacion peruana.

Aplicacion web para responder una pregunta concreta: **si invierto en exportar
un producto, cuanto dinero puedo hacer y con que evidencia.**

Combina dos cosas que normalmente viven separadas:

1. **Datos publicados de comercio** (volumen, valor FOB, precio unitario,
   principales destinos y competidores) que salen de los **Excel de Trade Map
   locales**. El proyecto corre 100% offline: sin API, sin claves, sin internet.
2. **Un modelo de inversion** (CAPEX, OPEX, capital de trabajo, VAN, TIR,
   payback, sensibilidad) con los supuestos que defines tu.

La separacion es el punto. El reporte marca cada numero como
*dato publicado* o como *supuesto tuyo*, porque confundir los dos es el error
mas comun en este tipo de analisis.

---

## Que necesitas antes de mirar un VAN

El orden importa, y no es cosmetico:

1. **Economia unitaria.** El margen bruto por kilo contra el precio FOB real
   de mercado. Si es negativo, el VAN negativo es consecuencia, no informacion.
2. **Volumen que el mercado sostiene.** Cuanto cabe crecer antes de que el
   mercado deje de dar. Si el headroom es de 70 millones de kilos y tu planta
   procesa 500 mil, el cuello de botella eres tu, no la demanda.
3. **Solo entonces el VAN.**

El reporte sigue ese orden a proposito.

---

## Arquitectura

Dos procesos, un comando:

```
npm run dev
   |
   +-- [api] uvicorn en http://127.0.0.1:8010   <- FastAPI, datos y modelo
   |
   +-- [web] Vite en    http://localhost:5180    <- interfaz, hace proxy a /api
```

El navegador solo ve el puerto **5180**. Vite hace proxy de `/api` y `/health`
hacia el backend, asi que no hay CORS y el frontend llama a rutas relativas.
El backend queda accesible directo en **8010** para las docs y para depurar.

## Instalacion

```bash
npm run setup
```

Ese script instala las dependencias de Node, instala el paquete Python en modo
editable y crea la plantilla de aranceles. Es el atajo para lo de abajo, que es
lo mismo:

```bash
python -m venv .venv
.venv\Scripts\activate                 # Windows
pip install -e ".[dev]"                # backend + tests
npm install                            # frontend
```

## Correr la app

```bash
npm run dev
```

Abre `http://localhost:5180`.

## Puertos

Los puertos estan en **`dev.config.json`** y en ningun otro lugar:

```json
{
  "api": 8010,
  "web": 5180,
  "host": "127.0.0.1"
}
```

Ese archivo es la unica fuente de verdad. Lo leen `scripts/run-api.mjs`,
`vite.config.js`, `scripts/check-ports.mjs` y los tests de la API. El puerto
**8010** es el que usa el backend porque el 8000 suele estar ocupado en esta
maquina, y el **5180** porque el 5173 lo tiene otro proyecto local.

Para cambiarlo, edita `dev.config.json` y levanta de nuevo. No hay que tocar
nada mas: el proxy de Vite se entera solo.

> Por que importa que sea una sola fuente: si el puerto estuviera escrito a
> mano en varios lugares y cambiases solo uno, el sintoma es "la web carga pero
> /api da 404", porque el proxy sigue apuntando al puerto viejo. Es una perdida
> de tiempo dificil de diagnosticar.

### Si un puerto esta ocupado

```bash
npm run check:ports
```

```
  OCUPADO  API (FastAPI): puerto 8010 -> python.exe (PID 26864)
  libre    Web (Vite): puerto 5180
```

Te dice que proceso lo tiene. Si prefieres otro puerto, cambialo en
`dev.config.json`. `npm run dev` tambien falla solo y con un mensaje claro si el
puerto esta ocupado, en vez de un `Errno 10048` de uvicorn.

## Otros comandos

| Comando | Que hace |
|---|---|
| `npm run dev` | Levanta API + web juntos (lo normal) |
| `npm run dev:api` | Solo el backend, en el puerto de `dev.config.json` |
| `npm run dev:web` | Solo el frontend de Vite |
| `npm run build` | Build estatico del frontend a `dist/` |
| `npm test` | Verifica la API y luego corre pytest |
| `npm run lint` | Ruff (Python) + ESLint (JavaScript) |
| `npm run tariffs` | Checklist de que buscar en Trade Map, con los destinos reales |
| `npm run tariffs:fill` | Pregunta los aranceles y escribe `tariffs.csv` |
| `npm run check:ports` | Revisa que los puertos esten libres |
| `npm run setup` | Instala dependencias y crea la plantilla |

## Endpoints

| Ruta | Que hace |
|---|---|
| `GET /` | Reporte completo con los bloques del analisis y graficos |
| `GET /api/products` | Catalogo de productos configurados |
| `GET /api/analysis/{slug}` | Analisis completo en JSON |
| `GET /api/analysis/{slug}?target_share=0.12` | Con participacion de mercado objetivo explicita |
| `GET /api/analysis/{slug}?price_usd_per_kg=6.5` | Con precio FOB de venta explicito |
| `GET /api/comparison?slugs=cafe_verde,uva_fresca` | Comparacion seleccionada con serie 2016-2025, variacion anual y CAGR desde 2016 |
| `GET /health` | Sonda de salud |
| `GET /docs` | Swagger UI interactivo |

La interfaz separa **Analisis por producto** de **Comparacion de productos**.
En la segunda vista puedes elegir uno o mas productos; la seleccion se conserva
en la URL. Incluye graficas de FOB del ultimo ano disponible, evolucion de
exportaciones y crecimiento interanual, junto con tablas anuales y CAGR
2016-2025. Son exportaciones FOB del Peru reportadas en Trade Map, no valores
importados de los mercados destino. Si el Excel no contiene un dato anual, se
muestra como `n/d` y no se interpreta como cero.

## Correr sin navegador

```bash
python scripts/smoke_test.py cafe_verde
```

Imprime el mismo analisis en texto. Util para revisar cambios rapido o para
correrlo en un cron y comparar contra el run anterior.

---

## Produccion

`npm run build` emite `dist/` con rutas relativas, y FastAPI lo sirve
automaticamente si el directorio existe. El mismo build funciona servido por
FastAPI, por nginx o por un CDN sin reconfiguracion.

Hay un segundo modo: sin `dist/`, FastAPI cae a los templates de Jinja y
renderiza todo en el servidor. Sirve para que la API sea util sola, sin Node
instalado, y para poder imprimir el reporte con el JS deshabilitado. Se fuerza
con `FORCE_SSR=1`.

---

## Agregar un producto

Todo vive en `config/products.yaml`. Un producto nuevo son ocho lineas:

```yaml
products:
  cacao_en_grano:
    name: "Cacao en grano"
    hs6: "180110"          # HS-6: la unidad de analisis
    nandina: "1801100000"  # partida SUNAT de 10 digitos, para el arancel
    unit: "kg"
    competitors: [170, 76, 218, 484, 818]
```

Y sus supuestos en `config/assumptions.yaml`:

```yaml
products:
  cacao_en_grano:
    capacity_kg_year: 300000
    capex_usd: 2800000
    variable_cost_usd_per_kg: 0.90
    purchase_cost_usd_per_kg: 3.10
    opex_fixed_usd_year: 140000
    working_capital_usd: 220000
```

No hay que tocar codigo. El catalogo, el reporte y la API lo toman
automaticamente.

---

## De donde salen los datos

### Mercado y competencia: Excel de Trade Map (100% offline)

El proyecto no consulta ninguna API. Cada producto es una carpeta
`data/<hs6> <nombre>/` con cuatro Excel exportados de ITC Trade Map:

| Archivo | Que trae | Unidad |
|---|---|---|
| `exporting-economies_<hs6>.xlsx` | Exportaciones de cada pais exportador (partner = World), serie por ano | USD Thousand |
| `importing-economies_<hs6>.xlsx` | Importaciones de cada pais importador (partner = World), serie por ano | USD Thousand |
| `perus-exports-to-world-by-importer_<hs6>.xlsx` | Exportaciones peruanas por destino, serie por ano | USD Thousand |
| `perus-exports-to-world-in-2025-by-importer_<hs6>.xlsx` | Snapshot 2025 por destino, con cantidad y precio unitario | kUSD, Tons, USD/Tons |

Como se leen:

- `reporterCd` / `partnerCd` son codigos **M49** (`config/countries.yaml`);
  `604` es Peru y `partnerCd = 0` es la fila de total "World".
- El valor se convierte a USD (los archivos vienen en miles) y la cantidad a
  kilos cuando Trade Map la publica en toneladas. El volumen solo existe en el
  snapshot 2025; en los demas anos queda `null`, que es un hueco real de la
  fuente, no un cero.
- El precio de venta del modelo sale del valor FOB ponderado por kilo de 2025.
  Se puede sobrescribir con `price_usd_per_kg` y el reporte dice de donde
  salio (`calculado de históricos`, `ajustado por el usuario` o `unit value del
  Excel`).

Para agregar o reemplazar data, copia los cuatro Excel en la carpeta del
producto con exactamente esos nombres. Ver `data/README.md`.

### Aranceles: carga manual, y por que

**No existe una API gratuita, estable y sin registro** que devuelva el arancel
aplicado a un HS-6 para un par (pais destino, pais de origen). Se verificaron
estas opciones:

| Fuente | Resultado |
|---|---|
| **SUNAT** (Aduanet, acumulado por subpartida/pais) | Responde 200 pero devuelve "No se encontraron registros" para todo, incluidas importaciones que si existen. Backend vacio. No usable. |
| **WITS / World Bank** | El endpoint documentado responde 400/403/405 segun la variante de URL. El adaptador se retiro: el modelo corre offline. |
| **WTO API** | Requiere registro y subscription key. Gratis, pero con signup. |
| **UNCTAD TRAINS** | Es la fuente real de WITS. No es gratuita. |
| **ITC Market Access Map** | Gratis e incluye el arancel junto con la data de comercio. Peru tiene acceso completo. Sin API publica, pero exporta a Excel. |

Por eso el arancel es un **CSV editable** y no un scraper. Es la opcion
correcta, no un atajo: el arancel cambia por acuerdo comercial y por medidas
antidumping, y alguien tiene que firmar que el numero es correcto.

La plantilla se crea sola con `npm run setup`, o a mano:

```bash
python -c "import sys; sys.path.insert(0,'src'); from exportanalysis.sources.manual_tariffs import ensure_template; ensure_template()"
```

### Como se llena sin volverse loco: el asistente

```bash
npm run tariffs              # que buscar, para cada destino real
npm run tariffs:fill         # te pregunta los numeros y escribe el CSV
```

`npm run tariffs` te arma la lista de consultas que ya viene con el codigo y el
pais, usando **los destinos reales del ultimo anio con data**, no una lista
inventada. Para cafe verde son Estados Unidos, Alemania, Belgica, Canada, Suecia
y Reino Unido. De cada uno te dice el valor que hay ahora en el CSV y, si esa
fila es de plantilla, lo marca:

```
  [842] Estados Unidos
        buscar:  HS 090111  ->  Estados Unidos  ->  applied duty / arancel
        actual:  0.0 %  <-- PLANTILLA, sin verificar en tariffs.csv
```

Eso importa mas de lo que parece: la plantilla trae `0.0` de ejemplo, y si el
reporte lo tomara por dato estariamos afirmando un arancel de 0% que nadie
verifico. Por eso el asistente distingue "dato" de "ejemplo".

`npm run tariffs:fill` pregunta uno por uno, en porcentaje, y escribe el CSV
solo. Si pones `0` lo marca como `PREF` a proposito: un arancel de cero casi
siempre es un acuerdo comercial, no una linea nacional.

> **Por que no hay un boton que baje el arancel solo:** Trade Map es una app web
> de ASP.NET. Se comprobo que hasta las URLs profundas devuelven siempre el mismo
> shell de "Trade Map beta is loading", porque los datos entran por XHR con un
> token de sesion. El propio ITC dice que solo da acceso a una API "in very
> specific circumstances". No hay contrato que proteja esos endpoints, asi que un
> scraper se rompe sin avisar.
>
> El endpoint de aranceles de UN Comtrade (`data/v1/getTariffline`) requiere
> `subscription-key`. Como el proyecto corre offline, no se usa: el arancel entra
> a mano por este CSV.

El archivo queda en `data/raw/tariffs/tariffs.csv`:

```csv
hs6,destination,origin,duty_type,duty_pct,year,source,notes
090111,842,604,PREF,0.0,2025,Market Access Map,Verificar TLC
090111,276,604,PREF,0.0,2025,Acuerdo UE-Peru,
090111,392,604,MFN,,2025,Market Access Map,Dejar vacio si no se conoce
```

- `destination` y `origin` son codigos **M49** (`config/countries.yaml`).
- `duty_type`: `PREF` (preferencial, manda si hay acuerdo), `AHS` (arancel
  efectivamente aplicado), `MFN` (linea nacional, el peor caso).
- `duty_pct` va en **porcentaje**: `6.0` significa 6%. Dejarlo vacio marca el
  valor como supuesto, no como dato, y el reporte lo dice.

---

## Supuestos: tu parte del trabajo

Ninguna API te va a decir cuanto cuesta tu planta ni a cuanto compras el
pergamino. Esos numeros van en `config/assumptions.yaml` y **son ejemplos, no
cotizaciones**. Antes de mirar el VAN reemplaza al menos:

- `purchase_cost_usd_per_kg` → tu precio de compra real
- `variable_cost_usd_per_kg` → tu costo de procesamiento por kg
- `capex_usd` → cotizacion de la planta
- `opex_fixed_usd_year` → planilla, alquiler, servicios
- `discount_rate` → tu WACC

Hay escenarios piloto de ejemplo para **todos los productos del catalogo** en
`config/assumptions.yaml`, para que el reporte y el modelo puedan ejecutarse.
Son cifras hipoteticas, no cotizaciones ni datos publicados, y no validan la
rentabilidad. Sustituyelas por cotizaciones de proveedores y costos reales
antes de tomar una decision.

El reporte distingue siempre entre dato y supuesto, y marca de donde salio la
curva de ocupacion de la planta (`ramp_source`).

---

## Como esta armado el proyecto

```
config/            productos, supuestos, paises  (todo declarativo)
dev.config.json    puertos de desarrollo (fuente unica de verdad)
package.json       scripts npm; los puertos NO se escriben aqui
eslint.config.js   reglas de ESLint 9 para el frontend y los scripts .mjs
vite.config.js     build del frontend + proxy hacia la API

frontend/          interfaz web (Vite, JavaScript modular, sin framework)
  index.html
  css/app.css
  js/
    main.js        orquestacion; el estado vive en la URL
    api.js         llamadas a /api, sin URLs hardcodeadas
    components.js  los 8 bloques del reporte
    charts.js      graficos con Chart.js
    format.js      formato de moneda, porcentaje y volumen

src/exportanalysis/
  sources/         trademap_excel.py, manual_tariffs.py, sunat.py (offline)
  pipeline/        market.py, competitors.py, excel_analysis.py, analyze.py
  model/           financials.py, valuation.py, unit_economics.py
  api/main.py      FastAPI; sirve dist/ si existe, si no cae a Jinja
  web/templates/   render en servidor (fallback sin Node)

scripts/
  setup.mjs        instala dependencias y crea la plantilla
  run-api.mjs      levanta uvicorn en el puerto de dev.config.json
  check-ports.mjs  revisa que los puertos esten libres
  check-api.mjs    verifica el contrato de la API
  tariff_helper.py  que buscar en Trade Map, y escribir el CSV sin editarlo a mano
  smoke_test.py    el analisis completo en texto

tests/             test_financials.py, test_landed_cost.py, test_api.py
```

El circuito que cierra el modelo:

```
Trade Map (Excel local) ─> mercado (volumen, FOB, precio, destinos)
                         ─> competidores (share, ranking, headroom)
                         ─> volumen implicito ─> curva de ocupacion de la planta
                         ─> P&L, flujo de caja, VAN, TIR, payback, sensibilidad
```

La curva de ocupacion sale del **headroom real de mercado**, no de un supuesto
inventado: si el mercado permite 70 millones de kilos y tu planta hace 500 mil,
la rampa satura al 100% y el reporte dice que el cuello de botella es la
planta, no la demanda.

### Decisiones de diseno que conviene conocer

- **El puerto esta en un solo archivo.** `dev.config.json`. Ver la seccion de
  puertos, que explica por que importa.
- **`capex_schedule` esta indexado desde el ano 0.** `[1.0]` significa todo el
  CAPEX antes de arrancar. Lo que no escribas no se gasta. La fraccion se
  aplica una sola vez: un CAPEX contado dos veces es un VAN erroneo tipico e
  invisible.
- **`duty_pct` esta en porcentaje** en todo el sistema (6.0 = 6%) y la
  conversion a fraccion ocurre en un solo punto. El arancel se aplica sobre el
  **CIF**, que es la base imponible de aduanas, no sobre el FOB.
- **Los NaN se convierten a `null` en el borde.** Un hueco en la data de
  comercio es `NaN` en pandas, y `NaN` no es JSON valido.
- **La biseccion de los umbrales espera funciones crecientes.** El VAN sube
  con el precio y con la ocupacion, asi que si `f(mid) > 0` la raiz esta por
  debajo de `mid`.
- **El frontend no usa framework.** Son ocho bloques fijos y sin estado;
  introducir React seria mas ceremonia que ayuda. El estado vive en la URL, asi
  que cualquier vista es compartible con un link.
- **Chart.js va por CDN, no por npm.** Es una libreria estable de 200 KB que no
  necesita versionarse con el proyecto. Para uso sin conexion, copiala a
  `frontend/vendor/` y cambia el `<script>` por una ruta local.

---

## Tests

```bash
npm test                 # verifica la API y luego corre pytest
npm run lint             # ruff + eslint
```

O por separado:

```bash
python -m pytest         # 61 tests del modelo, arancel y API
python -m ruff check src tests scripts
node scripts/check-api.mjs --external   # contra un backend ya levantado
```

Los tests apuntan a los errores que no se ven: CAPEX duplicado, arancel
confundido entre porcentaje y fraccion, biseccion con el signo invertido,
`NaN` rompiendo el JSON, y ramp de ocupacion sin origen declarado.

`npm test` no necesita un `npm run dev` en otro terminal: `check-api.mjs` levanta
el backend, espera el health check, corre las verificaciones y lo apaga.

---

## Cuando algo falla

| Sintoma | Causa probable y que hacer |
|---|---|
| `Errno 10048` al arrancar | El puerto de `dev.config.json` esta ocupado. `npm run check:ports` dice quien. |
| La web carga pero `/api` da 404 | El proxy apunta a un puerto que no coincide. Verifica que `dev.config.json` tenga el puerto que corre `npm run check:ports`. |
| `ModuleNotFoundError: exportanalysis` | Falta `pip install -e .` o falta `PYTHONPATH=src`. `npm run setup` lo resuelve. |
| El grafico no aparece | Chart.js se carga por CDN: sin conexion a internet el `<script>` falla. Ver la nota de Chart.js arriba. |
| La pagina sale sin estilos | Falta `npm install`, o estas viendo `/` sin haber corrido `npm run build` y sin el fallback. Revisa que `frontend/css/app.css` exista. |
| El backend tarda en el primer request | Normal la primera vez: lee y normaliza los Excel de Trade Map. Despues el sistema operativo los tiene en cache. |
| `Sin datos de comercio para este producto` | Falta el Excel del producto o el HS-6 no coincide con la carpeta. Verifica los nombres en `data/<hs6> <nombre>/`. |

---

## Avisos honestos

- El `share` de competidores se calcula sobre el subconjunto de paises que
  reportan en el ano, no sobre el mercado mundial completo. El reporte emite un
  aviso cuando la cobertura es parcial.
- El headroom es una cota superior teorica: asume que el crecimiento se le
  quita a los exportadores actuales. No modela demanda incremental, barreras de
  entrada ni reaccion de la competencia.
- La curva de aprendizaje esta indexada al ano, no a la produccion acumulada.
  Si tienes volumen historico, reescribir esa funcion vale la pena: es una de
  las palancas mas fuertes del modelo.
- El precio FOB que entra al modelo es el unit value promedio ponderado del
  ultimo ano con cantidad disponible (2025). Es un promedio de todo lo
  exportado, no el precio de tu calidad ni de tu cliente. Se puede sobrescribir
  con el parametro `price_usd_per_kg`.
- La aplicacion no predice. Traduce supuestos a flujos de caja y te dice que
  valor tienen. Si el resultado es negativo, no dice "no inviertas": dice "con
  estos supuestos no se justifica". Cambiar supuestos y volver a correr es el
  uso correcto.
