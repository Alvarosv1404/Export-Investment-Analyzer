/**
 * Graficos del reporte.
 *
 * Chart.js se carga desde CDN en index.html, no como dependencia de npm. Es
 * una libreria de 200 KB que no se versiona con el proyecto y cuya API es
 * estable; meterla al bundle anade un paso de build y un lockfile por un
 * beneficio que no se necesita en un reporte interno.
 *
 * Si el reporte se va a usar sin conexion, lo correcto es copiarla a
 * frontend/vendor/chart.umd.min.js y cambiar el <script> por una ruta local.
 */

import { compactUSD, fullUSD } from './format.js'

const money = fullUSD
const compact = compactUSD

function init() {
  if (typeof Chart === 'undefined') {
    console.warn('[charts] Chart.js no cargo; los graficos quedan vacios.')
    return false
  }
  Chart.defaults.font.family = 'system-ui, sans-serif'
  Chart.defaults.color = '#7d8a6b'
  return true
}

export function destroyCharts() {
  if (typeof Chart === 'undefined') return
  Object.values(Chart.instances).forEach((chart) => chart.destroy())
  if (Chart.instances && typeof Chart.instances.clear === 'function') Chart.instances.clear()
}

/** Serie anual: valor FOB en el eje izquierdo, volumen en el derecho. */
export function series(canvas, m) {
  if (!canvas || !m?.series?.length) return
  new Chart(canvas, {
    type: 'line',
    data: {
      labels: m.series.map((r) => r.year),
      datasets: [
        {
          label: 'Valor FOB',
          data: m.series.map((r) => r.fob_usd),
          borderColor: '#3a7d44',
          backgroundColor: 'rgba(58,125,68,.10)',
          fill: true,
          tension: 0.25,
          yAxisID: 'y',
        },
        {
          label: 'Volumen (kg)',
          data: m.series.map((r) => r.volume_kg),
          borderColor: '#2f8f4e',
          tension: 0.25,
          yAxisID: 'y1',
        },
      ],
    },
    options: {
      plugins: {
        legend: { position: 'bottom' },
        tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${c.parsed.y.toLocaleString('es-PE')}` } },
      },
      scales: {
        y: { position: 'left', ticks: { callback: compact }, title: { display: true, text: 'Valor FOB (USD)' } },
        y1: {
          position: 'right',
          grid: { drawOnChartArea: false },
          ticks: { callback: (v) => `${(v / 1e6).toFixed(0)} M kg` },
          title: { display: true, text: 'Volumen (millones de kg)' },
        },
      },
    },
  })
}

/** Destinos: barra horizontal, los 12 mas grandes. */
export function destinations(canvas, rows) {
  if (!canvas || !rows?.length) return
  const top = rows.slice(0, 12)
  new Chart(canvas, {
    type: 'bar',
    data: {
      labels: top.map((d) => d.partner_name),
      datasets: [{ label: 'Exportaciones FOB', data: top.map((d) => d.fob_usd), backgroundColor: '#7a5c3e' }],
    },
    options: {
      indexAxis: 'y',
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => money(c.parsed.x) } } },
      scales: { x: { ticks: { callback: compact } } },
    },
  })
}

/** Competencia: share por pais, Peru resaltado. */
export function competitors(canvas, c) {
  if (!canvas || !c?.available) return
  new Chart(canvas, {
    type: 'bar',
    data: {
      labels: c.rankings.map((r) => r.country),
      datasets: [
        {
          label: 'Share de mercado',
          data: c.rankings.map((r) => r.share * 100),
          backgroundColor: c.rankings.map((r) => (r.is_origin_country ? '#c0422a' : '#7d8a6b')),
        },
      ],
    },
    options: {
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (x) => `${x.parsed.y.toFixed(1)}%` } } },
      scales: { y: { ticks: { callback: (v) => `${v}%` } } },
    },
  })
}

/** Escalera de headroom: facturacion adicional por share objetivo. */
export function headroom(canvas, h) {
  if (!canvas || !h?.available) return
  new Chart(canvas, {
    type: 'bar',
    data: {
      labels: h.ladder.map((r) => `${(r.target_share * 100).toFixed(1)}%`),
      datasets: [
        { label: 'Facturación adicional', data: h.ladder.map((r) => r.headroom_usd), backgroundColor: '#2f6f9f' },
      ],
    },
    options: {
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => money(c.parsed.y) } } },
      scales: { y: { ticks: { callback: compact } } },
    },
  })
}

/** Flujo de caja libre por anio, verde positivo / rojo negativo. */
export function cashflows(canvas, inv) {
  if (!canvas || !inv?.cashflows) {
    if (canvas) new Chart(canvas, { type: 'line', data: { labels: [], datasets: [] }, options: { plugins: { legend: { display: false } } } })
    return
  }
  const flows = inv.cashflows
  new Chart(canvas, {
    type: 'bar',
    data: {
      labels: flows.map((_, i) => (i === 0 ? 'Inversión' : `Año ${i}`)),
      datasets: [
        {
          label: 'Flujo de caja libre',
          data: flows,
          backgroundColor: flows.map((v) => (v >= 0 ? '#2f8f4e' : '#c0422a')),
        },
      ],
    },
    options: {
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#26301c',
          titleColor: '#faf8ef',
          bodyColor: '#e6e0cc',
          callbacks: { label: (c) => money(c.parsed.y) },
        },
      },
      scales: {
        y: { ticks: { color: '#b9c2a6', callback: compact }, grid: { color: '#3a4630' } },
        x: { ticks: { color: '#b9c2a6' }, grid: { color: '#3a4630' } },
      },
    },
  })
}

/** Tornado: que variable mueve mas el VAN. */
export function tornado(canvas, sens) {
  if (!canvas || !sens?.tornado) {
    if (canvas) new Chart(canvas, { type: 'line', data: { labels: [], datasets: [] }, options: { plugins: { legend: { display: false } } } })
    return
  }
  const t = sens.tornado
  const span = Math.max(
    1,
    ...t.flatMap((row) => [
      Math.abs(row.low_delta_npv_usd),
      Math.abs(row.high_delta_npv_usd),
    ]),
  )
  const zeroGap = span * 0.008
  new Chart(canvas, {
    type: 'bar',
    data: {
      labels: t.map((row) => row.label || row.variable.replaceAll('_', ' ')),
      datasets: [
        {
          label: 'Impacto negativo',
          data: t.map((row) =>
            row.low_delta_npv_usd < -zeroGap ? [row.low_delta_npv_usd, -zeroGap] : null,
          ),
          backgroundColor: '#c0422a',
          borderRadius: 4,
          barThickness: 12,
        },
        {
          label: 'Impacto positivo',
          data: t.map((row) =>
            row.high_delta_npv_usd > zeroGap ? [zeroGap, row.high_delta_npv_usd] : null,
          ),
          backgroundColor: '#2f8f4e',
          borderRadius: 4,
          barThickness: 12,
        },
      ],
    },
    options: {
      indexAxis: 'y',
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#26301c',
          titleColor: '#faf8ef',
          bodyColor: '#e6e0cc',
          callbacks: {
            label: (context) => {
              const row = t[context.dataIndex]
              return [
                `VAN bajo: ${money(row.low_npv_usd)} (${money(row.low_delta_npv_usd)} vs. base)`,
                `VAN alto: ${money(row.high_npv_usd)} (${money(row.high_delta_npv_usd)} vs. base)`,
              ]
            },
          },
        },
      },
      scales: {
        x: {
          min: -span,
          max: span,
          ticks: { color: '#b9c2a6', callback: compact },
          grid: {
            color: (context) => (context.tick.value === 0 ? '#faf8ef' : '#3a4630'),
            lineWidth: (context) => (context.tick.value === 0 ? 2 : 1),
          },
          title: { display: true, text: 'Cambio del VAN frente al caso base (USD)' },
        },
        y: { ticks: { color: '#b9c2a6' }, grid: { display: false } },
      },
    },
  })
}

/** Comparacion entre productos: exportaciones FOB por anio. */
export function comparisonChart(canvas, data) {
  if (!canvas || !data?.products?.length) return
  const prods = data.products.filter((p) => p.available && p.series?.length)
  if (!prods.length) return
  const years = Array.from({ length: 10 }, (_, i) => 2016 + i)
  const colors = ['#3a7d44', '#2f8f4e', '#c0422a', '#7a5c3e', '#c47f17', '#2f6f9f', '#b05c8a', '#8a9a3b']
  const datasets = prods.map((p, i) => ({
    label: p.name || p.slug,
    data: years.map((y) => {
      const row = p.series.find((r) => r.year === y)
      return row ? row.fob_usd : null
    }),
    borderColor: colors[i % colors.length],
    tension: 0.25,
    spanGaps: false,
  }))
  new Chart(canvas, {
    type: 'line',
    data: { labels: years, datasets },
    options: {
      maintainAspectRatio: false,
      plugins: {
        legend: { position: 'bottom' },
        tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${money(c.parsed.y)}` } },
      },
      scales: { y: { ticks: { callback: compact }, title: { display: true, text: 'Exportaciones FOB (USD)' } } },
    },
  })
}

