# Export Investment Analyzer

Motor de analisis para evaluar inversiones en exportacion: mercado, competencia
y viabilidad financiera (VAN/TIR) con datos publicos. El catalogo inicial cubre
agroexportacion y pesca peruana.

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

## Catalogo actual

15 productos. **Toda la informacion sale de `data/`**: cada producto existe
porque tiene su carpeta con los Excel, y de ahi salen las cifras, el HS6, la
industria, la partida y hasta el nombre. `config/products.yaml` no es una fuente
de datos: es una capa opcional de curaduria que solo cambia como se muestra el
producto (nombre presentable y presentaciones). No tiene una sola cifra.

| Producto | Slug (URL) | HS6 | Industria | Ficha curada |
|---|---|---|---|---|
| Café verde | `cafe_verde` | 090111 | Agricola | si |
| Cacao | `cacao_en_grano` | 180100 | Agricola | si |
| Arandano | `arandano` | 081040 | Agricola | si |
| Uva | `uva_fresca` | 080610 | Agricola | si |
| Palta | `palta_fresca` | 080440 | Agricola | si |
| Esparrago | `esparrago_fresco` | 070920 | Agricola | si |
| Mango | `mango_fresco` | 080450 | Agricola | si |
| Quinua | `quinua` | 100850 | Agricola | si |
| Aji y paprika | `aji_paprika` | 090421 | Agricola | si |
| Jengibre | `jengibre` | 091011 | Agricola | si |
| Pota y calamar | `pota_calamar` | 030743 | Pesquero | si |
| Conservas de pescado | `conservas_pescado` | 160414 | Pesquero | si |
| Naranja fresca | `naranja_fresca` | 080510 | Agricola | no (nombre de carpeta) |
| Aceite de pescado crudo | `aceite_de_pescado_crudo` | 150420 | Agroindustria | no (nombre de carpeta) |
| Alcachofas en conserva | `alcachofas_en_conserva` | 200599 | Agroindustria | no (nombre de carpeta) |

> Los tres sin ficha se llaman asi por su carpeta y no tienen supuestos en
> `assumptions.yaml`: el reporte muestra su mercado avisando que faltan
> supuestos de inversion, en vez de inventar un VAN. La ficha curada no cambia
> ninguna cifra: solo pone un nombre presentable y las presentaciones
> (variantes). Al reves tambien vale: declarar un producto en `products.yaml`
> sin su carpeta en `data/` lo agrega al catalogo, pero no hay nada que
> analizar y el reporte falla por falta de data. El HS6 manda: `200599` es un
> codigo mas ancho que "alcachofas en conserva" (ver "Avisos honestos").

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
| `npm run preview` | Sirve `dist/` localmente, para revisar el build sin la API de Vite |
| `npm run setup` | Instala dependencias y crea la plantilla |

## Endpoints

| Ruta | Que hace |
|---|---|
| `GET /` | Reporte completo con los bloques del analisis y graficos |
| `GET /api/products` | Catalogo de productos configurados, cada uno con sus `assumptions` para precargar el simulador |
| `GET /api/analysis/{slug}` | Analisis completo en JSON |
| `GET /api/analysis/{slug}?target_share=0.12` | Con participacion de mercado objetivo explicita |
| `GET /api/analysis/{slug}?price_usd_per_kg=6.5` | Con precio FOB de venta explicito |
| `GET /api/comparison?slugs=cafe_verde,uva_fresca` | Comparacion seleccionada con serie 2016-2025, variacion anual y CAGR desde 2016 |
| `GET /api/ranking?slugs=cafe_verde,uva_fresca` | Screener: ordena los productos por puntaje ponderado (pesos en `config/scoring.yaml`). Sin `slugs`, rankea el catalogo completo |
| `GET /api/analysis/{slug}/export/excel` | Dossier Ejecutivo en Excel (`.xlsx`); acepta los mismos supuestos que el analisis |
| `GET /health` | Sonda de salud |
| `GET /docs` | Swagger UI interactivo |

