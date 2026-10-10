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
  Chart.defaults.color = '#555'
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
          ticks: { callback: (v) => `${(v / 1e6).toFixed(0)}M kg` },
          title: { display: true, text: 'Volumen' },
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
        { label: 'Facturacion adicional', data: h.ladder.map((r) => r.headroom_usd), backgroundColor: '#0891b2' },
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
  if (!canvas || !inv?.cashflows) return
  const flows = inv.cashflows
  new Chart(canvas, {
    type: 'bar',
    data: {
      labels: flows.map((_, i) => (i === 0 ? 'Inversion' : `Ano ${i}`)),
      datasets: [
        {
          label: 'Flujo de caja libre',
          data: flows,
          backgroundColor: flows.map((v) => (v >= 0 ? '#059669' : '#dc2626')),
        },
      ],
    },
    options: {
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => money(c.parsed.y) } } },
      scales: { y: { ticks: { callback: compact } } },
    },
  })
}

/** Tornado: que variable mueve mas el VAN. */
export function tornado(canvas, sens) {
  if (!canvas || !sens?.tornado) return
  const t = sens.tornado
  new Chart(canvas, {
    type: 'bar',
    data: {
      labels: t.map((x) => x.variable),
      datasets: [
        {
          label: 'Impacto en VAN',
          data: t.map((x) => x.swing_usd),
          backgroundColor: t.map((x) => (x.swing_usd > 0 ? '#f59e0b' : '#64748b')),
        },
      ],
    },
    options: {
      indexAxis: 'y',
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => `swing ${money(c.parsed.x)}` } } },
      scales: { x: { ticks: { callback: compact } } },
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
        y: { ticks: { callback: (value) => `${(value * 100).toFixed(0)}%` }, title: { display: true, text: 'Variacion anual' } },
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
}