/** Barras: compara el FOB del ultimo ano disponible de cada producto. */
function comparisonLatestChart(canvas, data) {
  if (!canvas || !data?.products?.length) return
  const products = data.products.filter((product) => product.available && product.series?.length)
  if (!products.length) return
  const colors = ['#3a7d44', '#c47f17', '#6b7358', '#2f8f4e', '#7a5c3e', '#d1a52a', '#2f6f9f', '#b05c8a']
  const latest = products.map((product) => {
    const row = product.series.find((year) => year.year === product.latest_year)
    return { product, value: row?.fob_usd ?? null }
  })
  new Chart(canvas, {
    type: 'bar',
    data: {
      labels: latest.map(({ product }) => `${product.name || product.slug} (${product.latest_year})`),
      datasets: [
        {
          label: 'Exportaciones FOB',
          data: latest.map(({ value }) => value),
          backgroundColor: latest.map((_, index) => colors[index % colors.length]),
          borderRadius: 5,
        },
      ],
    },
    options: {
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (context) => money(context.parsed.y) } },
      },
      scales: {
        y: { beginAtZero: true, ticks: { callback: compact }, title: { display: true, text: 'USD FOB' } },
        x: { ticks: { maxRotation: 35, minRotation: 0 } },
      },
    },
  })
}

