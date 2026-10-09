/**
 * Levanta FastAPI en el puerto definido en dev.config.json.
 *
 * Existe como script aparte, y no como un "--port 8010" en package.json, por
 * dos razones:
 *   1. El puerto queda en UN solo archivo. package.json, vite.config.js y los
 *      tests lo leen de dev.config.json, asi que cambiarlo no puede desincronizar
 *      el proxy de Vite del backend real. Con el puerto escrito a mano en tres
 *      lugares, el sintoma clasico es "la web carga pero /api da 404" porque el
 *      proxy apunta a un puerto que ya no existe.
 *   2. Fallar claro si el puerto esta ocupado, en vez de un traceback de uvicorn.
 */

import { spawn } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { createServer } from 'node:net'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(fileURLToPath(new URL('.', import.meta.url)), '..')
const config = JSON.parse(readFileSync(join(root, 'dev.config.json'), 'utf8'))
const PORT = config.api
const HOST = config.host

/** Devuelve true si algo ya escucha en el puerto. */
function isPortBusy(port, host) {
  return new Promise((resolve) => {
    const server = createServer()
    server.once('error', () => resolve(true))
    server.once('listening', () => server.close(() => resolve(false)))
    server.listen(port, host)
  })
}

const busy = await isPortBusy(PORT, HOST)
if (busy) {
  console.error(`\n  El puerto ${PORT} ya esta ocupado.`)
  console.error(`  Opciones:`)
  console.error(`    - cerrar el proceso que lo usa, o`)
  console.error(`    - cambiar "api" en dev.config.json y volver a correr npm run dev\n`)
  process.exit(1)
}

console.log(`API en http://${HOST}:${PORT}  (puerto de dev.config.json)`)
console.log('Docs interactivas: /docs\n')

const proc = spawn('python', ['-m', 'uvicorn', 'exportanalysis.api.main:app', '--reload', '--port', String(PORT), '--host', HOST], {
  cwd: root,
  stdio: 'inherit',
  env: { ...process.env, PYTHONPATH: 'src' },
})

proc.on('exit', (code) => process.exit(code ?? 0))
for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => proc.kill(signal))
}
