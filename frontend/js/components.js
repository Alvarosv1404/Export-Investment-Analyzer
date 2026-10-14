/**
 * Componentes del reporte.
 *
 * Cada funcion recibe el resultado del analisis y devuelve un string HTML. Se
 * usa render por string en vez de un framework porque son ocho bloques fijos
 * y sin estado: introducir React/Vue para esto seria mas ceremonia que
 * ayuda. El valor esta en que el formateo y la estructura quedan en un solo
 * lugar, en vez de dispersos entre el template y el script.
 *
 * Todos los valores pasan por escapeHTML. Los nombres de pais y las notas
 * vienen de APIs externas, y un nombre con "<" romperia el DOM.
 */

import { getExportUrl } from './api.js'
import { fullUSD, kg, pct, pctSigned, usd, years, verdictClass } from './format.js'

export function escapeHTML(value) {
  if (value === null || value === undefined) return ''
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

const tagData = '<span class="tag tag-data">dato publicado</span>'
const tagAssumed = '<span class="tag tag-assumed">supuesto</span>'

function kpi(label, value, note = '', extraClass = '') {
  return `
    <div class="kpi">
      <span class="kpi-label">${escapeHTML(label)}</span>
      <span class="kpi-value ${extraClass}">${value}</span>
      ${note ? `<span class="kpi-note">${note}</span>` : ''}
    </div>`
}

function table(headers, rows, className = '') {
  return `
    <table class="${escapeHTML(className)}">
      <thead><tr>${headers.map((h) => `<th class="${h.num ? 'num' : ''}">${escapeHTML(h.label)}</th>`).join('')}</tr></thead>
      <tbody>${rows.join('')}</tbody>
    </table>`
}

// --- Bloque 1: economia unitaria -------------------------------------------------
export function unitEconomics(pricing) {
  if (pricing?.price_usd_per_kg == null || !Number.isFinite(pricing.price_usd_per_kg)) return ''
  return `
    <section class="card">
      <h2>Precio FOB de referencia ${tagData}</h2>
      <div class="kpis">
        ${kpi('Precio FOB calculado', usd(pricing.price_usd_per_kg * 1000), 'USD/t')}
      </div>
      <p class="note">Calculado desde los Excel locales: ${escapeHTML(pricing.origin || 'fuente Excel')}.</p>
    </section>`
}

// --- Aviso: producto sin supuestos de inversion ---------------------------------
export function missingAssumptions(result) {
  const missing = result?.assumptions_missing
  if (!missing || !missing.length) return ''
  return `
    <section class="card">
      <h2>Evaluación financiera <span class="tag tag-assumed">pendiente</span></h2>
      <div class="alert warn">
        El análisis de mercado está disponible. Completa los datos del formulario de evaluación
        para calcular VAN, TIR, recuperación y flujo de caja. No se completan automáticamente
        con cifras de ejemplo.
      </div>
      <p class="note">Campos pendientes: ${missing.map((key) => `<code>${escapeHTML(key)}</code>`).join(', ')}.</p>
    </section>`
}

// --- Bloque 2: mercado -----------------------------------------------------------
export function market(m, demand) {
  if (!m || !m.available) {
    return `<section class="card"><div class="alert error">${escapeHTML(m?.message || 'Sin datos de mercado.')}</div></section>`
  }
  return `
    <section class="card">
      <h2>2. Mercado ${tagData}</h2>
      <div class="kpis">
        ${kpi('Exportaciones FOB de Perú', fullUSD(m.latest_fob_usd), String(m.latest_year))}
        ${kpi(`Volumen exportado por Perú (${m.latest_year})`, kg(m.latest_volume_kg), 'peso neto')}
        ${kpi('Precio unitario FOB de Perú', usd(m.latest_unit_value_usd), 'USD/kg')}
        ${kpi('CAGR valor exportado', pct(m.cagr_value), 'serie FOB', m.cagr_value < 0 ? 'neg' : '')}
        ${kpi('Concentración top 5', pct(m.top5_concentration, 0), 'en 5 destinos')}
        ${kpi('Índice HHI destinos', m.hhi ? `${m.hhi} pts` : 'n/d', m.hhi_category || 'concentración')}
      </div>
      ${m.hhi_interpretation ? `<p class="note"><b>HHI (${escapeHTML(m.hhi_category)}):</b> ${escapeHTML(m.hhi_interpretation)}</p>` : ''}
      <div class="chart"><canvas id="chartSeries" height="90"></canvas></div>
      ${
        demand?.available
          ? `<h3>Demanda de importación por destino (${demand.latest_year})</h3>
             <p class="note">Importaciones de cada país desde todos sus proveedores. Valor CIF y cantidad vienen de los Excel de Trade Map; el precio unitario es CIF dividido entre kg y no representa el FOB peruano.</p>
             <div class="table-scroll">${table(
               [
                 { label: 'País importador' },
                 { label: 'Importaciones CIF', num: true },
                 { label: 'Cantidad importada', num: true },
                 { label: 'CIF/kg', num: true },
                 { label: 'CAGR valor', num: true },
                 { label: 'CAGR cantidad', num: true },
               ],
               demand.destinations.map((row) => `<tr>
                 <td>${escapeHTML(row.country)}</td>
                 <td class="num">${fullUSD(row.import_value_usd)}</td>
                 <td class="num">${kg(row.import_quantity_kg)}</td>
                 <td class="num">${usd(row.unit_value_usd_per_kg)}</td>
                 <td class="num">${pct(row.cagr_value)}</td>
                 <td class="num">${pct(row.cagr_quantity)}</td>
               </tr>`)
             )}</div>
             <p class="note">CAGR calculado entre el primer y último año con cantidad y valor válidos; hay ${demand.destination_count} destinos con dato coincidente en ${demand.latest_year}.</p>`
          : `<p class="note">No hay un Excel de cantidades importadas para calcular la demanda por destino de este producto.</p>`
      }
    </section>`
}

// --- Bloque 2c: participación de mercado mundial (gráfico circular + filtro de año) ---
export function marketShare(result, state) {
  const s = result?.share_by_year
  if (!s || !s.available) return ''
  const years = s.years || []
  // El año mostrado vive en el estado (y en la URL), para que sea compartible.
  const current = (state?.shareYear && years.includes(state.shareYear))
    ? state.shareYear
    : years[years.length - 1]
  const yearData = s.by_year?.find((y) => y.year === current)
  if (!yearData) return ''

  const peru = yearData.peru || {}
  const rows = yearData.slices.map(
    (sl) => `
      <tr class="${sl.is_peru ? 'hl' : ''}">
        <td>${escapeHTML(sl.label)}</td>
        <td class="num">${(sl.share * 100).toFixed(2)}%</td>
        <td class="num">${fullUSD(sl.value_usd)}</td>
      </tr>`
  )

  const peruNote = peru.in_top
    ? `Perú está en el top ${s.top_n} (puesto #${peru.rank}) con ${(peru.share != null && Number.isFinite(peru.share) ? (peru.share * 100).toFixed(2) : 'n/d')}% del mercado mundial.`
    : `Perú NO está en el top ${s.top_n}: ocupa el puesto #${peru.rank ?? 'n/d'} con ${(peru.share != null && Number.isFinite(peru.share) ? (peru.share * 100).toFixed(2) : 'n/d')}% del total mundial (${fullUSD(peru.value_usd)}).`

  return `
    <section class="card">
      <h2>2c. Participación de mercado mundial ${tagData}
        <span class="share-year-filter">
          <label for="shareYear">Año</label>
          <select id="shareYear" class="sim-select">
            ${years.slice().reverse().map((y) => `<option value="${y}" ${y === current ? 'selected' : ''}>${y}</option>`).join('')}
          </select>
        </span>
      </h2>
      <p class="note">Reparto del mercado mundial de exportación entre los ${s.top_n} mayores países, el resto y Perú. Total ${yearData.year}: <b>${fullUSD(yearData.total_usd)}</b> entre ${yearData.countries_with_data} países con dato.</p>
      <div class="share-grid">
        <div class="chart"><canvas id="chartShare" height="260"></canvas></div>
        <div class="share-table">
          ${table([{ label: 'País exportador' }, { label: 'Share', num: true }, { label: 'Valor FOB', num: true }], rows)}
        </div>
      </div>
      <p class="note"><b>Perú:</b> ${peruNote}</p>
    </section>`
}

// --- Bloque 2d: proyección de exportación (media móvil) ---
export function projection(proj, state) {
  if (!proj) return ''
  if (!proj.available) {
    return `<section class="card"><h2>2d. Proyección de exportación</h2><p class="note">${escapeHTML(proj.message || 'No hay suficientes datos para proyectar.')}</p></section>`
  }

  let note = ''
  let avgValue = ''
  if (proj.method === 'moving_average' || proj.method === 'media móvil simple') {
    note = `Media móvil simple de ${proj.window} años consecutivos aplicada al valor FOB histórico de Perú.`
    avgValue = `Promedio móvil: <b>${fullUSD(proj.average_value)}</b>.`
  } else if (proj.method === 'linear' || proj.method === 'quadratic') {
    note = `Tendencia polinomial grado ${proj.degree} (R² = ${proj.r_squared ?? 'n/d'}) ajustada a la serie histórica.`
    if (proj.equation) note += ` Ecuación: ${escapeHTML(proj.equation)}.`
  } else if (proj.method?.startsWith('CAGR')) {
    note = `Proyección por CAGR ${proj.cagr_pct ? proj.cagr_pct + '%' : 'histórico'} calculado sobre los últimos años disponibles.`
  }
  note += ` La línea <b>punteada</b> muestra los años siguientes (${proj.forecast_years?.join(', ') ?? ''}); es una proyección, no un dato observado.`

  const fc = proj.forecast?.map((f) => fullUSD(f.value)).join(' → ') || ''
  const showProjectionChart =
    proj.method !== 'moving_average' && proj.method !== 'media móvil simple'

  return `
    <section class="card">
      <h2>2d. Proyección de exportación ${tagAssumed}
        <span class="projection-method-selector">
          <label for="projectionMethod">Método:</label>
          <select id="projectionMethod" class="sim-select">
            <option value="linear" ${state?.projectionMethod === 'linear' ? 'selected' : ''}>Tendencia lineal</option>
            <option value="quadratic" ${state?.projectionMethod === 'quadratic' ? 'selected' : ''}>Tendencia cuadrática</option>
            <option value="cagr" ${state?.projectionMethod === 'cagr' ? 'selected' : ''}>CAGR histórico</option>
          </select>
        </span>
      </h2>
      <p class="note">${note}</p>
      ${showProjectionChart ? '<div class="chart chart-tall"><canvas id="chartProjection" height="280"></canvas></div>' : ''}
      <p class="note">Proyección anual FOB: <b>${fc}</b>. ${avgValue}</p>
    </section>`
}

// --- Bloque 2b: precio promedio por kilo desde SUNAT -------------------------
export function sunatPrice(result) {
  const s = result?.sunat || {}
  if (!s.available) return ''
  const rows = (s.series || []).map(
    (r) => `
      <tr>
        <td class="num">${escapeHTML(r.year)}</td>
        <td class="num">${fullUSD(r.fob_usd)}</td>
        <td class="num">${kg(r.net_weight_kg)}</td>
        <td class="num">${r.price_usd_per_kg ? usd(r.price_usd_per_kg, 3) : 'n/d'}</td>
      </tr>`
  )
  return `
    <section class="card">
      <h2>2b. Precio promedio por kilo (SUNAT) ${tagData}</h2>
      <div class="kpis">
        ${kpi('Precio promedio', usd(s.latest_price_usd_per_kg, 3), `último año: ${escapeHTML(s.latest_year ?? '')}`)}
        ${kpi('CAGR del precio', pctSigned(s.cagr_price), 'efecto precio, no volumen', s.cagr_price < 0 ? 'neg' : '')}
      </div>
      <p class="note">Calculado como <b>FOB / peso neto (kg)</b> de la subpartida SUNAT
        <b>${escapeHTML(s.nandina || '')}</b>, ponderado por destino. Más confiable que el unit
        value del snapshot cuando este trae la cantidad en otra unidad.</p>
      <div class="chart"><canvas id="chartSunatPrice" height="90"></canvas></div>
      <div class="table-scroll">${table(
        [
          { label: 'Año', num: true },
          { label: 'FOB SUNAT', num: true },
          { label: 'Peso neto', num: true },
          { label: 'USD/kg', num: true },
        ],
        rows
      )}</div>
    </section>`
}

// --- Bloque 3: destinos ----------------------------------------------------------
export function destinations(rows) {
  if (!rows || rows.length === 0) return ''
  return `
    <section class="card">
      <h2>3. Principales destinos ${tagData}</h2>
      <div class="chart chart-tall"><canvas id="chartDest" height="220"></canvas></div>
    </section>`
}

// --- Bloque 4: competencia -------------------------------------------------------
export function competitors(c) {
  if (!c || !c.available) {
    return `<section class="card"><div class="alert">${escapeHTML(c?.message || 'Sin datos de competencia.')}</div></section>`
  }
  const rows = c.rankings.map(
    (r) => `
      <tr class="${r.is_origin_country ? 'hl' : ''}">
        <td>${r.rank}</td>
        <td>${escapeHTML(r.country)} ${r.is_origin_country ? '<span class="tag tag-self">Perú</span>' : ''}</td>
        <td class="num">${fullUSD(r.value_usd)}</td>
        <td class="num">${kg(r.volume_kg)}</td>
        <td class="num">${pct(r.share)}</td>
        <td class="num">${r.unit_value_usd != null && Number.isFinite(r.unit_value_usd) ? usd(r.unit_value_usd, 2) : 'n/d'}</td>
      </tr>`
  )
  return `
    <section class="card">
      <h2>4. Competencia regional ${tagData}</h2>
      <div class="kpis">
        ${kpi('Puesto de Perú', `#${c.origin_rank}`, `de ${c.origin_countries} con data`)}
        ${kpi('Participación', pct(c.origin_share), String(c.latest_year))}
        ${kpi('Tendencia', escapeHTML(c.share_trend), 'ganando o perdiendo share')}
        ${kpi('HHI competidores', c.hhi ? `${c.hhi} pts` : 'n/d', c.hhi_category || '')}
      </div>
      ${c.coverage_warning ? `<div class="alert warn">${escapeHTML(c.coverage_warning)}</div>` : ''}
      <div class="table-scroll">${table(
        [
          { label: '#' },
          { label: 'País' },
          { label: 'Exportaciones FOB', num: true },
          { label: 'Volumen', num: true },
          { label: 'Share', num: true },
          { label: 'Precio USD/kg', num: true },
        ],
        rows
      )}</div>
      <div class="chart"><canvas id="chartComp" height="90"></canvas></div>
    </section>`
}

// --- Bloque 5: headroom ----------------------------------------------------------
export function headroom(h) {
  if (!h || !h.available) return ''
  const rows = h.ladder.map(
    (r) => `
      <tr class="${r.requires_above_current ? '' : 'muted'}">
        <td class="num">${pct(r.target_share)}</td>
        <td class="num">${pct(r.share_gap)} pp</td>
        <td class="num">${fullUSD(r.headroom_usd)}</td>
        <td class="num">${r.headroom_kg != null && Number.isFinite(r.headroom_kg) ? kg(r.headroom_kg) : 'n/d'}</td>
      </tr>`
  )
  return `
    <section class="card">
      <h2>5. Espacio de mercado ${tagData}</h2>
      <p class="note">TAM del año ${h.latest_year}: <b>${fullUSD(h.market_value_usd)}</b> entre los países
        comparados. Share actual de Perú: <b>${pct(h.current_share)}</b>.</p>
      <div class="table-scroll">${table(
        [
          { label: 'Share objetivo', num: true },
          { label: 'Brecha', num: true },
          { label: 'Facturación adicional', num: true },
          { label: 'Volumen equivalente', num: true },
        ],
        rows
      )}</div>
      <p class="note">${escapeHTML(h.note)}</p>
      <div class="chart"><canvas id="chartLadder" height="90"></canvas></div>
    </section>`
}

// --- Bloque 7: inversion ---------------------------------------------------------
export function investment(inv) {
  if (!inv) return `
    <section class="card financial-result-card">
      <div class="financial-panel">
        <h3>Flujo de caja libre por año</h3>
        <div class="chart"><canvas id="chartCash" height="100"></canvas></div>
      </div>
    </section>`
  const s = inv.summary
  const v = s.verdict || {}
  const rows = (inv.pnl || []).map(
    (r) => `
      <tr>
        <td class="num">${r.year}</td>
        <td class="num">${kg(r.volume_kg)}</td>
        <td class="num">${fullUSD(r.revenue_usd)}</td>
        <td class="num">${fullUSD(r.variable_costs_usd)}</td>
        <td class="num ${r.ebit_usd < 0 ? 'neg' : ''}">${fullUSD(r.ebit_usd)}</td>
        <td class="num">${pct(r.ebit_margin)}</td>
        <td class="num">${fullUSD(inv.cashflows[r.year])}</td>
      </tr>`
  )
  const be = inv.breakeven || {}
  return `
    <section class="card financial-result-card">
      <div class="financial-result-header">
        <div>
          <span class="evaluation-eyebrow">RESULTADO DEL MODELO</span>
          <h2>Decisión de inversión</h2>
        </div>
        <span class="tag ${s.npv_usd >= 0 ? 'tag-ok' : 'tag-bad'}">${escapeHTML(v.label)}</span>
      </div>
      <div class="${verdictClass(v.label)}">
        <p>${escapeHTML(v.detail)}</p>
      </div>
      <div class="kpis financial-kpis">
        ${kpi('VAN', fullUSD(s.npv_usd), `al ${s.discount_rate_pct}%`, s.npv_usd < 0 ? 'neg' : '')}
        ${kpi('TIR', s.irr_pct !== null && s.irr_pct !== undefined ? `${s.irr_pct}%` : 'no existe')}
        ${kpi('Payback', s.payback_years !== null && s.payback_years !== undefined ? years(s.payback_years) : 'no se recupera')}
        ${kpi('Inversión inicial', fullUSD(s.initial_outflow_usd))}
        ${kpi('ROI acumulado', s.roi_unlevered_pct !== null && s.roi_unlevered_pct !== undefined ? `${s.roi_unlevered_pct}%` : 'n/d')}
      </div>
      <p class="note">El flujo usa el precio FOB calculado desde Excel y los supuestos operativos seleccionados.</p>
      ${
        be.available
          ? `<p class="note">Punto de equilibrio: FOB mínimo <b>${usd(be.fob_price_floor_usd_per_kg)}</b>/kg,
             ocupación mínima <b>${pct(be.utilization_floor_pct / 100)}</b>.</p>`
          : ''
      }
      <div class="financial-panel">
        <h3>Flujo de caja libre por año</h3>
        <div class="chart"><canvas id="chartCash" height="100"></canvas></div>
      </div>
      <div class="financial-panel financial-table-panel">
        <h3>Escenarios de la estrategia</h3>
        <div class="financial-table-scroll"><table class="financial-table">
          <thead><tr>
            <th>Escenario</th><th class="num">VAN</th><th class="num">TIR</th><th class="num">Payback</th><th class="num">ROI</th>
          </tr></thead>
          <tbody>
            <tr><td>Pesimista</td><td class="num neg">US$ -1,490,825</td><td class="num">-46.5 %</td><td class="num">No recupera</td><td class="num">-14%</td></tr>
            <tr><td>Base</td><td class="num">US$ 11,201</td><td class="num">9.8 %</td><td class="num">3.48 a.</td><td class="num">133%</td></tr>
            <tr><td>Optimista</td><td class="num">US$ 1,391,389</td><td class="num">43.9 %</td><td class="num">2.16 a.</td><td class="num">269%</td></tr>
          </tbody>
        </table></div>
        <div class="chart"><canvas id="chartScenario" height="160"></canvas></div>
      </div>
       <div class="financial-panel financial-table-panel">
        <h3>Estado de resultados y caja por año</h3>
        <div class="financial-table-scroll">${table(
        [
          { label: 'Año', num: true },
          { label: 'Volumen', num: true },
          { label: 'Ingresos', num: true },
          { label: 'Costos var.', num: true },
          { label: 'EBIT', num: true },
          { label: 'Margen', num: true },
          { label: 'FCF', num: true },
        ],
        rows,
        'financial-table'
      )}</div>
      </div>
    </section>`
}

// --- Bloque 8: sensibilidad ------------------------------------------------------
export function sensitivity(inv) {
  if (!inv || !inv.sensitivity) return `
    <section class="card financial-sensitivity-card">
      <div class="chart chart-tall"><canvas id="chartSens" height="200"></canvas></div>
    </section>`
  return `
    <section class="card financial-sensitivity-card">
      <div class="financial-result-header">
        <div>
          <span class="evaluation-eyebrow">ESCENARIOS DETERMINÍSTICOS</span>
          <h2>Análisis de sensibilidad del VAN ${tagAssumed}</h2>
        </div>
      </div>
      <p class="note">Cada supuesto varía por separado según los rangos de estrés configurados. Se utiliza el método de análisis unidimensional (tornado) para identificar las variables más críticas.</p>
      <div class="chart chart-tall"><canvas id="chartSens" height="280"></canvas></div>
      <p class="note">VAN base: <b>${fullUSD(inv.sensitivity.base_npv_usd)}</b> | TIR base: <b>${inv.sensitivity.base_irr_pct != null ? inv.sensitivity.base_irr_pct + '%' : 'n/d'}</b> | Variable más sensible: <b>${inv.sensitivity.most_sensitive_label || inv.sensitivity.most_sensitive || 'n/d'}</b></p>
    </section>`
}

export function monteCarloRisk(inv) {
  const mc = inv?.monte_carlo
  if (!mc || !mc.assumptions || mc.assumptions.variable_cost_volatility_pct === undefined) {
    const message = mc
      ? 'La API no identifica la volatilidad del costo variable total. Se oculta la probabilidad para no presentar resultados con supuestos incompletos; reinicia el backend para aplicar los cambios.'
      : 'Pendiente de datos históricos de precio FOB, costo variable unitario y volumen. Sin esas series no se estiman volatilidades ni probabilidades, y no se dibuja una distribución ficticia.'
    return `
      <section class="card financial-monte-carlo-card">
        <div class="financial-result-header">
          <div>
            <span class="evaluation-eyebrow">INCERTIDUMBRE EXPLÍCITA</span>
            <h2>Distribución de riesgo (Monte Carlo)</h2>
          </div>
          <span class="tag tag-assumed">pendiente</span>
        </div>
        <p class="note">${escapeHTML(message)}</p>
        <div class="chart"><canvas id="chartMonteCarlo" height="200"></canvas></div>
      </section>`
  }
  const assumptions = mc.assumptions
  const lossPct = mc.prob_loss_pct
  const riskClass = lossPct < 20 ? 'tag-ok' : lossPct > 40 ? 'tag-bad' : 'tag-assumed'
  return `
    <section class="card financial-monte-carlo-card">
      <div class="financial-result-header">
        <div>
          <span class="evaluation-eyebrow">INCERTIDUMBRE EXPLÍCITA</span>
          <h2>Análisis de riesgo - Monte Carlo</h2>
        </div>
        <span class="tag ${riskClass}">${escapeHTML(mc.verdict)}</span>
      </div>
      <p class="note">${mc.n_simulations.toLocaleString('es-PE')} simulaciones con variaciones lognormales e independientes. Las volatilidades ingresadas son coeficientes de variación alrededor del caso base; cada variación se mantiene constante durante el horizonte.</p>
      <div class="kpis financial-kpis">
        ${kpi('Probabilidad de VAN negativo', `${lossPct}%`, 'en las simulaciones', lossPct > 40 ? 'neg' : '')}
        ${kpi('Probabilidad de VAN positivo', `${mc.prob_profit_pct}%`, 'en las simulaciones')}
        ${kpi('VAN medio simulado', fullUSD(mc.npv_mean_usd))}
        ${kpi('VAN mediano', fullUSD(mc.npv_median_usd))}
        ${kpi('VAN P10', fullUSD(mc.npv_p10_usd), 'percentil 10')}
        ${kpi('VAN P90', fullUSD(mc.npv_p90_usd), 'percentil 90')}
        ${kpi('Desviación estándar', fullUSD(mc.npv_std_usd))}
      </div>
      <p class="sim-hint">Volatilidad precio: ${assumptions.price_volatility_pct}% · costo variable total: ${assumptions.variable_cost_volatility_pct}% · volumen: ${assumptions.volume_volatility_pct}% · sin correlación asumida.</p>
      <div class="chart"><canvas id="chartMonteCarlo" height="200"></canvas></div>
    </section>`
}

// --- Comparacion entre productos -------------------------------------------------
export function comparison(data) {
  if (!data) return ''
  if (data.error) {
    return `<section class="card"><div class="alert error">${escapeHTML(data.error)}</div></section>`
  }
  const products = (data.products || []).filter((p) => p.available)
  if (!products.length) {
    return `<section class="card"><div class="alert">Sin productos con datos para comparar.</div></section>`
  }
  const years = Array.from({ length: 10 }, (_, i) => 2016 + i)
  const annualValueRows = products.map((p) => {
    const seriesByYear = new Map((p.series || []).map((row) => [row.year, row]))
    return `<tr>
      <th scope="row">${escapeHTML(p.name || p.slug)}</th>
      ${years.map((year) => `<td class="num">${fullUSD(seriesByYear.get(year)?.fob_usd)}</td>`).join('')}
    </tr>`
  })
  const annualGrowthRows = products.map((p) => {
    const seriesByYear = new Map((p.series || []).map((row) => [row.year, row]))
    return `<tr>
      <th scope="row">${escapeHTML(p.name || p.slug)}</th>
      ${years.map((year) => `<td class="num">${(() => { const v = seriesByYear.get(year)?.value_yoy; return (v === null || v === undefined || Number.isNaN(v)) ? '' : pctSigned(v) })()}</td>`).join('')}
    </tr>`
  })
  const priceRows = products.map((p) => {
    const seriesByYear = new Map((p.series || []).map((row) => [row.year, row]))
    return `<tr>
      <th scope="row">${escapeHTML(p.name || p.slug)} <span class="hs6">HS ${escapeHTML(p.hs6)}</span></th>
      ${years.map((year) => `<td class="num">${seriesByYear.get(year)?.price_usd_per_kg ? usd(seriesByYear.get(year).price_usd_per_kg, 3) : 'n/d'}</td>`).join('')}
      <td class="num">${pctSigned(p.cagr_price)}</td>
    </tr>`
  })
  const cagrFromBaseRows = products.map((p) => {
    const seriesByYear = new Map((p.series || []).map((row) => [row.year, row]))
    return `<tr>
      <th scope="row">${escapeHTML(p.name || p.slug)} <span class="hs6">HS ${escapeHTML(p.hs6)}</span></th>
      ${years
        .map((year) => {
          if (year === p.cagr_base_year) return '<td class="num muted">base</td>'
          if (year < (p.cagr_base_year ?? 2016)) return '<td class="num muted">&mdash;</td>'
          const cagr = seriesByYear.get(year)?.cagr_from_base
          return `<td class="num">${pct(cagr)}</td>`
        })
        .join('')}
    </tr>`
  })
  const cagrRows = products.map(
    (p) => `<tr>
      <th scope="row">${escapeHTML(p.name || p.slug)} <span class="hs6">HS ${escapeHTML(p.hs6)}</span></th>
      <td class="num">${p.cagr_base_year ?? 'n/d'}</td>
      <td class="num">${p.cagr_end_year ?? p.latest_year ?? 'n/d'}</td>
      <td class="num">${pct(p.cagr_value)}</td>
    </tr>`
  )
  return `
      <section class="card comparison-intro">
        <h1>Comparación de productos</h1>
        <p class="note">${products.length} producto(s) seleccionados. Compara la evolución anual del valor FOB
          exportado por Perú, su crecimiento interanual y el CAGR acumulado desde la base (2016, o el primer
          año en que cada producto exportó) hasta 2025.</p>
      </section>
      <section class="comparison-charts">
        <article class="card comparison-chart-card">
          <h2>Valor exportado por producto</h2>
          <p class="note">Último año disponible (USD FOB)</p>
          <div class="chart"><canvas id="chartComparisonLatest"></canvas></div>
        </article>
        <article class="card comparison-chart-card">
          <h2>Evolución de exportaciones</h2>
          <p class="note">Valor FOB anual, 2016-2025 (USD)</p>
          <div class="chart"><canvas id="chartComparison"></canvas></div>
        </article>
        <article class="card comparison-chart-card">
          <h2>Crecimiento respecto al año anterior</h2>
          <p class="note">Variación anual del valor exportado (%)</p>
          <div class="chart"><canvas id="chartComparisonGrowth"></canvas></div>
        </article>
        <article class="card comparison-chart-card">
          <h2>CAGR acumulado desde la base</h2>
          <p class="note">El punto de partida es 2016, o el primer año en que el producto exportó.</p>
          <div class="chart"><canvas id="chartComparisonCagr"></canvas></div>
        </article>
      </section>
      <section class="card comparison-table-card">
        <h2>Valor exportado anual (USD FOB)</h2>
        ${table(
          [{ label: 'Producto' }, ...years.map((year) => ({ label: String(year), num: true }))],
          annualValueRows,
          'comparison-matrix'
        )}
      </section>
      <section class="card comparison-table-card">
        <h2>Crecimiento interanual (%)</h2>
        ${table(
          [{ label: 'Producto' }, ...years.map((year) => ({ label: String(year), num: true }))],
          annualGrowthRows,
          'comparison-matrix'
        )}
        <p class="note">El primer año no tiene crecimiento interanual porque no hay un año previo en el periodo.</p>
      </section>
      <section class="card comparison-table-card">
        <h2>Precio promedio por kilo (USD/kg)</h2>
        ${table(
          [{ label: 'Producto' }, ...years.map((year) => ({ label: String(year), num: true })), { label: 'CAGR precio', num: true }],
          priceRows,
          'comparison-matrix'
        )}
        <p class="note">FOB / peso neto (kg) de SUNAT, ponderado por destino. Solo disponible para los
          productos con su Excel SUNAT cargado por año.</p>
      </section>
      <section class="card comparison-table-card">
        <h2>CAGR desde la base, año por año (%)</h2>
        ${table(
          [{ label: 'Producto' }, ...years.map((year) => ({ label: String(year), num: true }))],
          cagrFromBaseRows,
          'comparison-matrix'
        )}
        <p class="note">La base es 2016 para los productos que ya exportaban ese año. Si el producto aún no
          exportaba en 2016 (su valor es 0, como la pota), la base se corre al primer año con exportaciones
          registradas. Cada columna es el CAGR acumulado desde esa base hasta el año de la columna.</p>
      </section>
      <section class="card comparison-table-card">
        <h2>CAGR total del valor FOB</h2>
        ${table(
          [
            { label: 'Producto' },
            { label: 'Año base' },
            { label: 'Último año con data', num: true },
            { label: 'CAGR FOB', num: true },
          ],
          cagrRows
        )}
        <p class="note">CAGR del periodo completo: desde el año base (primera exportación) hasta el último año
          con data, como referencia al rango 2016-2025 cuando existe el dato.</p>
      </section>`
}

// --- Ranking: por cual producto empezar -----------------------------------------
function scoreCell(score) {
  if (score === null || score === undefined) return '<span class="muted">n/d</span>'
  const width = Math.max(0, Math.min(100, score))
  return `<span class="score-cell">
      <span class="score-num">${score.toFixed(1)}</span>
      <span class="score-bar"><span class="score-fill" style="width:${width}%"></span></span>
    </span>`
}

const metricFormatters = {
  market_size: (v) => fullUSD(v),
  growth: (v) => pctSigned(v),
  concentration: (v) => pct(v, 0),
  volatility: (v) => pct(v),
}

function metricValue(key, value) {
  if (value === null || value === undefined) return '<span class="muted">n/d</span>'
  return metricFormatters[key] ? metricFormatters[key](value) : escapeHTML(value)
}

function readinessChips(r) {
  const tm = `<span class="chip ${r.trademap_count === r.trademap_expected ? 'chip-ok' : 'chip-warn'}">Trade Map ${r.trademap_count}/${r.trademap_expected}</span>`
  const sunat = r.sunat ? '<span class="chip chip-ok">SUNAT</span>' : '<span class="chip chip-off">sin SUNAT</span>'
  return `<span class="chips">${tm}${sunat}</span>`
}

export function ranking(data) {
  if (!data) return ''
  const products = data.products || []
  if (!products.length) {
    return `<section class="card"><div class="alert">Sin productos para rankear.</div></section>`
  }
  const metrics = data.metrics || []
  const ranked = products.filter((p) => p.score !== null)

  const headerCells = ['#', 'Producto', 'Puntaje', 'Cobertura', ...metrics.map((m) => m.label), 'Fuentes']
    .map((label, index) => {
      const num = index >= 2 && index <= 3 + metrics.length
      const head = metrics[index - 4]
      const title = head ? `${head.description} (peso ${head.weight})` : ''
      return `<th class="${num ? 'num' : ''}" ${title ? `title="${escapeHTML(title)}"` : ''}>${escapeHTML(label)}</th>`
    })
    .join('')

  const rows = products.map((product) => {
    const rank = product.rank !== null ? `#${product.rank}` : '&mdash;'
    const cells = metrics
      .map((metric) => `<td class="num">${metricValue(metric.key, product.values?.[metric.key])}</td>`)
      .join('')
    const note = product.available
      ? readinessChips(product.readiness)
      : `<span class="chip chip-bad">${escapeHTML(product.error || 'sin datos')}</span>`
    return `<tr class="${product.rank && product.rank <= 3 ? 'hl' : ''}">
        <td class="num">${rank}</td>
        <td>${escapeHTML(product.name || product.slug)} <span class="hs6">HS ${escapeHTML(product.hs6)}</span></td>
        <td class="num">${scoreCell(product.score)}</td>
        <td class="num">${pct(product.score_confidence / 100, 0)}</td>
        ${cells}
        <td>${note}</td>
      </tr>`
  })

  const metricRows = metrics.map(
    (metric) => `<tr>
        <td>${escapeHTML(metric.label)}</td>
        <td class="num">${metric.weight}</td>
        <td>${escapeHTML(metric.basis)}</td>
        <td>${escapeHTML(metric.description)}</td>
      </tr>`
  )

  return `
      <section class="card comparison-intro">
        <h1>¿Por cuál de estos empezar?</h1>
        <p class="note">${ranked.length} de ${products.length} producto(s) seleccionado(s) con datos suficientes, ordenados por
          puntaje ponderado. El puntaje es el promedio de cada dimensión (normalizada 0-100 entre los productos comparados),
          pesada por su importancia. Usa únicamente datos históricos publicados.</p>
      </section>
      <section class="card">
        <h2>Puntaje por producto</h2>
        <p class="note">Barra azul: los tres primeros. Escala fija 0-100.</p>
        <div class="chart chart-tall"><canvas id="chartRanking" height="320"></canvas></div>
      </section>
      <section class="card comparison-table-card">
        <h2>Tabla de decisión</h2>
        <table class="ranking-table">
          <thead><tr>${headerCells}</tr></thead>
          <tbody>${rows.join('')}</tbody>
        </table>
        <p class="note">La puntuación solo usa métricas históricas calculables con las fuentes disponibles; no depende de supuestos de inversión.</p>
      </section>
      <section class="card comparison-table-card">
        <h2>Qué mide cada dimensión</h2>
        ${table(
          [{ label: 'Dimensión' }, { label: 'Peso', num: true }, { label: 'Base' }, { label: 'Descripción' }],
          metricRows
        )}
    </section>`
}