/** Lineas: crecimiento porcentual de las exportaciones frente al ano anterior. */
function comparisonGrowthChart(canvas, data) {
  if (!canvas || !data?.products?.length) return
  const products = data.products.filter((product) => product.available && product.series?.length)
  if (!products.length) return
  const years = Array.from({ length: 10 }, (_, i) => 2016 + i)
  const colors = ['#3a7d44', '#c47f17', '#6b7358', '#2f8f4e', '#7a5c3e', '#d1a52a', '#2f6f9f', '#b05c8a']
  new Chart(canvas, {
    type: 'line',
    data: {
      labels: years,
      datasets: products.map((product, index) => ({
        label: product.name || product.slug,
        data: years.map((year) => product.series.find((row) => row.year === year)?.value_yoy ?? null),
        borderColor: colors[index % colors.length],
        backgroundColor: colors[index % colors.length],
        pointRadius: 3,
        tension: 0.2,
        spanGaps: false,
      })),
    },
    options: {
      maintainAspectRatio: false,
      plugins: {
        legend: { position: 'bottom' },
        tooltip: { callbacks: { label: (context) => `${context.dataset.label}: ${(context.parsed.y * 100).toFixed(1)}%` } },
      },
      scales: {
        y: { ticks: { callback: (value) => `${(value * 100).toFixed(0)}%` }, title: { display: true, text: 'Variación anual' } },
      },
    },
  })
}

/** Lineas: CAGR acumulado de cada producto desde su anio base. */
function comparisonCagrChart(canvas, data) {
  if (!canvas || !data?.products?.length) return
  const products = data.products.filter((product) => product.available && product.series?.length)
  if (!products.length) return
  const years = Array.from({ length: 10 }, (_, i) => 2016 + i)
  const colors = ['#3a7d44', '#c47f17', '#6b7358', '#2f8f4e', '#7a5c3e', '#d1a52a', '#2f6f9f', '#b05c8a']
  new Chart(canvas, {
    type: 'line',
    data: {
      labels: years,
      datasets: products.map((product, index) => ({
        label: product.name || product.slug,
        data: years.map((year) => {
          if (year <= product.cagr_base_year) return null
          return product.series.find((row) => row.year === year)?.cagr_from_base ?? null
        }),
        borderColor: colors[index % colors.length],
        backgroundColor: colors[index % colors.length],
        pointRadius: 3,
        tension: 0.2,
        spanGaps: false,
      })),
    },
    options: {
      maintainAspectRatio: false,
      plugins: {
        legend: { position: 'bottom' },
        tooltip: { callbacks: { label: (context) => `${context.dataset.label}: ${(context.parsed.y * 100).toFixed(1)}%` } },
      },
      scales: {
        y: { ticks: { callback: (value) => `${(value * 100).toFixed(0)}%` }, title: { display: true, text: 'CAGR desde la base' } },
      },
    },
  })
}

