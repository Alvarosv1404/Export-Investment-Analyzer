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
export function unitEconomics(u) {
  if (!u) return ''
  const viable = u.is_viable
  return `
    <section class="card ${viable ? '' : 'card-bad'}">
      <h2>1. Economia unitaria
        <span class="tag ${viable ? 'tag-ok' : 'tag-bad'}">${viable ? 'viable' : 'margen negativo'}</span>
      </h2>
      <div class="kpis">
        ${kpi('Precio FOB de mercado', usd(u.fob_price_usd_per_kg), 'Trade Map / input')}
        ${kpi('Costo variable total', usd(u.total_variable_cost_usd_per_kg), 'supuesto tuyo')}
        ${kpi('Margen bruto', usd(u.gross_margin_usd_per_kg), `${pct(u.gross_margin_pct)} por kilo`, viable ? '' : 'neg')}
        ${kpi('Precio de equilibrio', usd(u.breakeven_fob_price_usd_per_kg), 'minimo para no perder')}
      </div>
      ${(u.warnings || []).map((w) => `<div class="alert warn">${escapeHTML(w)}</div>`).join('')}
    </section>`
}

// --- Bloque 2: mercado -----------------------------------------------------------
export function market(m) {
  if (!m || !m.available) {
    return `<section class="card"><div class="alert error">${escapeHTML(m?.message || 'Sin datos de mercado.')}</div></section>`
  }
  return `
    <section class="card">
      <h2>2. Mercado ${tagData}</h2>
      <div class="kpis">
        ${kpi('Exportaciones FOB', fullUSD(m.latest_fob_usd), String(m.latest_year))}
        ${kpi('Volumen', kg(m.latest_volume_kg), 'peso neto')}
        ${kpi('Precio unitario', usd(m.latest_unit_value_usd), 'por kg, promedio ponderado')}
        ${kpi('CAGR valor', pct(m.cagr_value), 'ventana analizada', m.cagr_value < 0 ? 'neg' : '')}
        ${kpi('CAGR volumen', pct(m.cagr_volume), 'fisico', m.cagr_volume < 0 ? 'neg' : '')}
        ${kpi('CAGR precio', pctSigned(m.cagr_unit_value), 'efecto precio vs volumen', m.cagr_unit_value < 0 ? 'neg' : '')}
        ${kpi('Concentracion top 5', pct(m.top5_concentration, 0), 'en 5 destinos')}
      </div>
      <div class="chart"><canvas id="chartSeries" height="90"></canvas></div>
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
        <td>${escapeHTML(r.country)} ${r.is_origin_country ? '<span class="tag tag-self">Peru</span>' : ''}</td>
        <td class="num">${fullUSD(r.value_usd)}</td>
        <td class="num">${kg(r.volume_kg)}</td>
        <td class="num">${pct(r.share)}</td>
        <td class="num">${r.unit_value_usd ? usd(r.unit_value_usd, 2) : 'n/d'}</td>
      </tr>`
  )
  return `
    <section class="card">
      <h2>4. Competencia regional ${tagData}</h2>
      <div class="kpis">
        ${kpi('Puesto de Peru', `#${c.origin_rank}`, `de ${c.origin_countries} con data`)}
        ${kpi('Participacion', pct(c.origin_share), String(c.latest_year))}
        ${kpi('Tendencia', escapeHTML(c.share_trend), 'ganando o perdiendo share')}
      </div>
      ${c.coverage_warning ? `<div class="alert warn">${escapeHTML(c.coverage_warning)}</div>` : ''}
      ${table(
        [
          { label: '#' },
          { label: 'Pais' },
          { label: 'Exportaciones FOB', num: true },
          { label: 'Volumen', num: true },
          { label: 'Share', num: true },
          { label: 'Precio USD/kg', num: true },
        ],
        rows
      )}
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
        <td class="num">${r.headroom_kg ? kg(r.headroom_kg) : 'n/d'}</td>
      </tr>`
  )
  return `
    <section class="card">
      <h2>5. Espacio de mercado ${tagData}</h2>
      <p class="note">TAM del ano ${h.latest_year}: <b>${fullUSD(h.market_value_usd)}</b> entre los paises
        comparados. Share actual de Peru: <b>${pct(h.current_share)}</b>.</p>
      ${table(
        [
          { label: 'Share objetivo', num: true },
          { label: 'Brecha', num: true },
          { label: 'Facturacion adicional', num: true },
          { label: 'Volumen equivalente', num: true },
        ],
        rows
      )}
      <p class="note">${escapeHTML(h.note)}</p>
      <div class="chart"><canvas id="chartLadder" height="90"></canvas></div>
    </section>`
}

// --- Bloque 6: aranceles ---------------------------------------------------------
export function tariffs(result) {
  const l = result.landed_cost || {}
  const rows = (result.tariffs || []).map(
    (t) => `
      <tr>
        <td>${escapeHTML(t.destination_name)}</td>
        <td class="num">${t.duty_pct !== null && t.duty_pct !== undefined ? `${t.duty_pct.toFixed(2)}%` : 'n/d'}</td>
        <td>${t.is_estimated ? '<span class="muted">sin dato cargado</span>' : 'cargado'}</td>
      </tr>`
  )
  return `
    <section class="card">
      <h2>6. Aranceles y costo puesto en destino ${tagAssumed}</h2>
      ${rows.length ? table([{ label: 'Destino' }, { label: 'Arancel', num: true }, { label: 'Estado' }], rows) : ''}
      ${
        l.fob_usd_per_kg !== undefined
          ? `<div class="kpis">
              ${kpi('FOB', usd(l.fob_usd_per_kg))}
              ${kpi('CIF (flete + seguro)', usd(l.cif_usd_per_kg))}
              ${kpi('Arancel', usd(l.duty_usd_per_kg), `${(l.duty_pct ?? 0).toFixed(2)}%`)}
              ${kpi('Costo en destino', usd(l.landed_usd_per_kg))}
              ${kpi('Peso del arancel', pct(l.duty_share_of_landed), 'de la factura del importador')}
            </div>`
          : ''
      }
      <div class="alert warn">${escapeHTML(result.data_quality?.warning || '')}</div>
    </section>`
}

// --- Bloque 7: inversion ---------------------------------------------------------
export function investment(inv) {
  if (!inv) return ''
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
        <td class="num ${(inv.cashflows[r.year] ?? 0) < 0 ? 'neg' : ''}">${fullUSD(inv.cashflows[r.year])}</td>
      </tr>`
  )
  const be = inv.breakeven || {}
  return `
    <section class="card">
      <h2>7. Decision de inversion ${tagAssumed}</h2>
      <div class="${verdictClass(v.label)}">
        <span class="verdict-label">${escapeHTML(v.label)}</span>
        <p>${escapeHTML(v.detail)}</p>
      </div>
      <div class="kpis">
        ${kpi('VAN', fullUSD(s.npv_usd), `al ${s.discount_rate_pct}%`, s.npv_usd < 0 ? 'neg' : '')}
        ${kpi('TIR', s.irr_pct !== null && s.irr_pct !== undefined ? `${s.irr_pct}%` : 'no existe')}
        ${kpi('Payback', s.payback_years !== null && s.payback_years !== undefined ? years(s.payback_years) : 'no se recupera')}
        ${kpi('Inversion inicial', fullUSD(s.initial_outflow_usd))}
      </div>
      <p class="note">Curva de ocupacion: <code>${escapeHTML(JSON.stringify(inv.inputs.utilization_ramp))}</code>
        &mdash; origen: <b>${escapeHTML(inv.ramp_source.source)}</b>. ${escapeHTML(inv.ramp_source.reason)}</p>
      ${
        be.available
          ? `<p class="note">Punto de equilibrio: FOB minimo <b>${usd(be.fob_price_floor_usd_per_kg)}</b>/kg,
             ocupacion minima <b>${pct(be.utilization_floor_pct / 100)}</b>.</p>`
          : ''
      }
      <div class="chart"><canvas id="chartCash" height="90"></canvas></div>
      <h3>Estado de resultados por ano</h3>
      ${table(
        [
          { label: 'Ano', num: true },
          { label: 'Volumen', num: true },
          { label: 'Ingresos', num: true },
          { label: 'Costos var.', num: true },
          { label: 'EBIT', num: true },
          { label: 'Margen', num: true },
          { label: 'FCF', num: true },
        ],
        rows
      )}
    </section>`
}

