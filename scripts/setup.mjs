/**
 * Prepara el entorno para `npm run dev`.
 *
 * Instala las dependencias de Node y verifica que las de Python esten
 * disponibles. No falla duro si falta algo de Python: avisa con el comando
 * exacto y sigue, porque el frontend se puede levantar igual y asi el error
 * aparece en el terminal de uvicorn, que es donde pertenece.
 */

import { spawnSync } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(fileURLToPath(new URL('.', import.meta.url)), '..')
const dev = JSON.parse(readFileSync(join(root, 'dev.config.json'), 'utf8'))

function run(cmd, args) {
  console.log(`\n$ ${cmd} ${args.join(' ')}`)
  return spawnSync(cmd, args, { cwd: root, stdio: 'inherit', shell: process.platform === 'win32' }).status === 0
}

console.log('1/3  Dependencias de Node')
if (!run('npm', ['install'])) {
  console.error('Fallo npm install.')
  process.exit(1)
}

console.log('\n2/3  Paquete Python (exportanalysis)')
const pyOk = run('python', ['-m', 'pip', 'install', '-e', '.'])
if (!pyOk) {
  console.warn('\n  No se pudo instalar el paquete Python. Para que uvicorn lo encuentre:')
  console.warn('    python -m pip install -e ".[dev]"')
}

console.log('\n3/3  Plantilla de aranceles')
if (!existsSync(join(root, 'data', 'raw', 'tariffs', 'tariffs.csv'))) {
  run('python', ['-c', 'import sys; sys.path.insert(0,"src"); from exportanalysis.sources.manual_tariffs import ensure_template; ensure_template()'])
}

console.log('\nListo. Levanta todo con:\n  npm run dev')
console.log(`  web  -> http://${dev.host}:${dev.web}   (Vite, hace proxy a la API)`)
console.log(`  api  -> http://${dev.host}:${dev.api}   (FastAPI directo, por si la quieres)`)
