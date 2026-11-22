// TEMP override for cloudflared quick-tunnel — lives in frontend/ so `vite` resolves from
// frontend/node_modules. Does NOT touch the committed vite.config.js and will NOT be committed.
// It only opens allowedHosts so the tunnel's public hostname is accepted by vite preview.
process.env.PORT = '4173'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  build: { outDir: 'dist' },
  server:  { host: '0.0.0.0', port: 4173, strictPort: true, allowedHosts: 'all' },
  preview: { host: '0.0.0.0', port: 4173, strictPort: true, allowedHosts: 'all' },
})
