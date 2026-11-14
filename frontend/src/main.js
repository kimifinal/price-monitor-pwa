import { createApp } from 'vue'
import App from './App.vue'
// Design-token single source of truth (issue #21): every component resolves
// var(--token) defined in style.css. Global + imported first so tokens exist
// before any component <style> references them.
import './style.css'

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
