import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e',
  // CI cold-starts slower in ubuntu-latest; give preview time + retry so a
  // slow Vite preview doesn't flake the whole pipeline.
  retries: process.env.CI ? 2 : 0,
  use: {
    baseURL: 'http://127.0.0.1:4173',
  },
  webServer: {
    command: 'npm run preview',
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: !process.env.CI,
    timeout: 60 * 1000,
  },
  expect: { timeout: 10000 },
})
