/**
 * Formato de numeros para el reporte.
 *
 * Todo el formato de moneda y porcentaje vive aca en vez de esparcido en los
 * templates. La razon es que los datos vienen en distintos monedas y escalas:
 * el FOB de Peru esta en miles de millones y el precio por kilo en 4.62. Sin
 * una funcion comun, cada bloque termina con su propia convencion y el reporte
 * se vuelve dificil de leer de un vistazo.
 */

const LOCALE = 'es-PE'

/** Compacta montos grandes: 1.1e9 -> "$1,100M". Para ejes y barras. */
export function compactUSD(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return 'n/d'
  const abs = Math.abs(value)
  if (abs >= 1e9) return `$${(value / 1e9).toFixed(2)}MM`
  if (abs >= 1e6) return `$${(value / 1e6).toFixed(1)}M`
  if (abs >= 1e3) return `$${(value / 1e3).toFixed(0)}K`
  return `$${value.toFixed(0)}`
}

/** Monto completo con separadores: 1100414274 -> "$1,100,414,274". */
export function fullUSD(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return 'n/d'
  return `$${Math.round(value).toLocaleString(LOCALE)}`
}

/** Volumen en kg con separadores y sin decimales. */
export function kg(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return 'n/d'
  return `${Math.round(value).toLocaleString(LOCALE)} kg`
}

/** Fraccion a porcentaje: 0.0658 -> "6.6%". */
export function pct(fraction, digits = 1) {
  if (fraction === null || fraction === undefined || Number.isNaN(fraction)) return 'n/d'
  return `${(fraction * 100).toFixed(digits)}%`
}

/** Porcentaje con signo explicito, para deltas: 0.054 -> "+5.4%". */
export function pctSigned(fraction, digits = 1) {
  if (fraction === null || fraction === undefined || Number.isNaN(fraction)) return 'n/d'
  const sign = fraction > 0 ? '+' : ''
  return `${sign}${(fraction * 100).toFixed(digits)}%`
}

/** Precio por kilo: 4.619 -> "$4.619". */
export function usd(value, digits = 3) {
  if (value === null || value === undefined || Number.isNaN(value)) return 'n/d'
  return `$${value.toFixed(digits)}`
}

/** Anos a texto: 2.5 -> "2.5 anos", 3 -> "3 anos". */
export function years(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return 'n/d'
  const rounded = Math.round(value * 100) / 100
  return `${rounded} ${rounded === 1 ? 'ano' : 'anos'}`
}

/**
 * Etiqueta de veredicto -> clase CSS.
 *
 * El CSS tiene una clase por veredicto. Se separa aqui para que anadir un
 * veredicto nuevo en el modelo no rompa el estilo en silencio.
 */
export function verdictClass(label) {
  if (!label) return 'verdict'
  const slug = label.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '')
  return `verdict verdict-${slug.replace(/\s+/g, '-')}`
}
