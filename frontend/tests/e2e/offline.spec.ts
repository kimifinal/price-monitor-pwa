import { test, expect } from '@playwright/test'

// OFFLINE GUARD (issue #6: 離線 PWA).
//
// Best-effort / NON-BLOCKING by design: this exercises the whole offline chain —
// the service worker precaches the committed snapshot, and with the network cut
// the 即時比價 (live) section must still render a movement card from that
// snapshot. The HARDF guard for the same contract is the deterministic unit test
// in tests/unit/offline-cache.test.js (which runs everywhere, incl. a CI
// browser-less runner). This spec is wired as a `continue-on-error` step in
// .github/workflows/ci.yml so a flaky/offline sandbox can never turn CI red.
test('the live section renders a movement card fully offline (SW + baked snapshot)', async ({
  context,
  page,
}) => {
  // 1) Online first: install + precache the SW (shell + both snapshots).
  await page.goto('/')
  const worker = await context.waitForEvent('worker')
  await waitUntilActivated(worker)

  // 2) Cut the network, including the API, then reload so the SW serves cache.
  await context.setOffline(true)
  await context.route('**/api/**', (route) => route.abort())
  await page.goto('/')
  await page.waitForLoadState('networkidle').catch(() => {})

  // 3) The live section's cards come from the cache/snapshot, not the network.
  const live = page.locator('section[data-section="live"]')
  await expect(live).toBeVisible()
  const cards = live.locator('.price-history[data-verdict]')
  expect(await cards.count()).toBeGreaterThanOrEqual(1)
  // at least one rendered movement card carries a visible sparkline path
  await expect(live.locator('path').first()).toBeVisible()
})

// Poll the worker's ready state so a slow (re)activation doesn't flake the guard.
async function waitUntilActivated(worker) {
  const deadline = Date.now() + 8000
  while (Date.now() < deadline) {
    const state = await worker.state().catch(() => 'installing')
    if (state === 'activated') return
    await new Promise((r) => setTimeout(r, 150))
  }
}