// --- Bloque 8: sensibilidad ------------------------------------------------------
export function sensitivity(inv) {
  if (!inv || !inv.sensitivity) return ''
  return `
    <section class="card">
      <h2>8. Sensibilidad ${tagAssumed}</h2>
      <p class="note">Cada variable se mueve sola, una a la vez. El largo de la barra es cuanto mueve el VAN.</p>
      <div class="chart chart-tall"><canvas id="chartSens" height="200"></canvas></div>
      <p class="note">VAN base: <b>${fullUSD(inv.sensitivity.base_npv_usd)}</b>.</p>
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
      ${years.map((year) => `<td class="num">${pctSigned(seriesByYear.get(year)?.value_yoy)}</td>`).join('')}
    </tr>`
  })
  const cagrRows = products.map(
    (p) => `<tr>
      <th scope="row">${escapeHTML(p.name || p.slug)} <span class="hs6">HS ${escapeHTML(p.hs6)}</span></th>
      <td class="num">${p.latest_year ?? 'n/d'}</td>
      <td class="num">${pct(p.cagr_value)}</td>
    </tr>`
  )
  return `
    <section class="comparison-page">
      <section class="card comparison-intro">
        <h1>Comparacion de productos</h1>
        <p class="note">${products.length} producto(s) seleccionados. Compara la evolucion anual del valor FOB
          exportado por Peru, su crecimiento interanual y el CAGR para el periodo 2016-2025.</p>
        <p class="note">Fuente: series de exportacion peruana de Trade Map. La grafica de barras compara el ultimo
          ano con datos de cada producto; los vacios en las tablas indican que no hay un valor reportado.</p>
        <span>${tagData}</span>
      </section>
      <section class="comparison-charts">
        <article class="card comparison-chart-card">
          <h2>Valor exportado por producto</h2>
          <p class="note">Ultimo ano disponible (USD FOB)</p>
          <div class="chart"><canvas id="chartComparisonLatest"></canvas></div>
        </article>
        <article class="card comparison-chart-card">
          <h2>Evolucion de exportaciones</h2>
          <p class="note">Valor FOB anual, 2016-2025 (USD)</p>
          <div class="chart"><canvas id="chartComparison"></canvas></div>
        </article>
        <article class="card comparison-chart-card">
          <h2>Crecimiento respecto al ano anterior</h2>
          <p class="note">Variacion anual del valor exportado (%)</p>
          <div class="chart"><canvas id="chartComparisonGrowth"></canvas></div>
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
        <p class="note">El primer ano no tiene crecimiento interanual porque no hay un ano previo en el periodo.</p>
      </section>
      <section class="card comparison-table-card">
        <h2>CAGR 2016-2025</h2>
        ${table(
          [
            { label: 'Producto' },
            { label: 'Ultimo ano disponible', num: true },
            { label: 'CAGR del valor FOB', num: true },
          ],
          cagrRows
        )}
        <p class="note">El CAGR solo se calcula cuando hay valores positivos reportados en 2016 y 2025.</p>
      </section>
    </section>`
}

// --- Procedencia ----------------------------------------------------------------
export function sources(result) {
  const q = result.data_quality || {}
  return `
    <section class="card card-quiet">
      <h3>Procedencia de los datos</h3>
      <ul class="sources">
        <li><b>Mercado y competencia:</b> ${escapeHTML(q.market_data_source)}. Anios con data: ${escapeHTML(JSON.stringify(q.years_with_data))}.</li>
        <li><b>Aranceles:</b> ${escapeHTML(q.tariff_source)}.</li>
        <li><b>Supuestos financieros:</b> ${escapeHTML(q.assumptions_source)}. No provienen de ninguna API.</li>
      </ul>
      <p class="note">Lo marcado ${tagData} viene de una fuente oficial. Lo marcado ${tagAssumed} lo defines tu.
        La distincion es deliberada: confundir ambos es el error mas comun en este tipo de analisis.</p>
    </section>`
}
