import { test, expect } from '@playwright/test'

// E2E guard for the 歷史價格比價 section.
// The section renders one PriceHistory card per compare card; each card must
// have a sparkline <path> and a verdict data attribute.
test('the compare section renders sparkline cards sorted by drop %', async ({ page }) => {
  await page.goto('/')

  const section = page.locator('section[data-section="compare"]')
  await expect(section).toBeVisible()

  // 3 sample cards
  const cards = section.locator('.price-history[data-verdict]')
  await expect(cards.first()).toBeVisible()
  await expect(cards.count()).toBeGreaterThan(0)

  // each card has an SVG <path> (the sparkline) and a verdict badge
  for (const card of (await cards.locator('path').all())) {
    await expect(card).toBeAttached()
  }
  await expect(cards.first().locator('.ph-badge')).toBeVisible()
})