export function renderComparisonCharts(data) {
  if (!init()) return
  comparisonLatestChart(document.getElementById('chartComparisonLatest'), data)
  comparisonChart(document.getElementById('chartComparison'), data)
  comparisonGrowthChart(document.getElementById('chartComparisonGrowth'), data)
  comparisonCagrChart(document.getElementById('chartComparisonCagr'), data)
}

/** Ranking: puntaje ponderado por producto, los mejor rankeados arriba. */
function rankingChart(canvas, data) {
  if (!canvas || !data?.products?.length) return
  const products = data.products.filter((product) => product.score !== null)
  if (!products.length) return
  new Chart(canvas, {
    type: 'bar',
    data: {
      labels: products.map((product) => `${product.name || product.slug} (HS ${product.hs6})`),
      datasets: [
        {
          label: 'Puntaje',
          data: products.map((product) => product.score),
          backgroundColor: products.map((_, index) => (index < 3 ? '#3a7d44' : '#7d8a6b')),
          borderRadius: 5,
        },
      ],
    },
    options: {
      indexAxis: 'y',
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#26301c',
          titleColor: '#faf8ef',
          bodyColor: '#e6e0cc',
          callbacks: {
            label: (context) => {
              const product = products[context.dataIndex]
              return `puntaje ${product.score} / 100 (confianza ${product.score_confidence}%)`
            },
          },
        },
      },
      scales: {
        x: { beginAtZero: true, max: 100, title: { display: true, text: 'Puntaje ponderado (0-100)' } },
      },
    },
  })
}

export function renderRankingChart(data) {
  if (!init()) return
  rankingChart(document.getElementById('chartRanking'), data)
}

/** Precio promedio por kilo SUNAT: FOB / peso neto, linea por anio. */
function sunatPriceChart(canvas, s) {
  if (!canvas || !s?.available || !s.series?.length) return
  const rows = s.series.filter((r) => r.price_usd_per_kg !== null && r.price_usd_per_kg !== undefined)
  if (!rows.length) return
  new Chart(canvas, {
    type: 'line',
    data: {
      labels: rows.map((r) => r.year),
      datasets: [
        {
          label: 'Precio promedio USD/kg',
          data: rows.map((r) => r.price_usd_per_kg),
          borderColor: '#2f6f9f',
          backgroundColor: 'rgba(47,111,159,.14)',
          fill: true,
          tension: 0.25,
        },
      ],
    },
    options: {
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (c) => `$${c.parsed.y.toFixed(3)}/kg` } },
      },
      scales: { y: { title: { display: true, text: 'USD/kg' } } },
    },
  })
}

/** Histograma de distribución de probabilidades de Monte Carlo. */
export function monteCarloChart(canvas, mc) {
  if (!canvas || !mc?.histogram?.length) {
    if (canvas) new Chart(canvas, { type: 'line', data: { labels: [], datasets: [] }, options: { plugins: { legend: { display: false } } } })
    return
  }
  const labels = mc.histogram.map((b) => b.label)
  const data = mc.histogram.map((b) => b.count)
  const colors = mc.histogram.map((b) => (b.is_negative ? 'rgba(192,66,42,0.7)' : 'rgba(47,143,78,0.7)'))
  new Chart(canvas, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        {
          label: 'Frecuencia de simulaciones',
          data,
          backgroundColor: colors,
          borderRadius: 6,
          borderWidth: 1,
          borderColor: '#e6e0cc',
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        title: {
          display: true,
          text: `Distribución de VAN - ${mc.n_simulations?.toLocaleString('es-PE') || ''} simulaciones`,
          font: { size: 13, weight: '600' },
        },
        tooltip: {
          callbacks: {
            label: (c) =>
              `${c.parsed.y} simulaciones (${((c.parsed.y / (mc.n_simulations || 1)) * 100).toFixed(1)}%) - ${c.label}`,
          },
        },
      },
      scales: {
        x: { ticks: { maxRotation: 35, minRotation: 35, font: { size: 10 } }, title: { display: true, text: 'VAN (USD)' } },
        y: { ticks: { }, title: { display: true, text: 'Frecuencia de simulaciones' } },
      },
    },
  })
}