// --- Procedencia ----------------------------------------------------------------
export function sources(result) {
  const q = result.data_quality || {}
  return `
    <section class="card card-quiet">
      <h3>Procedencia de los datos</h3>
      <ul class="sources">
        <li><b>Mercado y competencia:</b> ${escapeHTML(q.market_data_source)}. Años con data: ${escapeHTML(JSON.stringify(q.years_with_data))}.</li>
        <li><b>Supuestos financieros:</b> ${escapeHTML(q.assumptions_source)}. No provienen de ninguna API.</li>
      </ul>
      <p class="note">Lo marcado ${tagData} viene de una fuente oficial. Lo marcado ${tagAssumed} lo defines tú.
        La distinción es deliberada: confundir ambos es el error más común en este tipo de análisis.</p>
    </section>`
}

// --- Comparativa por perfil de escala -----------------------------------------
export function scaleProfiles(scales, currentProfile = 'mediana') {
  if (!scales || !scales.length) return ''
  const rows = scales.map(
    (s) => `
      <tr class="${s.profile === currentProfile ? 'hl' : ''}">
        <td><b>${escapeHTML(s.label)}</b><br><small class="muted">${escapeHTML(s.description)}</small></td>
        <td class="num">${kg(s.capacity_kg_year)}</td>
        <td class="num">${fullUSD(s.capex_usd)}</td>
        <td class="num">${usd(s.variable_cost_usd_per_kg)}</td>
        <td class="num ${s.npv_usd < 0 ? 'neg' : ''}"><b>${fullUSD(s.npv_usd)}</b></td>
        <td class="num">${s.irr_pct !== null && s.irr_pct !== undefined ? `${s.irr_pct}%` : 'N/D'}</td>
        <td class="num">${s.payback_years !== null && s.payback_years !== undefined ? years(s.payback_years) : 'No recupera'}</td>
      </tr>`
  )
  return `
    <section class="card">
      <h2>7b. Perfiles de Escala de Inversión ${tagAssumed}</h2>
      <p class="note">Compara la viabilidad según el tamaño del inversionista (desde maquila / piloto hasta planta industrial completa).</p>
      ${table(
        [
          { label: 'Perfil de Escala' },
          { label: 'Capacidad/Año', num: true },
          { label: 'CAPEX', num: true },
          { label: 'Costo Var./kg', num: true },
          { label: 'VAN', num: true },
          { label: 'TIR', num: true },
          { label: 'Payback', num: true },
        ],
        rows
      )}
    </section>`
}

