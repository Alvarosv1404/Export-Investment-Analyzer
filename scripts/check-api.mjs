/**
 * Verificacion de la API sin depender del backend levantado.
 *
 * `npm test` corre esto antes que pytest. Sirve para dos cosas:
 *   1. Fallar rapido y con un mensaje claro si la API cambio de contrato.
 *   2. No requerir `npm run dev` en un terminal aparte para los tests de
 *      frontend: este script levanta el backend en un hilo, espera el health
 *      check, hace las llamadas y lo apaga.
 *
 * Si prefieres correrlo contra un backend ya levantado en :8000, pasa
 * `--external` y no se levanta ninguno.
 */

import { spawn } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { setTimeout as sleep } from 'node:timers/promises'
import { fileURLToPath } from 'node:url'

const root = join(fileURLToPath(new URL('.', import.meta.url)), '..')
// El puerto sale de dev.config.json, la misma fuente que run-api.mjs y
// vite.config.js. Asi el test nunca apunta a un puerto que ya no existe.
const dev = JSON.parse(readFileSync(join(root, 'dev.config.json'), 'utf8'))
const PORT = dev.api
const HOST = dev.host
const BASE = `http://${HOST}:${PORT}`
const USE_EXTERNAL = process.argv.includes('--external')

let proc = null
let failures = 0

function check(label, condition, detail = '') {
  if (condition) {
    console.log(`  ok    ${label}`)
  } else {
    console.error(`  FAIL  ${label}${detail ? ` -> ${detail}` : ''}`)
    failures += 1
  }
}

async function waitForHealth(timeoutMs = 30_000) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${BASE}/health`)
      if (res.ok) return true
    } catch {
      /* todavia no levanta */
    }
    await sleep(400)
  }
  return false
}

async function startBackend() {
  proc = spawn('python', ['-m', 'uvicorn', 'exportanalysis.api.main:app', '--port', String(PORT)], {
    stdio: 'ignore',
    env: { ...process.env, PYTHONPATH: 'src' },
  })
  const up = await waitForHealth()
  if (!up) throw new Error(`El backend no respondio en ${BASE}/health tras 30s`)
}

async function stopBackend() {
  if (proc && !proc.killed) proc.kill()
}

async function main() {
  console.log(`Verificando la API en ${BASE}`)
  if (!USE_EXTERNAL) await startBackend()
  else if (!(await waitForHealth(5_000))) throw new Error(`No hay backend en ${BASE}; usa --external solo si ya esta corriendo`)

  const health = await fetch(`${BASE}/health`)
  check('GET /health responde 200', health.status, `status ${health.status}`)

  const products = await (await fetch(`${BASE}/api/products`)).json()
  check('GET /api/products devuelve el catalogo', Array.isArray(products.products) && products.products.length > 0)
  check('el reporter por defecto es Peru (604)', products.reporter === 604, `reporter ${products.reporter}`)

  const analysisRes = await fetch(`${BASE}/api/analysis/cafe_verde`)
  check('GET /api/analysis/cafe_verde responde 200', analysisRes.status === 200, `status ${analysisRes.status}`)
  const analysis = await analysisRes.json()
  check('el analisis trae mercado disponible', analysis.market?.available === true)
  check('el mercado tiene FOB > 0', (analysis.market?.latest_fob_usd ?? 0) > 0)
  check('el primer anio no tiene NaN en yoy', analysis.market?.series?.[0]?.value_yoy === null)
  check('la rampa declara su origen', Boolean(analysis.investment?.ramp_source?.source))
  check('el JSON no trae Infinity', !JSON.stringify(analysis).match(/NaN|Infinity/))

  const missing = await fetch(`${BASE}/api/analysis/no_existe`)
  check('slug inexistente da 404', missing.status === 404, `status ${missing.status}`)

  await stopBackend()
  if (failures > 0) {
    console.error(`\n${failures} verificacion(es) fallaron.`)
    process.exit(1)
  }
  console.log('\nAPI verificada.')
}

main().catch(async (err) => {
  await stopBackend()
  console.error(`\nError verificando la API: ${err.message}`)
  process.exit(1)
})
