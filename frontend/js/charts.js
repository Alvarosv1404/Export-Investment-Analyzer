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
  Chart.defaults.color = '#94a3b8'
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
          borderColor: '#2563eb',
          backgroundColor: 'rgba(37,99,235,.08)',
          fill: true,
          tension: 0.25,
          yAxisID: 'y',
        },
        {
          label: 'Volumen (kg)',
          data: m.series.map((r) => r.volume_kg),
          borderColor: '#059669',
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
      datasets: [{ label: 'Exportaciones FOB', data: top.map((d) => d.fob_usd), backgroundColor: '#7c3aed' }],
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
          backgroundColor: c.rankings.map((r) => (r.is_origin_country ? '#dc2626' : '#94a3b8')),
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
        { label: 'Facturación adicional', data: h.ladder.map((r) => r.headroom_usd), backgroundColor: '#0891b2' },
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
          backgroundColor: flows.map((v) => (v >= 0 ? '#059669' : '#dc2626')),
        },
      ],
    },
    options: {
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#0f172a',
          titleColor: '#f8fafc',
          bodyColor: '#e2e8f0',
          callbacks: { label: (c) => money(c.parsed.y) },
        },
      },
      scales: {
        y: { ticks: { color: '#cbd5e1', callback: compact }, grid: { color: '#334155' } },
        x: { ticks: { color: '#cbd5e1' }, grid: { color: '#334155' } },
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
          backgroundColor: '#ef4444',
          borderRadius: 4,
          barThickness: 12,
        },
        {
          label: 'Impacto positivo',
          data: t.map((row) =>
            row.high_delta_npv_usd > zeroGap ? [zeroGap, row.high_delta_npv_usd] : null,
          ),
          backgroundColor: '#10b981',
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
          backgroundColor: '#0f172a',
          titleColor: '#f8fafc',
          bodyColor: '#e2e8f0',
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
          ticks: { color: '#cbd5e1', callback: compact },
          grid: {
            color: (context) => (context.tick.value === 0 ? '#f8fafc' : '#334155'),
            lineWidth: (context) => (context.tick.value === 0 ? 2 : 1),
          },
          title: { display: true, text: 'Cambio del VAN frente al caso base (USD)' },
        },
        y: { ticks: { color: '#cbd5e1' }, grid: { display: false } },
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
  const colors = ['#2563eb', '#059669', '#dc2626', '#7c3aed', '#f59e0b', '#0891b2', '#db2777', '#65a30d']
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
  const colors = ['#2563eb', '#f97316', '#64748b', '#059669', '#7c3aed', '#eab308', '#0891b2', '#db2777']
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
  const colors = ['#2563eb', '#f97316', '#64748b', '#059669', '#7c3aed', '#eab308', '#0891b2', '#db2777']
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
  const colors = ['#2563eb', '#f97316', '#64748b', '#059669', '#7c3aed', '#eab308', '#0891b2', '#db2777']
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
          backgroundColor: products.map((_, index) => (index < 3 ? '#2563eb' : '#94a3b8')),
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
          backgroundColor: '#0f172a',
          titleColor: '#f8fafc',
          bodyColor: '#e2e8f0',
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
          borderColor: '#0d9488',
          backgroundColor: 'rgba(13,148,136,.12)',
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
  const colors = mc.histogram.map((b) => (b.is_negative ? 'rgba(239, 68, 68, 0.7)' : 'rgba(16, 185, 129, 0.7)'))
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
          borderColor: '#e2e8f0',
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
    '#2563eb', '#059669', '#d97706', '#7c3aed', '#0891b2',
    '#db2777', '#65a30d', '#ea580c', '#4f46e5', '#94a3b8',
  ]
  new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels: yearData.slices.map((s) => s.label),
      datasets: [
        {
          data: yearData.slices.map((s) => +(s.share * 100).toFixed(2)),
          backgroundColor: yearData.slices.map((s, i) => {
            if (s.is_peru) return '#dc2626'
            if (s.is_rest) return '#cbd5e1'
            return palette[i % palette.length]
          }),
          borderColor: '#1e293b',
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

  // Labels para el eje X completo (2016-2027) para todas las series
  const labels = [...new Set([...hist.map((p) => p.year), ...trend.map((p) => p.year), ...fc.map((p) => p.year)])].sort((a, b) => a - b)

  // Datos históricos: un valor por cada año en labels (2016-2027)
  let histData = labels.map((year) => {
    const h = hist.find((p) => p.year === year)
    return h ? h.value : null
  })

  // Tendencia (lineal/cuadrática): valores donde existen, null en el resto
  let trendData = labels.map((year) => {
    const t = trend.find((p) => p.year === year)
    return t ? t.value : null
  })

  // PROYECCIÓN: Array alineado con labels (2016-2027)
  // Solo 2025, 2026, 2027 tienen valores; resto null
  let forecastData = labels.map(() => null)

  // Índices fijos para 2025, 2026, 2027
  const year2025Idx = labels.indexOf(2025)
  const year2026Idx = labels.indexOf(2026)
  const year2027Idx = labels.indexOf(2027)

  // PROYECCIÓN: Calcular correctamente según el método
  // ------------------------------------------------------------
  // Tendencia lineal/cuadrática: extender la curva ajustada (trend)
  // CAGR: crecimiento compuesto hacia adelante
  // ------------------------------------------------------------

  let projValue2025 = null
  let projValue2026 = null
  let projValue2027 = null

  if (isTrend) {
    // TENDENCIA LINEAL/CUADRÁTICA: Usar valores de la tendencia ajustada
    const trend2025 = trend.find((p) => p.year === 2025)
    const trend2026 = trend.find((p) => p.year === 2026)
    const trend2027 = trend.find((p) => p.year === 2027)
    projValue2025 = trend2025 ? trend2025.value : null
    projValue2026 = trend2026 ? trend2026.value : null
    projValue2027 = trend2027 ? trend2027.value : null
    // Fallback a fc si no hay trend para 2026/2027
    if (projValue2026 === null) {
      const f2026 = fc.find((p) => p.year === 2026)
      projValue2026 = f2026 ? f2026.value : null
    }
    if (projValue2027 === null) {
      const f2027 = fc.find((p) => p.year === 2027)
      projValue2027 = f2027 ? f2027.value : null
    }
  } else if (isCagr) {
    // CAGR: Crecer al ritmo del CAGR histórico
    // Usar el ÚLTIMO VALOR HISTÓRICO REAL (hist) como base, no la tendencia
    const hist2025 = hist.find((p) => p.year === 2025)
    const baseValue = hist2025 ? hist2025.value : null
    const cagr = proj.cagr_pct ? proj.cagr_pct / 100 : 0
    if (baseValue !== null && cagr > 0) {
      projValue2025 = baseValue
      projValue2026 = baseValue * (1 + cagr)
      projValue2027 = baseValue * Math.pow(1 + cagr, 2)
    }
  } else {
    // Fallback: usar fc (forecast del backend)
    const f2025 = fc.find((p) => p.year === 2025)
    const f2026 = fc.find((p) => p.year === 2026)
    const f2027 = fc.find((p) => p.year === 2027)
    projValue2025 = f2025 ? f2025.value : null
    projValue2026 = f2026 ? f2026.value : null
    projValue2027 = f2027 ? f2027.value : null
  }

  // Asignar valores calculados al array forecastData
  if (year2025Idx >= 0 && projValue2025 !== null) forecastData[year2025Idx] = projValue2025
  if (year2026Idx >= 0 && projValue2026 !== null) forecastData[year2026Idx] = projValue2026
  if (year2027Idx >= 0 && projValue2027 !== null) forecastData[year2027Idx] = projValue2027

  // forecastData ya está alineado con labels (2016-2027), solo 2025-2027 tienen valores

  // Etiquetas y colores segun metodo
  let trendLabel = 'Tendencia'
  let trendColor = '#d97706'
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
      borderColor: '#2563eb',
      backgroundColor: 'rgba(37,99,235,.08)',
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
      borderColor: '#f97316',
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
          color: '#475569',
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

export function scenarioChart(canvas) {
  if (!canvas) return
  Chart.getChart(canvas)?.destroy()
  new Chart(canvas, {
    type: 'bar',
    data: {
      labels: ['Pesimista', 'Base', 'Optimista'],
      datasets: [
        {
          label: 'VAN (US$)',
          data: [-1490825, 11201, 1391389],
          backgroundColor: ['#dc2626', '#0284c7', '#059669'],
        },
      ],
    },
    options: {
      plugins: { legend: { display: false } },
      scales: {
        y: { ticks: { color: '#cbd5e1', callback: compact }, grid: { color: '#334155' } },
        x: { ticks: { color: '#cbd5e1' }, grid: { color: '#334155' } },
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
  scenarioChart(scenarioCanvas)
}
