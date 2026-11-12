// C9 lesson from mini-calculator: flat ESLint config. The key gotcha is the
// Vue + flat-parser wiring. This is JS-based (not TS) so we skip the
// tseslint parserOptions wiring, but the flat structure is the same.
import js from '@eslint/js'
import pluginVue from 'eslint-plugin-vue'

export default [
  {
    // 'src/sw.js' is a build-time-only Web-API bridge (imported into the SW by
    // vite-plugin-pwa); its real logic lives in the linted/tested
    // src/lib/offline-cache.js, so we skip linting the adapter itself.
    ignores: ['dist', 'node_modules', 'coverage', '*.ts', '.git', 'src/sw.js'],
  },
  js.configs.recommended,
  ...pluginVue.configs['flat/essential'],
  {
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: {
        window: 'readonly',
        navigator: 'readonly',
        console: 'readonly',
        setTimeout: 'readonly',
        setInterval: 'readonly',
        document: 'readonly',
      },
    },
  },
  {
    rules: {
      'no-unused-vars': 'warn',
    },
  },
]