/** Grafico circular (donut) de participacion de mercado de un anio. */
export function shareDonut(canvas, yearData) {
  if (!canvas || !yearData?.slices?.length) return
  const palette = [
    '#3a7d44', '#2f8f4e', '#c47f17', '#7a5c3e', '#2f6f9f',
    '#b05c8a', '#8a9a3b', '#ea580c', '#4f46e5', '#7d8a6b',
  ]
  new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels: yearData.slices.map((s) => s.label),
      datasets: [
        {
          data: yearData.slices.map((s) => +(s.share * 100).toFixed(2)),
          backgroundColor: yearData.slices.map((s, i) => {
            if (s.is_peru) return '#c0422a'
            if (s.is_rest) return '#b9c2a6'
            return palette[i % palette.length]
          }),
          borderColor: '#26301c',
          borderWidth: 2,
        },
      ],
    },
    options: {
      responsive: true,
      cutout: '52%',
      plugins: {
        legend: { position: 'right', labels: { boxWidth: 12, font: { size: 11 } } },
        tooltip: {
          callbacks: {
            label: (c) => {
              const s = yearData.slices[c.dataIndex]
              return `${c.label}: ${c.parsed.toFixed(2)}%  (${compact(s.value_usd)})`
            },
          },
        },
        title: {
          display: true,
          text: `Participación de mercado mundial ${yearData.year}`,
          font: { size: 13, weight: '600' },
        },
      },
    },
  })
}

/**
 * Serie historica + linea de tendencia + proyeccion a futuro.
 * La proyeccion se dibuja punteada para distinguir "dato" de "estimado": la
 * parte solida es lo que ya ocurrio, la punteada es la extrapolacion del modelo.
 * Soporta metodos: moving_average, linear, quadratic, cagr
 */
export function projectionChart(canvas, proj) {
  if (
    !canvas ||
    !proj?.available ||
    proj.method === 'moving_average' ||
    proj.method === 'media móvil simple'
  ) return

  const isTrend = proj.method === 'linear' || proj.method === 'quadratic'
  const isCagr = proj.method === 'cagr'

  const hist = proj.historical || []
  const trend = proj.trend || []
  const fc = proj.forecast || []

  if (!hist.length && !trend.length && !fc.length) return

  // Labels para el eje X completo (histórico + tendencia + proyección)
  const labels = [...new Set([...hist.map((p) => p.year), ...trend.map((p) => p.year), ...fc.map((p) => p.year)])].sort((a, b) => a - b)

  // Datos históricos: un valor por cada año en labels (null donde no hay dato)
  let histData = labels.map((year) => {
    const h = hist.find((p) => p.year === year)
    return h ? h.value : null
  })

  // Tendencia (lineal/cuadrática): valores donde existen, null en el resto
  let trendData = labels.map((year) => {
    const t = trend.find((p) => p.year === year)
    return t ? t.value : null
  })

  // PROYECCIÓN: la calcula el backend en `proj.forecast` (años futuros).
  // Para que la línea punteada sea continua se ancla al último punto de la
  // tendencia ajustada (lineal/cuadrática) o al último dato real (CAGR).
  const lastOf = (points) => (points.length ? points.reduce((a, b) => (b.year > a.year ? b : a)) : null)
  const anchor = isTrend ? lastOf(trend) : lastOf(hist)
  const forecastPoints = fc.length ? (anchor ? [anchor, ...fc] : fc) : []
  const forecastData = labels.map((year) => {
    const point = forecastPoints.find((p) => p.year === year)
    return point ? point.value : null
  })

  // Etiquetas y colores segun metodo
  let trendLabel = 'Tendencia'
  let trendColor = '#c47f17'
  let titleText = 'Proyección FOB'
  let subtitleText = ''

  if (isTrend) {
    const degreeLabel = proj.degree === 1 ? 'lineal' : 'cuadrática'
    trendLabel = `Tendencia ${degreeLabel} (R² = ${proj.r_squared ?? 'n/d'})`
    titleText = `Proyección FOB por tendencia ${degreeLabel}`
    if (proj.equation) subtitleText = `Ecuación: ${proj.equation}`
  } else if (isCagr) {
    trendLabel = `CAGR ${proj.cagr_pct ? proj.cagr_pct + '%' : 'histórico'}`
    titleText = `Proyección FOB por CAGR histórico`
    subtitleText = `Basado en últimos años disponibles`
  }

  const datasets = [
    {
      label: 'Exportación FOB (dato)',
      data: histData,
      borderColor: '#3a7d44',
      backgroundColor: 'rgba(58,125,68,.10)',
      fill: true,
      tension: 0.25,
      spanGaps: true,
    },
  ]

  if (isTrend && trendData.some(v => v !== null)) {
    datasets.push({
      label: trendLabel,
      data: trendData,
      borderColor: trendColor,
      borderWidth: 2,
      pointRadius: 0,
      tension: 0.3,
      spanGaps: true,
    })
  }

  if (forecastData.some(v => v !== null)) {
    datasets.push({
      label: 'Proyección',
      data: forecastData,
      borderColor: '#c47f17',
      borderDash: [6, 5],
      borderWidth: 2,
      pointRadius: 3,
      pointStyle: 'rectRot',
      tension: 0.3,
      fill: false,
      spanGaps: true,
    })
  }

  new Chart(canvas, {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } },
        title: {
          display: true,
          text: titleText,
          font: { size: 13, weight: '600' },
        },
        subtitle: subtitleText ? {
          display: true,
          text: subtitleText,
          font: { size: 11, style: 'italic' },
          color: '#5d6a4c',
          padding: { bottom: 6 },
        } : { display: false },
        tooltip: {
          callbacks: {
            label: (c) => (c.parsed.y == null ? null : `${c.dataset.label}: ${compact(c.parsed.y)}`),
          },
        },
      },
      scales: {
        y: { ticks: { callback: compact }, title: { display: true, text: 'FOB (USD)' } },
      },
    },
  })
}

