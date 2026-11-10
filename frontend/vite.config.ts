import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { VitePWA } from 'vite-plugin-pwa'

// Mirrors the mini-calculator Vite config: a PWA that builds to GitHub Pages
// (base './') with an auto-updating service worker + manifest.
export default defineConfig({
  base: './',
  plugins: [
    vue(),
    VitePWA({
      injectRegister: 'auto',
      registerType: 'autoUpdate',
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
      workbox: {
        globPatterns: ['index.html', 'assets/**/*'],
        navigateFallback: 'index.html',
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
