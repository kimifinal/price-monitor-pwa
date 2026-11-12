import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { VitePWA } from 'vite-plugin-pwa'

// Mirrors the mini-calculator Vite config: a PWA that builds to GitHub Pages
// (base './') with an auto-updating service worker + manifest.
//
// Issue #6: instead of workbox's generateSW (app-shell only), we ship a CUSTOM
// service worker (src/sw.js) via `injectManifest`. It delegates every request to
// the pure, unit-tested `src/lib/offline-cache.js` strategy so /api/costco/history
// (and /api/crypto) resolve from cache when offline, then fall back to the
// committed snapshot JSON — the 歷史價格比價 cards render last-known series even
// with no network. `src/sw.js` is excluded from ESLint (thin web-API bridge); the
// real logic lives in the linted/tested module it imports.
export default defineConfig({
  base: './',
  plugins: [
    vue(),
    VitePWA({
      injectRegister: 'auto',
      registerType: 'autoUpdate',
      // Flip the build to injectManifest so our CUSTOM service worker
      // (src/sw.js -> offline-cache.js) ships instead of workbox's auto-gen
      // app-shell SW. `strategies` selects the mode; `srcDir`+`filename` point
      // the Vite build's SW entry at src/sw.js, where its relative import of
      // './lib/offline-cache.js' resolves.
      strategies: 'injectManifest',
      srcDir: 'src',
      filename: 'sw.js',
      manifest: {
        name: 'Price Monitor',
        short_name: 'PriceMon',
        description: '追蹤目標價，跌破就通知',
        lang: 'zh-TW',
        display: 'standalone',
        background_color: '#0f0d13',
        theme_color: '#141218',
        icons: [
          { src: 'icons/icon-192x192.png', sizes: '192x192', type: 'image/png' },
          { src: 'icons/icon-512x512.png', sizes: '512x512', type: 'image/png' },
          {
            src: 'icons/icon-512x512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable',
          },
        ],
      },
      injectManifest: {
        // Vite (above, via srcDir+filename) builds src/sw.js into dist/sw.js, and
        // workbox then injects its precache manifest here as `self.__WB_MANIFEST`.
        // These patterns are the app shell — the SW precaches the committed
        // snapshots separately (on install) so the 比價 cards work offline.
        globPatterns: ['index.html', 'assets/**/*', 'icons/**/*', 'manifest.webmanifest'],
      },
      devOptions: { enabled: false },
    }),
  ],
  test: {
    globals: true,
    environment: 'jsdom',
    environmentOptions: {
      jsdom: {
        // Non-opaque origin so window.localStorage is defined.
        url: 'http://localhost:4173/',
      },
    },
    include: ['tests/unit/**/*.test.js'],
    setupFiles: ['tests/setup.js'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'text-summary', 'json-summary', 'html'],
      include: ['src/lib/**', 'src/components/**'],
      // C9 lesson from mini-calculator: thresholds are a real REGRESSION GATE.
      // Set BELOW a realistic baseline so it passes now but turns RED on a drop.
      thresholds: {
        statements: 80,
        branches: 80,
        functions: 80,
        lines: 80,
      },
    },
  },
})
