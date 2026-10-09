import js from '@eslint/js'

export default [
  {
    ignores: ['dist/**', 'node_modules/**'],
  },
  js.configs.recommended,
  {
    files: ['frontend/js/**/*.js'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: {
        // Chart.js llega por <script> en index.html, no como modulo.
        Chart: 'readonly',
        console: 'readonly',
        document: 'readonly',
        fetch: 'readonly',
        history: 'readonly',
        location: 'readonly',
        setTimeout: 'readonly',
        URL: 'readonly',
        URLSearchParams: 'readonly',
        window: 'readonly',
      },
    },
    rules: {
      'no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
    },
  },
  {
    files: ['scripts/**/*.mjs'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: {
        process: 'readonly',
        console: 'readonly',
        fetch: 'readonly',
        setTimeout: 'readonly',
        URL: 'readonly',
      },
    },
  },
  {
    files: ['*.config.js'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: {
        URL: 'readonly',
      },
    },
  },
]