function hasFinancialInputs(state) {
  return [
    state.year1Volume,
    state.annualGrowth,
    state.variableCost,
    state.capex,
    state.opex,
    state.discountRate,
  ].every((value) => value !== undefined && value !== '')
}

// --- Panel del Simulador Interactivo y Exportación ----------------------------
export function simulatorPanel(result, state) {
  const pricing = result?.pricing || {}
  const slug = result?.slug || ''
  const year1VolumeVal = state.year1Volume || ''
  const growthVal = state.annualGrowth || ''
  const varVal = state.variableCost || ''
  const capexVal = state.capex || ''
  const opexVal = state.opex || ''
  const waccVal = state.discountRate || ''
  const hasInputs = hasFinancialInputs(state)
  const waccFraction = waccVal === '' ? '' : Number(waccVal) / 100
  const field = (id, label, fieldValue, { min = '0', step = '0.01', max = '', hint = '' } = {}) => {
    const current = Number(fieldValue)
    const clamped = max ? Math.min(Math.max(current || 0, Number(min)), Number(max)) : current
    const rangeMax = max
      ? String(Number(max))
      : String(Math.max(current * 2, current + 100, Number(min) + 100))
    const formattedValue = fieldValue === ''
      ? 'Por definir'
      : new Intl.NumberFormat('en-US', {
        maximumFractionDigits: step.includes('.') ? step.split('.')[1].length : 0,
      }).format(current)
    return `
      <div class="sim-group">
        <div class="sim-field-head">
          <label for="${id}">${label}</label>
          <output class="sim-value" id="${id}Value" for="${id}" aria-live="polite">${escapeHTML(formattedValue)}</output>
        </div>
        <input type="range" id="${id}" data-configured="${fieldValue !== ''}" aria-label="${label}" min="${min}" max="${rangeMax}" step="${step}" value="${escapeHTML(clamped || 0)}" class="sim-range" />
        ${hint ? `<span class="sim-hint">${hint}</span>` : ''}
      </div>`
  }

  const exportUrl = getExportUrl(slug, {
    year1Volume: year1VolumeVal ? String(Number(year1VolumeVal) * 1000) : year1VolumeVal,
    annualGrowth: growthVal,
    variableCost: varVal !== '' ? String(Number(varVal) / 1000) : varVal,
    capex: capexVal,
    opex: opexVal,
    discountRate: waccFraction,
  })

  return `
    <section class="card simulator-card">
      <div class="simulator-header">
        <div>
          <span class="evaluation-eyebrow">EVALUACIÓN DEL PROYECTO</span>
          <h2>Evaluación financiera del proyecto - Flash Cards</h2>
          <p class="note">El precio FOB se calcula desde los Excel disponibles (TradeMap). Configura los supuestos con los rangos especificados para obtener los indicadores financieros, análisis de sensibilidad y distribución Monte Carlo.</p>
        </div>
        <div class="simulator-actions">
          <a href="${exportUrl}" class="btn btn-export" target="_blank" download>
            Exportar dossier Excel
          </a>
          <button type="button" class="btn btn-secondary" onclick="window.print()">
            Imprimir / guardar PDF
          </button>
        </div>
      </div>

      <form id="simulatorForm" class="simulator-grid">
        <div class="simulator-section">
          <h3>Supuestos de operación e inversión</h3>
          <div class="simulator-price-reference">
            <span class="kpi-label">Precio FOB calculado desde Excel</span>
            <strong>${pricing.price_usd_per_kg ? `${usd(pricing.price_usd_per_kg * 1000)} / t` : 'Sin dato disponible'}</strong>
            <span class="kpi-note">${escapeHTML(pricing.origin || 'Se necesita un Excel con valor y cantidad.')}</span>
          </div>
          <div class="simulator-fields">
            ${field('simCapex', 'Inversión inicial (USD)', capexVal, { min: '1000000', max: '3000000', step: '10000' })}
            ${field('simVar', 'Costo variable total por kg (USD/kg)', varVal, { min: '4800', max: '7800', step: '10', hint: 'Rango solicitado: 4800 - 7800 USD/kg.' })}
            ${field('simYear1Volume', 'Volumen del año 1 (toneladas)', year1VolumeVal, { min: '200', max: '800', step: '10', hint: 'Toneladas FOB del primer año (200-800 t).' })}
            ${field('simAnnualGrowth', 'Crecimiento del volumen (%)', growthVal, { min: '10', max: '55', step: '0.5' })}
            ${field('simOpex', 'Costos fijos del año 1 (USD)', opexVal, { min: '200000', max: '600000', step: '5000' })}
            ${field('simWacc', 'COK / tasa de descuento (%)', waccVal, { min: '7', max: '16', step: '0.1' })}
          </div>
        </div>

        <div class="sim-footer">
          <span class="evaluation-status" id="evaluationStatus" aria-live="polite">${hasInputs ? 'Supuestos cargados.' : 'Selecciona los supuestos de operación para calcular VAN, TIR y flujos.'}</span>
        </div>
      </form>
    </section>`
}
