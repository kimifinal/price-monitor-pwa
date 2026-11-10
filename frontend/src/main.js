import { createApp } from 'vue'
import App from './App.vue'

// Register the PWA service worker (vite-plugin-pwa injects this at build time;
// the manual guard keeps the dev server from failing on a missing SW).
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch((err) => {
      console.warn('[pwa] SW registration failed:', err)
    })
  })
}

createApp(App).mount('#app')