/** Dibuja todos los graficos del reporte. Idempotente por id de canvas. */
export function renderAll(result) {
  if (!init() || !result) return
  const get = (id) => document.getElementById(id)
  series(get('chartSeries'), result.market)
  sunatPriceChart(get('chartSunatPrice'), result.sunat)
  destinations(get('chartDest'), result.destinations)
  competitors(get('chartComp'), result.competitors)
  headroom(get('chartLadder'), result.headroom)
  cashflows(get('chartCash'), result.investment)
  tornado(get('chartSens'), result.investment?.sensitivity)
  monteCarloChart(get('chartMonteCarlo'), result.investment?.monte_carlo)
  const donutYear = window.__shareYear || result.share_by_year?.years?.slice(-1)[0]
  const yearData = result.share_by_year?.by_year?.find((y) => y.year === donutYear)
  shareDonut(get('chartShare'), yearData)
  projectionChart(get('chartProjection'), result.projection)
}

const SCENARIO_COLORS = { pessimistic: '#c0422a', base: '#2f6f9f', optimistic: '#2f8f4e' }

export function scenarioChart(canvas, investment) {
  if (!canvas) return
  Chart.getChart(canvas)?.destroy()
  const items = investment?.scenarios?.items
  if (!items || !items.length) return
  new Chart(canvas, {
    type: 'bar',
    data: {
      labels: items.map((item) => item.label),
      datasets: [
        {
          label: 'VAN (US$)',
          data: items.map((item) => item.npv_usd),
          backgroundColor: items.map((item) => SCENARIO_COLORS[item.key] || '#6b7358'),
        },
      ],
    },
    options: {
      plugins: { legend: { display: false } },
      scales: {
        y: { ticks: { color: '#b9c2a6', callback: compact }, grid: { color: '#3a4630' } },
        x: { ticks: { color: '#b9c2a6' }, grid: { color: '#3a4630' } },
      },
    },
  })
}

export function renderFinancialCharts(investment) {
  if (!init()) return
  const cashCanvas = document.getElementById('chartCash')
  const sensitivityCanvas = document.getElementById('chartSens')
  const monteCarloCanvas = document.getElementById('chartMonteCarlo')
  const scenarioCanvas = document.getElementById('chartScenario')
  if (cashCanvas) Chart.getChart(cashCanvas)?.destroy()
  if (sensitivityCanvas) Chart.getChart(sensitivityCanvas)?.destroy()
  if (monteCarloCanvas) Chart.getChart(monteCarloCanvas)?.destroy()
  if (scenarioCanvas) Chart.getChart(scenarioCanvas)?.destroy()
  cashflows(cashCanvas, investment)
  tornado(sensitivityCanvas, investment?.sensitivity)
  monteCarloChart(monteCarloCanvas, investment?.monte_carlo)
  scenarioChart(scenarioCanvas, investment)
}