La interfaz separa **Analisis por producto** de **Comparacion de productos**.
En la segunda vista puedes elegir uno o mas productos; la seleccion se conserva
en la URL. Incluye graficas de FOB del ultimo ano disponible, evolucion de
exportaciones y crecimiento interanual, junto con tablas anuales y CAGR
2016-2025. Son exportaciones FOB del Peru reportadas en Trade Map, no valores
importados de los mercados destino. Si el Excel no contiene un dato anual, se
muestra como `n/d` y no se interpreta como cero.

Esa misma vista trae el **ranking de productos** ("¿por cual de estos
empezar?"): ordena los productos marcados por un puntaje ponderado
(`config/scoring.yaml`) que usa solo datos historicos publicados -tamano de
mercado, crecimiento, diversidad de destinos y estabilidad exportadora-, sin
supuestos de inversion. Cada fila muestra ademas la cobertura de fuentes
(cuantos Excel de Trade Map tiene y si tiene el de SUNAT). El analisis de cada
producto tiene un boton para descargar el **Dossier Ejecutivo en Excel**.

## Correr sin navegador

```bash
python scripts/smoke_test.py cafe_verde
```

Imprime el mismo analisis en texto. Util para revisar cambios rapido o para
correrlo en un cron y comparar contra el run anterior.

---

## Produccion

`npm run build` emite `dist/` con rutas relativas, y FastAPI lo sirve
automaticamente. El mismo build funciona servido por FastAPI, por nginx o por
un CDN sin reconfiguracion.

Sin `dist/` no hay interfaz: la raiz (`/`) responde **503** con un mensaje que
pide correr `npm run build`. La API JSON (`/api/...`) funciona igual sin build.

### Desplegar en Netlify (UI) + Render (API)

Netlify sirve solo estaticos y **no puede correr Python**, y todo el analisis
sale de la API. Por eso el despliegue son dos piezas enlazadas por un proxy.

1. **API en Render.** Crea un *Web Service* desde el repositorio. El
   `render.yaml` ya lo define todo (`runtime: python`, `plan: free`,
   `pip install -e . -c constraints.txt`, `uvicorn`). Al terminar copia su URL
   (`https://algo.onrender.com`) y comprueba que responde en `/health`.
   El plan gratis duerme tras ~15 min de inactividad: la primera peticion tarda
   ~30-60 s en despertarla, asi que visitá la URL antes de entrar a Netlify.

   Render no usa Docker, pero instala exactamente lo mismo: Python `3.12.15`
   (el `PYTHON_VERSION` del blueprint, igual que la imagen `python:3.12.15-slim`)
   y el mismo `constraints.txt`. Asi un cambio de version no puede hacer que la
   API de Render y la de Docker respondan distinto.

2. **UI en Netlify.** Sitio nuevo conectado al mismo repositorio. Netlify lee
   `netlify.toml` (build `npm ci && npm run build:netlify`, publica `dist`).
   En *Site configuration -> Environment variables* define:

   ```
   API_URL = https://algo.onrender.com
   ```

   El build genera `dist/_redirects`, que manda `/api/*` y `/health` a esa URL.
   El navegador ve un solo origen: sin CORS y sin URLs hardcodeadas (si cambias
   de backend, solo cambia la variable).

3. Despliega. La UI queda en `https://algo.netlify.app` y los datos los sirve
   la API de Render a traves del proxy.

Sin Netlify tambien funciona en un solo servicio, y para eso el repo trae
`Dockerfile`: Node compila la UI y Python sirve UI + API con la misma URL (ver
*Docker*, abajo). En Render alcanza con elegir *Deploy from Dockerfile*.

### Docker (UI + API en un solo contenedor)

```bash
docker build -t export-investment-analyzer:latest .
docker run --rm -p 8000:8000 export-investment-analyzer:latest
```

Queda en `http://localhost:8000`. Respeta `PORT`:
`docker run --rm -e PORT=9000 -p 9000:9000 ...`.

El build es reproducible:

- `python:3.12.15-slim` y `node:22.23.4-alpine`, con tag de parche exacto (no
  `3.12-slim`/`22-alpine` a secas, que cambian con el tiempo).
- `npm ci`, que respeta `package-lock.json`.
- `constraints.txt`, con las versiones de Python que se validaron (154 tests y
  los 15 productos). Sin el, `pandas>=2.2` resolvia a cualquier version nueva:
  un build trajo pandas 3.1 y rompio la API.

Para actualizar el lock:

```bash
docker run --rm export-investment-analyzer:latest python -m pip freeze
```

y reemplazar la lista de `constraints.txt` (sin la linea del paquete editable).

El proceso corre como usuario sin privilegios (`appuser`, uid 10001) y el
`HEALTHCHECK` pega en `/health`.

> `constraints.txt` es solo para Docker: tu Python local puede ser mas nuevo y no
> tener wheels de esas versiones exactas. Para desarrollo usa `pip install -e
> ".[dev]"` como siempre.

### Desplegar en Fly.io (misma imagen Docker)

La app esta publicada en **https://export-investment-analyzer-peru.fly.dev**
(region `gru`, 512 MB, una maquina que se apaga sola sin trafico).

`fly.toml` describe el servicio: construye con el `Dockerfile` del repo,
enruta el puerto `8000` (el mismo del `EXPOSE` y del `CMD`) y usa `/health`
como chequeo. La app no necesita base de datos, disco ni variables de entorno.

```bash
fly deploy --remote-only    # compila en la nube y crea/actualiza la maquina
fly status                  # estado y resultado del chequeo
fly logs                    # logs en vivo
```

Detalles utiles:

- **Region.** `gru` (Sao Paulo) es la mas cercana a Peru que ofrece Fly; no
  existen `bog` ni `mia`. Otras opciones: `iad`, `ewr`, `dfw`, `lax`, `sjc`.
  Cambiar con `fly regions set <codigo> --app export-investment-analyzer-peru`.
- **Memoria.** 512 MB porque el pico medido sirviendo los 15 productos fue
  136 MiB y pandas/pyarrow piden mas al parsear un Excel grande; con 256 MB la
  maquina puede morir por OOM.
- **Costo.** `auto_stop_machines = 'stop'` y `min_machines_running = 0` apagan la
  maquina sin trafico; la primera peticion despues de un rato tarda ~4-10 s en
  arrancar. Para tenerla siempre encendida, cambiar esos dos valores en
  `fly.toml` y volver a desplegar.
- **Una sola maquina.** `fly scale count 1` (Fly crea dos por defecto para alta
  disponibilidad; para una demo la segunda solo duplica el gasto).

---

## Agregar un producto

Hay dos caminos.

**El mas simple: solo data.** Deja la carpeta del producto en
`data/<hs6> <nombre>/` con sus cuatro Excel de Trade Map. El producto aparece
solo en el catalogo: el HS6 sale del nombre de la carpeta o de los archivos. Ver
`data/README.md`.

**Si quieres curarlo** (nombre, presentaciones, industria), agregalo como un item
de la lista `products:` en `config/products.yaml`:

```yaml
products:
  - slug: cacao_en_grano
    name: "Cacao en grano"
    hs6: "180100"          # HS-6: la unidad de analisis
    nandina: "1801001900"  # partida SUNAT de 10 digitos, para el arancel
    unit: "kg"
    industry: Agricola
    presentations:
      - {hs6: "180100", label: "Grano entero o partido, crudo"}
```

No declares competidores: se derivan de `exporting-economies_<hs6>.xlsx` (los
mayores exportadores del ultimo anio). El campo `competitors` existe como escape
hatch, pero el default es la data.

Y sus supuestos en `config/assumptions.yaml` (este si es un diccionario por
slug):

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

Opcionales, con la misma forma (una columna por ano + `<ano>_unit`):

| Archivo | Que aporta | Unidad |
|---|---|---|
| `kg_importing-economies_<hs6>.xlsx` | Cantidades importadas por pais y ano: la demanda mundial que proyecta el modelo | Tons/kg |
| `kg_exporting-economies_<hs6>.xlsx` | Cantidades exportadas por pais y ano: el volumen y el precio unitario de cada competidor | Tons/kg |

Opcional, con otra forma, para el bloque SUNAT:

| Archivo | Que aporta | Unidad |
|---|---|---|
| `<nandina>.xlsx` | Exportaciones SUNAT por destino, **una hoja por ano** (hojas llamadas `2024`, `2025`, ...). Trae el peso neto real, asi que da el precio por kilo mas confiable. El nombre es la partida NANDINA de 10 digitos (p. ej. `0901119000.xlsx`) | USD, kg |

Se buscan las hojas cuyo nombre son 4 digitos (el ano) y dentro las columnas
`Pais de Destino`, `Valor FOB(dolares)` y `Peso Neto(Kilos)`, ubicadas por
nombre y no por orden. Si el archivo no esta, el bloque SUNAT del reporte queda
como no disponible; no se rellena con cero. Su presencia es el chip `SUNAT` del
ranking.

Como se leen:

- `reporterCd` / `partnerCd` son codigos **M49** (`config/countries.yaml`);
  `604` es Peru. En estos archivos el partner es siempre World (`partnerCd = 0`)
  y la fila `reporterCd = 0` es el **total agregado** "World", no un pais.
- El valor se convierte a USD (los archivos vienen en miles) y la cantidad a
  kilos cuando Trade Map la publica en toneladas.
- El volumen **historico por destino** solo existe en el snapshot 2025; en los
  demas anos queda `null`, que es un hueco real de la fuente, no un cero. El
  volumen **por competidor** sale del Excel opcional `kg_exporting-economies`;
  sin ese archivo, las columnas de volumen y precio de la tabla de competencia
  quedan `n/d`, no en cero.
- **Los competidores salen de la data, no de una lista escrita a mano.** El
  bloque de competencia compara a Peru contra los mayores exportadores del
  ultimo anio con data, leidos del mismo Excel (`exporting-economies`), sin Peru
  ni la fila "World". No hay que declarar nada: un producto recien agregado ya
  trae competencia. (`products.yaml` todavia acepta un campo `competitors` como
  escape hatch, pero ningun producto lo usa: el default es la data.)
- La fila de total "World" se excluye en **todos** los calculos. Tratarla como un
  pais duplicaba el total mundial y dejaba el share de cada exportador a la mitad
  (un 50% fantasma en el grafico de participacion).
- El precio de venta del modelo sale del valor FOB ponderado por kilo de 2025.
  Se puede sobrescribir con `price_usd_per_kg` y el reporte dice de donde
  salio (`calculado de históricos`, `ajustado por el usuario` o `unit value del
  Excel`).

Para agregar o reemplazar data, copia los cuatro Excel requeridos en la carpeta
del producto con exactamente esos nombres. Los dos opcionales de cantidades se
agregan igual, con sus nombres. Ver `data/README.md`.

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

Hay escenarios piloto de ejemplo para **12 de los 15 productos** en
`config/assumptions.yaml`, para que el reporte y el modelo puedan ejecutarse.
Los tres que no tienen ficha (los `auto` de la tabla de arriba) muestran su
analisis de mercado sin bloque de inversion: la API devuelve `assumptions_missing`
con lo que falta, en vez de inventar un VAN.
Son cifras hipoteticas, no cotizaciones ni datos publicados, y no validan la
rentabilidad. Sustituyelas por cotizaciones de proveedores y costos reales
antes de tomar una decision.

El reporte distingue siempre entre dato y supuesto, y marca de donde salio la
curva de ocupacion de la planta (`ramp_source`).

### Simulador: precarga y rangos por producto

El simulador no arranca con los mismos numeros para todo el catalogo.
`GET /api/products` devuelve, para cada producto **con ficha**, sus **supuestos
efectivos** de `config/assumptions.yaml` (capacidad, CAPEX, costos, OPEX, capital
de trabajo y tasa de descuento). Los tres `auto` devuelven solo la tasa de
descuento por defecto, asi que usan los rangos base (ver abajo). El frontend usa
esos valores para **precargar el volumen, el OPEX, el COK, el CAPEX y el costo
variable** de cada producto.

Cuatro variables usan un **rango fijo** (el ejercicio se evalua dentro de ellos):

| Supuesto | Rango | Unidad |
|---|---|---|
| Volumen del año 1 | 200 - 800 | t |
| Crecimiento del volumen | 10 - 55 | % |
| Costos fijos del año 1 | 200,000 - 600,000 | USD |
| COK / tasa de descuento | 7 - 16 | % |

El **CAPEX** y el **costo variable total** se anclan a la ficha del producto,
porque un rango unico no sirve para todo el catalogo:

| Supuesto | Rango por producto | Valor por defecto |
|---|---|---|
| Inversion inicial (CAPEX) | ficha −40% / +40% | CAPEX de la ficha |
| Costo variable total | ficha (compra + proceso) ±50% | costo de la ficha |

El costo variable del slider es el **costo total por tonelada** (compra +
proceso), en USD/t. Se precarga con la suma de la ficha y el slider deja
moverlo ±50%. Si un producto no tiene ficha, ambos caen al rango base
(CAPEX 1M-3M, costo 4,800-7,800 USD/t).

Los rangos viven en `SIMULATOR_RANGES` (base) y `rangosDe(product)` (por
producto) en `frontend/js/components.js`, y el precargado recorta los defaults a
esos limites con `snapToRange` (`frontend/js/main.js`): asi el numero que usa el
analisis y el que muestra el slider siempre coinciden.

> **Por que el costo no es un rango fijo.** Un piso unico de 4.8 USD/kg dejaba
> fuera a 11 de 15 productos: su FOB de mercado esta por debajo de ese piso, y
> con costo ≥ piso cada kilo pierde dinero, con VAN negativo sin importar el
> volumen ni el crecimiento, aunque el negocio real sea viable. Anclando el
> rango a la ficha, el default refleja el costo real del producto. Si un
> producto no cierra a esos supuestos, el VAN sale negativo igual: es la
> respuesta honesta del modelo, no un error de calculo.

---

## Como esta armado el proyecto

```
config/            productos, supuestos, paises y pesos del ranking (declarativo)
dev.config.json    puertos de desarrollo (fuente unica de verdad)
package.json       scripts npm; los puertos NO se escriben aqui
eslint.config.js   reglas de ESLint 9 para el frontend y los scripts .mjs
vite.config.js     build del frontend + proxy hacia la API
constraints.txt    versiones exactas de Python (build de Docker y de Render)
Dockerfile         build multi-etapa (Node compila, Python sirve UI + API)
fly.toml           deploy en Fly.io (puerto 8000, healthcheck, 512 MB)
render.yaml        API en Render (mismo lock que Docker)
netlify.toml       UI en Netlify (build estatico + proxy de /api)

frontend/          interfaz web (Vite, JavaScript modular, sin framework)
  index.html
  css/app.css      tema "campo": verdes de hoja, tierras y trigo (un solo archivo)
  js/
    main.js        orquestacion; el estado vive en la URL
    api.js         llamadas a /api, sin URLs hardcodeadas
    components.js  los bloques del reporte
    charts.js      graficos con Chart.js
    format.js      formato de moneda, porcentaje y volumen
  public/assets/
    chart.umd.min.js  Chart.js vendorizado (v4.4.3): Vite lo copia a dist/

src/exportanalysis/
  sources/         trademap_excel.py, manual_tariffs.py, sunat.py (scraper retirado, sin uso)
  pipeline/        market.py, competitors.py, excel_analysis.py, analyze.py
  model/           financials.py, valuation.py, unit_economics.py
  api/main.py      FastAPI; sirve el build de Vite y expone la API JSON

scripts/
  setup.mjs        instala dependencias y crea la plantilla
  run-api.mjs      levanta uvicorn en el puerto de dev.config.json
  check-ports.mjs  revisa que los puertos esten libres
  check-api.mjs    verifica el contrato de la API
  tariff_helper.py  que buscar en Trade Map, y escribir el CSV sin editarlo a mano
  smoke_test.py    el analisis completo en texto

tests/             9 archivos: modelo financiero, data, API, comparacion, arancel/precio y screener
```

El circuito que cierra el modelo:

```
Trade Map (Excel local) ─> mercado (volumen, FOB, precio, destinos)
                         ─> competidores (share, ranking, HHI, headroom)
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
- **El frontend no usa framework.** Son bloques fijos y sin estado;
  introducir React seria mas ceremonia que ayuda. El estado vive en la URL, asi
  que cualquier vista es compartible con un link.
- **Chart.js va vendorizado, no por npm.** Es una libreria estable de ~200 KB;
  vive en `frontend/public/assets/chart.umd.min.js` y Vite la copia tal cual a
  `dist/assets/`. No entra al bundle ni sale a internet, asi que la UI funciona
  sin conexion. Para actualizarla, ver el comentario de `frontend/js/charts.js`.

---

## Tests

```bash
npm test                 # verifica la API y luego corre pytest
npm run lint             # ruff + eslint
```

`npm test` es `test:api` + `test:py`, y `npm run lint` es `lint:web` +
`lint:py`: si solo quieres una mitad, corre esa.

O por separado:

```bash
python -m pytest         # 154 tests del modelo, arancel y API
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
| El grafico no aparece | Chart.js no se cargo. Verifica que exista `frontend/public/assets/chart.umd.min.js` y que `dist/assets/` lo tenga: si falta, corre `npm run build`. |
| La pagina sale sin estilos | Falta `npm install` o `npm run build` (la raiz responde 503 sin build). Revisa que `frontend/css/app.css` exista. |
| El backend tarda en el primer request | Normal la primera vez: lee y normaliza los Excel de Trade Map. Despues el sistema operativo los tiene en cache. |
| `Sin datos de comercio para este producto` | Falta el Excel del producto o el HS-6 no coincide con la carpeta. Verifica los nombres en `data/<hs6> <nombre>/`. |

---

## Avisos honestos

- El `share` de competidores se calcula sobre el subconjunto de paises que
  reportan en el ano, no sobre el mercado mundial completo. El reporte emite un
  aviso cuando la cobertura es parcial, y otro cuando no hay con quien comparar
  (un "100%" seria solo Peru, no dominio de mercado).
- El `HHI competidores` mide que tan repartida esta la oferta entre esos paises
  comparados (mismos cortes que el HHI de destinos: <1.500 baja, hasta 2.500
  moderada, >2.500 alta). Es una lectura de la oferta, no del riesgo de clientes.
  Con un solo exportador comparable queda en `n/d`, no en 10.000.
- El conjunto de competidores se deriva de la data (ver "De donde salen los
  datos"): son los mayores exportadores del ultimo anio, no un grupo curado a
  mano. El campo `competitor_source` de la API lo deja explicito.
- **Ese ranking mide valor exportado, e incluye reexportacion.** Trade Map no
  separa produccion propia de reexportacion: paises como Paises Bajos, Belgica o
  Alemania aparecen por su rol de hub. Eso puede mejorar la posicion relativa de
  Peru, porque compite contra un flujo bruto y no contra produccion. Es la data
  tal cual; el modelo no la corrige ni la recorta.
- **El HS6 puede ser mas ancho que el nombre comercial.** El nombre suele venir
  del nombre de la carpeta en `data/`. Ejemplo: `200599` es "las demas hortalizas
  preparadas o conservadas", que incluye bastante mas que "alcachofas en
  conserva". Cuando compares cifras, mira el HS6, no solo el titulo.
- **El puntaje del ranking es relativo a la seleccion.** Cada dimension se
  normaliza 0-100 entre los productos marcados, asi que agregar o quitar uno
  cambia los puntajes (y hasta el orden) aunque los datos no cambien. Sirve para
  comparar un conjunto, no como nota absoluta del producto. Tampoco usa
  supuestos financieros: solo exportaciones historicas publicadas.
- **El headroom es una cota superior teorica:** asume que el crecimiento se le
  quita a los exportadores actuales. No modela demanda incremental, barreras de
  entrada ni reaccion de la competencia.
- **El simulador es un ejercicio acotado, no una prediccion de escala.** El
  volumen se mueve entre 200 y 800 t y los costos fijos entre 200,000 y 600,000
  USD, mientras el CAPEX y el costo variable salen de la ficha del producto. Si
  la planta de la ficha es mucho mas grande que ese volumen, el VAN puede salir
  negativo por **escala** aunque el margen por kilo sea bueno. No es un error de
  calculo: es el tamano del ejercicio. Para evaluar otra escala, cambia el
  volumen o la ficha.
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
